"""
agents/curator.py v3 — Edition-Aware News Curation

AM edition (runs 4:00 AM EST):
  • News window : yesterday 1:00 PM EST → today 4:00 AM EST  (~15 hrs)
  • Also pulls  : yesterday_recap block from story memory (top PM stories)
  • Hook style  : Forward-looking — "what set up today"

PM edition (runs 1:00 PM EST):
  • News window : today 4:00 AM EST → today 1:00 PM EST      (~9 hrs)
  • Excludes    : stories already covered in today's AM edition
  • Hook style  : Summary of "what broke this morning"
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
    get_am_story_headlines,
    get_yesterday_pm_recap,
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
}

# ─── Edition-specific time windows (hours back from now) ─────────────────────
#   AM: from yesterday 1 PM EST to today 4 AM EST = ~15 hours
#   PM: from today 4 AM EST to today 1 PM EST     = ~9 hours
EDITION_LOOKBACK_HOURS = {
    "am": 16,   # Slight buffer beyond the 15hr window
    "pm": 10,   # Slight buffer beyond the 9hr window
}

# ─── System prompts ───────────────────────────────────────────────────────────

CURATOR_SYSTEM_PROMPT_AM = """You are the senior editorial producer for "The Signal," a twice-daily business and tech podcast.

You are curating the MORNING EDITION (4:00 AM EST). This episode has two jobs:
  1. YESTERDAY'S RECAP — briefly revisit the 2-3 biggest stories from yesterday afternoon's PM edition
  2. OVERNIGHT NEWS    — cover the most important stories that broke since 1 PM yesterday

MORNING EDITION TONE: "Here's where we left off, here's what happened overnight, here's what it means for your day."
The listener is waking up. They want orientation, not overload. Lead with what they missed that matters.

STORY QUOTAS (strict):
  yesterday_recap   : exactly 2-3 stories from yesterday's PM (these come from story memory — summarise, don't re-investigate)
  business_stories  : exactly 2 fresh overnight stories (1 deep + 1 medium)
  overlap_stories   : exactly 1 fresh overnight story bridging business and tech
  tech_stories      : exactly 2 fresh overnight stories (1 deep + 1 medium)
  Total fresh stories: 5 (plus the recap block)

HOOK: Generate a 3-5 word punchy episode hook for the AM edition.
  Good examples: "Markets Open Under Pressure" / "AI Chips Change Everything" / "Fed Sends Mixed Signals"
  Bad examples: "Morning Edition Episode" / "Today's Business News"

PRIORITY RULES:
  MUST_INCLUDE injected stories → always include, improve framing, never drop
  CONSIDER injected stories     → high-priority tip, include if stronger than organic option
  BACKGROUND injected stories   → use as context only

DEDUPLICATION:
  Do NOT cover stories from the last 3 days unless a major new development warrants UPDATE: framing
  Yesterday's recap stories should be brief (1-2 sentences each) — not full re-investigations

OUTPUT: Valid JSON only, exact schema below."""

CURATOR_SYSTEM_PROMPT_PM = """You are the senior editorial producer for "The Signal," a twice-daily business and tech podcast.

You are curating the AFTERNOON EDITION (1:00 PM EST) — a tight 8–15 minute HIGHLIGHTS REEL.
This is NOT a deep-dive episode. It covers the morning's biggest stories quickly and conversationally.

AFTERNOON EDITION TONE: "Here's what happened this morning — the highlights, fast."
The listener wants a quick catch-up, not a seminar. Each story gets a punchy headline, one key
takeaway, and maybe one sharp exchange between Alex and Morgan. That's it. Keep it moving.

STORY QUOTAS (strict):
  business_stories : exactly 2 fresh morning stories (both quick — headline + key takeaway)
  overlap_stories  : exactly 1 story bridging business and tech (quick)
  tech_stories     : exactly 2 fresh morning stories (both quick — headline + key takeaway)
  Total: 5 stories (all fresh since 4 AM EST, all quick format)

ESTIMATED MINUTES: Each story should be ~1.5–2 minutes. Total content ~8–10 min + intro/outro.

HOOK: Generate a 3-5 word punchy episode hook for the PM edition.
  Good examples: "Midday Markets Rethink Everything" / "Fed Breaks From Script" / "OpenAI Makes Its Move"
  Bad examples: "Afternoon Edition News" / "PM Episode Summary"

CRITICAL — NO REPEATS:
  The AM edition already covered overnight news. The stories listed under "AM STORIES ALREADY COVERED"
  must NOT be re-covered unless a dramatic new development occurred (use UPDATE: framing if so).
  Your job is to cover what happened THIS MORNING, not to recap the AM episode.

PRIORITY RULES:
  MUST_INCLUDE injected stories → always include
  CONSIDER injected stories     → include if stronger than organic
  BACKGROUND injected stories   → context only

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

        # 3. Edition-specific context
        if edition == "am":
            # Get yesterday's PM stories for the recap block
            yesterday_recap = get_yesterday_pm_recap(episode_date)
            am_exclusions = []
        else:
            # PM: exclude what AM already covered today
            yesterday_recap = []
            am_exclusions = get_am_story_headlines(episode_date)
            if am_exclusions:
                log.info(f"  Excluding {len(am_exclusions)} stories from today's AM edition")

        # 4. Recent history (3-day cooldown on topics, both editions)
        recent_summary = build_recently_covered_summary(days=3)

        # 5. Curate with Claude
        brief = self._curate_with_claude(
            raw_stories, injections, recent_summary, episode_date,
            edition, yesterday_recap, am_exclusions,
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
                    feed = feedparser.parse(feed_url, request_headers={"User-Agent": "TheSignalBot/3.0"})
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
                 "Economist", "MIT Technology Review", "IEEE Spectrum"]
        tier2 = ["TechCrunch", "Wired", "Ars Technica", "CNBC", "Fortune",
                 "VentureBeat", "The Verge", "Harvard Business Review"]
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
        episode_date: str, edition: str,
        yesterday_recap: list, am_exclusions: list,
    ) -> dict:

        system_prompt = CURATOR_SYSTEM_PROMPT_AM if edition == "am" else CURATOR_SYSTEM_PROMPT_PM

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

        # ── AM recap block ─────────────────────────────────────────────────────
        recap_block = ""
        if edition == "am" and yesterday_recap:
            recap_block = "\n\n=== YESTERDAY'S PM STORIES (for recap segment — summarise briefly) ===\n"
            for r in yesterday_recap:
                recap_block += f"  • [{r['category'].upper()}] {r['headline']}\n"

        # ── PM exclusion block ─────────────────────────────────────────────────
        excl_block = ""
        if edition == "pm" and am_exclusions:
            excl_block = "\n\n=== AM STORIES ALREADY COVERED TODAY (DO NOT REPEAT) ===\n"
            for h in am_exclusions:
                excl_block += f"  • {h}\n"

        # ── Raw stories ────────────────────────────────────────────────────────
        raw_sorted = sorted(raw_stories, key=lambda x: -x.get("source_weight", 1))
        stories_text = json.dumps(raw_sorted[:90], indent=2)

        # ── Schema (different for AM vs PM) ───────────────────────────────────
        if edition == "am":
            schema_note = """Return this EXACT JSON structure:
{
  "episode_date": "...",
  "edition": "am",
  "episode_hook": "3-5 word punchy AM hook",
  "show_theme": "One sentence — today's overarching AM narrative",
  "yesterday_recap": [
    {
      "headline": "Original PM headline",
      "one_line_summary": "One sentence update/recap for the AM",
      "category": "business|tech|overlap"
    }
  ],
  "business_stories": [
    {
      "rank": 1,
      "type": "deep|medium",
      "podcast_headline": "Punchy overnight headline",
      "source": "...", "url": "...",
      "context": "3-4 sentences",
      "extrapolation": "2-3 sentences",
      "talking_points": ["4-6 debatable points"],
      "debate_angle": "Core tension",
      "lead_host": "alex",
      "injected": false,
      "estimated_minutes": 4
    }
  ],
  "overlap_stories": [ /* exactly 1 overnight crossover story */ ],
  "tech_stories": [ /* exactly 2 overnight tech stories, same schema */ ],
  "editorial_note": "Optional note to scriptwriter"
}"""
        else:
            schema_note = """Return this EXACT JSON structure:
{
  "episode_date": "...",
  "edition": "pm",
  "episode_hook": "3-5 word punchy PM hook",
  "show_theme": "One sentence — this morning's overarching narrative",
  "business_stories": [
    {
      "rank": 1,
      "type": "quick",
      "podcast_headline": "Punchy morning headline",
      "source": "...", "url": "...",
      "context": "1-2 sentences — just the key fact",
      "talking_points": ["1-2 quick reaction points"],
      "lead_host": "alex",
      "injected": false,
      "estimated_minutes": 1.5
    }
  ],
  "overlap_stories": [ /* exactly 1 quick crossover story, same schema */ ],
  "tech_stories": [ /* exactly 2 quick morning tech stories, same schema */ ],
  "editorial_note": "Optional"
}

IMPORTANT: All stories must be type "quick". No deep dives. Each story ~1.5-2 min.
Total episode target: ~11 minutes (8-15 min acceptable range)."""

        prompt = f"""Date: {episode_date} | Edition: {edition.upper()}

{recent_summary}
{recap_block}
{excl_block}
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
