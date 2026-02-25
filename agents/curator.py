"""
agents/curator.py v4 — Unified Three-Edition News Curation

Morning edition (runs 7:00 AM EST):
  • News window : previous 6:00 PM EST → today 7:00 AM EST  (~14 hrs)

Midday edition (runs 1:00 PM EST):
  • News window : today 7:00 AM EST → today 1:00 PM EST      (~7 hrs)

Evening edition (runs 5:30 PM EST):
  • News window : today 1:00 PM EST → today 5:30 PM EST      (~5 hrs)

All editions: 5 stories (2 business + 1 overlap + 2 tech), ~12 min target.
Soft dedup: earlier same-day stories provide context, not hard exclusion.
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

# ─── News Sources ─────────────────────────────────────────────────────────────

RSS_FEEDS = {
    "business": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.reuters.com/reuters/companyNews",
        "https://www.cnbc.com/id/10001147/device/rss/rss.html",
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",
        "https://fortune.com/feed/",
        "https://feeds.ft.com/ft/businessnews",
        "https://feeds.feedburner.com/wsj/xml/rss/3_7085.xml",
        "https://hbr.org/feeds/topics/business-communication.rss",
        "https://www.economist.com/business/rss.xml",
        "https://seekingalpha.com/market_currents.xml",
    ],
    "tech": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://www.wired.com/feed/rss",
        "https://feeds.feedburner.com/venturebeat/SZYF",
        "https://www.technologyreview.com/feed/",
        "https://feeds.feedburner.com/TechCrunch/startups",
        "https://news.ycombinator.com/rss",
        "https://www.infoworld.com/index.rss",
        "https://spectrum.ieee.org/feeds/feed.rss",
    ],
    "ai_specific": [
        "https://www.artificialintelligence-news.com/feed/",
        "https://www.deeplearning.ai/the-batch/feed/",
        "https://importai.substack.com/feed",
    ],
    "politics": [
        "https://feeds.reuters.com/reuters/politicsNews",
        "https://rss.politico.com/congress.xml",
        "https://thehill.com/feed/",
    ],
}

# ─── Edition-specific time windows (hours back from now) ─────────────────────
EDITION_LOOKBACK_HOURS = {
    "morning": 14,
    "midday":  7,
    "evening": 5,
}

EDITION_LABELS = {
    "morning": "MORNING",
    "midday":  "MIDDAY",
    "evening": "EVENING",
}

# ─── Unified system prompt ───────────────────────────────────────────────────

CURATOR_SYSTEM_PROMPT = """You are the senior editorial producer for "The Signal," a three-daily business, tech, and policy podcast.

You are curating the {edition_label} EDITION ({publish_time} EST). All editions follow the same format:
  • 10-15 minutes of content (~12 min ideal, 5 stories)
  • 2 business stories + 1 crossover/overlap story + 2 tech stories
  • Each story ~2 minutes

EDITION TONE: Concise, conversational, and smart. Each story gets a punchy headline, key context,
and one sharp insight. Keep it moving — the listener wants the signal, not the noise.

STORY QUOTAS (strict):
  business_stories : exactly 2 fresh stories (each ~2 min)
  overlap_stories  : exactly 1 crossover story bridging business and tech (~2 min)
  tech_stories     : exactly 2 fresh stories (each ~2 min)
  Total: 5 stories, all uniform format

POLITICS INSTRUCTION: Include political and policy stories ONLY when they have direct, concrete
implications for business or technology. A regulation affecting tech companies qualifies. A purely
electoral horse-race story does not. Mark these with "policy_angle": true in the story object.

HOOK: Generate a 3-5 word punchy episode hook.
  Good examples: "Markets Open Under Pressure" / "AI Chips Change Everything" / "Fed Sends Mixed Signals"
  Bad examples: "Morning Edition Episode" / "Today's Business News"

PRIORITY RULES:
  MUST_INCLUDE injected stories → always include, improve framing, never drop
  CONSIDER injected stories     → high-priority tip, include if stronger than organic option
  BACKGROUND injected stories   → use as context only

DEDUPLICATION:
  Do NOT cover stories from the last 3 days unless a major new development warrants UPDATE: framing.
  If earlier editions today covered a story, you MAY revisit it with UPDATE framing if there are
  significant new developments. Otherwise, find fresh stories.

OUTPUT: Valid JSON only, exact schema below."""


class CuratorAgent:

    def run(self, episode_date: str, edition: str) -> dict:
        edition = edition.lower()
        lookback_hours = EDITION_LOOKBACK_HOURS[edition]

        # 1. Load injections for this edition
        injections = get_pending_injections(episode_date, edition)
        must    = [i for i in injections if i["priority"] == "must_include"]
        consider = [i for i in injections if i["priority"] == "consider"]
        bg      = [i for i in injections if i["priority"] == "background"]
        log.info(f"  Injections: {len(must)} must, {len(consider)} consider, {len(bg)} bg")

        # 2. Gather raw news within the edition's time window
        raw_stories = self._gather_stories(lookback_hours)
        log.info(f"  Gathered {len(raw_stories)} raw stories (lookback {lookback_hours}h)")

        # 3. Earlier editions context (soft dedup)
        earlier_headlines = get_earlier_edition_headlines(episode_date, edition)
        if earlier_headlines:
            log.info(f"  Context from {len(earlier_headlines)} earlier edition stories")

        # 4. Recent history (3-day cooldown on topics, all editions)
        recent_summary = build_recently_covered_summary(days=3)

        # 5. Curate with Claude
        brief = self._curate_with_claude(
            raw_stories, injections, recent_summary, episode_date,
            edition, earlier_headlines,
        )

        # 6. Mark injections used
        mark_injections_used(episode_date, edition)

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

        for category, feeds in RSS_FEEDS.items():
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
        tier1 = ["Reuters", "Financial Times", "Wall Street Journal", "Bloomberg",
                 "Economist", "MIT Technology Review", "IEEE Spectrum", "Politico"]
        tier2 = ["TechCrunch", "Wired", "Ars Technica", "CNBC", "Fortune",
                 "VentureBeat", "The Verge", "Harvard Business Review", "The Hill"]
        n = name.lower()
        for t in tier1:
            if t.lower() in n: return 3
        for t in tier2:
            if t.lower() in n: return 2
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
        for category in ["business", "technology"]:
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
        return stories

    # ─── Claude curation ──────────────────────────────────────────────────────

    def _curate_with_claude(
        self, raw_stories: list, injections: list, recent_summary: str,
        episode_date: str, edition: str, earlier_headlines: list,
    ) -> dict:

        edition_label = EDITION_LABELS[edition]
        publish_times = {"morning": "7:00 AM", "midday": "1:00 PM", "evening": "5:30 PM"}
        system_prompt = CURATOR_SYSTEM_PROMPT.format(
            edition_label=edition_label,
            publish_time=publish_times[edition],
        )

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
                    inj_block += (f"  • [{s.get('category','?').upper()}] {s['headline']}{note}\n"
                                  f"    {s['summary']}\n    {s.get('context','')}\n"
                                  f"    Points: {'; '.join(s.get('talking_points', []))}\n")
            if consider:
                inj_block += "\n🟡 CONSIDER:\n"
                for i in consider:
                    s = i["story"]
                    note = f"\n   Note: {i['note']}" if i.get("note") else ""
                    inj_block += f"  • [{s.get('category','?').upper()}] {s['headline']}{note}\n    {s['summary']}\n"
            if bg:
                inj_block += "\n⚪ BACKGROUND:\n"
                for i in bg:
                    inj_block += f"  • {i['story']['headline']}: {i['story']['summary'][:150]}\n"

        # ── Earlier editions context block (soft dedup) ───────────────────────
        context_block = ""
        if earlier_headlines:
            context_block = "\n\n=== EARLIER EDITIONS TODAY (for context — revisit only with UPDATE framing if major new developments) ===\n"
            for h in earlier_headlines:
                context_block += f"  • [{h['edition'].upper()}] {h['headline']}\n"

        # ── Raw stories ────────────────────────────────────────────────────────
        raw_sorted = sorted(raw_stories, key=lambda x: -x.get("source_weight", 1))
        stories_text = json.dumps(raw_sorted[:90], indent=2)

        # ── Schema (unified for all editions) ─────────────────────────────────
        schema_note = """Return this EXACT JSON structure:
{
  "episode_date": "...",
  "edition": "%s",
  "episode_hook": "3-5 word punchy hook",
  "show_theme": "One sentence — today's overarching narrative",
  "business_stories": [
    {
      "rank": 1,
      "type": "standard",
      "podcast_headline": "Punchy headline",
      "source": "...", "url": "...",
      "context": "2-3 sentences",
      "extrapolation": "1-2 sentences",
      "talking_points": ["3-4 debatable points"],
      "debate_angle": "Core tension",
      "lead_host": "alex",
      "injected": false,
      "policy_angle": false,
      "estimated_minutes": 2
    }
  ],
  "overlap_stories": [ /* exactly 1 crossover story, same schema */ ],
  "tech_stories": [ /* exactly 2 tech stories, same schema */ ],
  "editorial_note": "Optional note to scriptwriter"
}

All stories should be type "standard". Each story ~2 min.
Total episode target: ~12 minutes (10-15 min acceptable range).""" % edition

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
