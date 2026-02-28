"""
agents/curator.py v5 — Multi-Show News Curation

Reads feeds, source tiers, NewsAPI config, and system prompt from ShowConfig.
"""

import os
import json
import logging
import feedparser
import requests
from anthropic import Anthropic
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from agents.inject_stories import get_pending_injections, mark_injections_used
from agents.story_memory import (
    build_recently_covered_summary,
    get_earlier_edition_headlines,
)

log = logging.getLogger("curator")
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
EST = ZoneInfo("America/New_York")


class CuratorAgent:

    def __init__(self, show=None):
        if show is None:
            from agents.show_loader import load_show
            show = load_show("the-signal")
        self.show = show

    def run(self, episode_date: str, edition: str) -> dict:
        edition = edition.lower()
        edition_config = self.show.editions.get(edition, {})
        lookback_hours = edition_config.get("news_window_hours", 14)

        # 1. Load injections for this edition
        injections = get_pending_injections(episode_date, edition, show_slug=self.show.slug)
        must    = [i for i in injections if i["priority"] == "must_include"]
        consider = [i for i in injections if i["priority"] == "consider"]
        bg      = [i for i in injections if i["priority"] == "background"]
        log.info(f"  Injections: {len(must)} must, {len(consider)} consider, {len(bg)} bg")

        # 2. Gather raw news within the edition's time window
        raw_stories = self._gather_stories(lookback_hours)
        log.info(f"  Gathered {len(raw_stories)} raw stories (lookback {lookback_hours}h)")

        # 3. Earlier editions context (soft dedup)
        earlier_headlines = get_earlier_edition_headlines(episode_date, edition, show=self.show)
        if earlier_headlines:
            log.info(f"  Context from {len(earlier_headlines)} earlier edition stories")

        # 4. Recent history (3-day cooldown on topics, all editions)
        cooldown_days = self.show.pipeline_config.get("story_cooldown_days", 3)
        recent_summary = build_recently_covered_summary(days=cooldown_days, show=self.show)

        # 5. Curate with Claude
        brief = self._curate_with_claude(
            raw_stories, injections, recent_summary, episode_date,
            edition, earlier_headlines,
        )

        # 6. Mark injections used
        mark_injections_used(episode_date, edition, show_slug=self.show.slug)

        # 7. Attach metadata
        brief["edition"] = edition
        brief["injections_used"] = {
            "must_include": len(must),
            "consider": len(consider),
            "background": len(bg),
        }

        return brief

    # ─── Story gathering ───────────────────────────────────────────────────────

    def _gather_stories(self, lookback_hours: int) -> list:
        cutoff = datetime.now() - timedelta(hours=lookback_hours)
        stories = []

        for category, feeds in self.show.feeds.items():
            for feed_url in feeds:
                try:
                    feed = feedparser.parse(feed_url, request_headers={"User-Agent": "TheSignalBot/4.0"})
                    for entry in feed.entries[:12]:
                        published = self._parse_date(entry.get("published", ""))
                        if published and published < cutoff:
                            continue
                        title = entry.get("title", "").strip()
                        if len(title) < 15 or title.lower().startswith("sponsored"):
                            continue
                        stories.append({
                            "title": title,
                            "summary": self._clean_html(entry.get("summary", ""))[:600],
                            "url": entry.get("link", ""),
                            "source": feed.feed.get("title", feed_url),
                            "published": str(published) if published else "",
                            "category_hint": category,
                            "source_weight": self._source_weight(feed.feed.get("title", "")),
                        })
                except Exception as e:
                    log.warning(f"  Feed failed ({feed_url[:50]}): {e}")

        # NewsAPI supplement
        news_api_key = os.getenv("NEWS_API_KEY")
        if news_api_key:
            stories.extend(self._fetch_newsapi(news_api_key, lookback_hours))

        return self._deduplicate(stories)

    def _source_weight(self, name: str) -> int:
        tiers = self.show.source_tiers
        n = name.lower()
        for t in tiers.get("tier1", []):
            if t.lower() in n:
                return 3
        for t in tiers.get("tier2", []):
            if t.lower() in n:
                return 2
        return 1

    def _clean_html(self, text: str) -> str:
        import re
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _deduplicate(self, stories: list) -> list:
        seen, unique = [], []
        for s in stories:
            words = set(s["title"].lower().split())
            if not any(len(words & sw) / max(len(words), len(sw), 1) > 0.6 for sw in seen):
                seen.append(words)
                unique.append(s)
        log.info(f"  After dedup: {len(unique)} stories (removed {len(stories)-len(unique)})")
        return unique

    def _fetch_newsapi(self, api_key: str, lookback_hours: int) -> list:
        stories = []
        from_dt = (datetime.now() - timedelta(hours=lookback_hours)).strftime("%Y-%m-%dT%H:%M:%S")
        newsapi = self.show.newsapi_config

        if newsapi.get("mode") == "categories":
            for category in newsapi.get("categories", ["business", "technology"]):
                try:
                    resp = requests.get(
                        "https://newsapi.org/v2/top-headlines",
                        params={"category": category, "language": "en", "pageSize": 20,
                                "from": from_dt, "country": "us"},
                        headers={"X-Api-Key": api_key}, timeout=10,
                    )
                    for article in resp.json().get("articles", []):
                        title = (article.get("title") or "").strip()
                        if not title or title == "[Removed]":
                            continue
                        stories.append({
                            "title": title,
                            "summary": (article.get("description") or "")[:600],
                            "url": article.get("url", ""),
                            "source": article.get("source", {}).get("name", ""),
                            "published": article.get("publishedAt", ""),
                            "category_hint": category,
                            "source_weight": 2,
                        })
                except Exception as e:
                    log.warning(f"  NewsAPI failed: {e}")
        elif newsapi.get("mode") == "keywords":
            # Keyword-based search (for niche shows like golf)
            for query in newsapi.get("queries", []):
                try:
                    resp = requests.get(
                        "https://newsapi.org/v2/everything",
                        params={"q": query, "language": "en", "pageSize": 20,
                                "from": from_dt, "sortBy": "publishedAt"},
                        headers={"X-Api-Key": api_key}, timeout=10,
                    )
                    for article in resp.json().get("articles", []):
                        title = (article.get("title") or "").strip()
                        if not title or title == "[Removed]":
                            continue
                        stories.append({
                            "title": title,
                            "summary": (article.get("description") or "")[:600],
                            "url": article.get("url", ""),
                            "source": article.get("source", {}).get("name", ""),
                            "published": article.get("publishedAt", ""),
                            "category_hint": "general",
                            "source_weight": 2,
                        })
                except Exception as e:
                    log.warning(f"  NewsAPI keyword search failed: {e}")

        return stories

    # ─── Claude curation ──────────────────────────────────────────────────────

    def _curate_with_claude(
        self, raw_stories: list, injections: list, recent_summary: str,
        episode_date: str, edition: str, earlier_headlines: list,
    ) -> dict:

        edition_config = self.show.editions.get(edition, {})
        edition_label = edition.upper()
        publish_time_est = edition_config.get("publish_time_est", "07:00")
        # Format publish time nicely
        h, m = publish_time_est.split(":")
        h_int = int(h)
        ampm = "AM" if h_int < 12 else "PM"
        h_12 = h_int if h_int <= 12 else h_int - 12
        publish_time = f"{h_12}:{m} {ampm}"

        # Load system prompt from show config
        system_template = self.show.prompts.get("curator", "")
        if system_template:
            system_prompt = system_template.format(
                show_name=self.show.name,
                show_tagline=self.show.tagline,
                edition_label=edition_label,
                publish_time=publish_time,
            )
        else:
            system_prompt = f"You are the editorial producer for {self.show.name}. Curate stories for the {edition_label} edition."

        # ── Injection block ────────────────────────────────────────────────────
        inj_block = ""
        must    = [i for i in injections if i["priority"] == "must_include"]
        consider = [i for i in injections if i["priority"] == "consider"]
        bg      = [i for i in injections if i["priority"] == "background"]
        if injections:
            inj_block = "\n\n=== PRODUCER INJECTIONS ===\n"
            if must:
                inj_block += "\n🔴 MUST INCLUDE:\n"
                for i in must:
                    s = i["story"]
                    note = f"\n   Note: {i['note']}" if i.get("note") else ""
                    inj_block += (f"  * [{s.get('category','?').upper()}] {s['headline']}{note}\n"
                                  f"    {s['summary']}\n    {s.get('context','')}\n"
                                  f"    Points: {'; '.join(s.get('talking_points', []))}\n")
            if consider:
                inj_block += "\n🟡 CONSIDER:\n"
                for i in consider:
                    s = i["story"]
                    note = f"\n   Note: {i['note']}" if i.get("note") else ""
                    inj_block += f"  * [{s.get('category','?').upper()}] {s['headline']}{note}\n    {s['summary']}\n"
            if bg:
                inj_block += "\n⚪ BACKGROUND:\n"
                for i in bg:
                    inj_block += f"  * {i['story']['headline']}: {i['story']['summary'][:150]}\n"

        # ── Earlier editions context block (soft dedup) ───────────────────────
        context_block = ""
        if earlier_headlines:
            context_block = "\n\n=== EARLIER EDITIONS TODAY (for context — revisit only with UPDATE framing if major new developments) ===\n"
            for h in earlier_headlines:
                context_block += f"  * [{h['edition'].upper()}] {h['headline']}\n"

        # ── Raw stories ────────────────────────────────────────────────────────
        raw_sorted = sorted(raw_stories, key=lambda x: -x.get("source_weight", 1))
        stories_text = json.dumps(raw_sorted[:90], indent=2)

        # ── Build story quotas string from config ─────────────────────────────
        quotas = self.show.story_quotas
        quota_lines = []
        for key, count in quotas.items():
            label = key.replace("_", " ")
            quota_lines.append(f"  {key} : exactly {count} stories")
        total = sum(quotas.values())

        # ── Schema ────────────────────────────────────────────────────────────
        story_categories = list(quotas.keys())
        schema_stories = {}
        for cat in story_categories:
            schema_stories[cat] = "[/* story objects */]"

        schema_note = f"""Return this EXACT JSON structure:
{{
  "episode_date": "...",
  "edition": "{edition}",
  "episode_hook": "3-5 word punchy hook",
  "show_theme": "One sentence — today's overarching narrative",
  {', '.join(f'"{cat}": [...]' for cat in story_categories)},
  "editorial_note": "Optional note to scriptwriter"
}}

Each story object:
{{
  "rank": 1,
  "type": "standard",
  "podcast_headline": "Punchy headline",
  "source": "...", "url": "...",
  "context": "2-3 sentences",
  "extrapolation": "1-2 sentences",
  "talking_points": ["3-4 debatable points"],
  "debate_angle": "Core tension",
  "lead_host": "host_key",
  "injected": false,
  "policy_angle": false,
  "estimated_minutes": 2
}}

Story quotas:
{chr(10).join(quota_lines)}
Total: {total} stories."""

        prompt = f"""Date: {episode_date} | Edition: {edition_label}

{recent_summary}
{context_block}
{inj_block}

=== RAW STORIES ({len(raw_sorted[:90])} in window) ===
{stories_text}

{schema_note}

INCLUDE all MUST_INCLUDE injections. Integrate CONSIDER injections if they beat organic options."""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())

    # ─── Date parser ──────────────────────────────────────────────────────────

    def _parse_date(self, date_str: str):
        if not date_str:
            return None
        try:
            import email.utils
            parsed = email.utils.parsedate(date_str)
            if parsed:
                return datetime(*parsed[:6])
        except Exception:
            pass
        try:
            clean = date_str.replace("Z", "").split("+")[0].split(".")[0]
            return datetime.fromisoformat(clean)
        except Exception:
            return None
