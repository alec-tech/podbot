"""
agents/story_memory.py v3 — Edition-Aware Story Coverage Memory

Tracks stories by edition (am/pm) so:
  • PM curator excludes what AM already covered today
  • AM curator pulls yesterday's PM stories for the recap segment
  • 3-day cooldown applies across both editions combined
"""

import os
import json
import sqlite3
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from anthropic import Anthropic

log = logging.getLogger("story_memory")
DB_PATH = Path("database/story_memory.db")


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS covered_stories (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            episode_num       INTEGER,
            episode_date      TEXT,
            edition           TEXT,
            headline          TEXT,
            category          TEXT,
            topic_fingerprint TEXT,
            companies         TEXT,
            covered_at        TEXT
        )
    """)
    # Migrate old DBs that lack the edition column
    cols = [r[1] for r in conn.execute("PRAGMA table_info(covered_stories)").fetchall()]
    if "edition" not in cols:
        conn.execute("ALTER TABLE covered_stories ADD COLUMN edition TEXT DEFAULT 'unknown'")
    conn.commit()
    conn.close()


# ─── Write ────────────────────────────────────────────────────────────────────

def record_covered_stories(brief: dict, episode_num: int, episode_date: str, edition: str):
    """Persist all curated stories for this edition to the memory DB."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    all_stories = (
        [(s, "business") for s in brief.get("business_stories", [])]
        + [(s, "tech")    for s in brief.get("tech_stories", [])]
        + [(s, "overlap") for s in brief.get("overlap_stories", [])]
    )
    for story, category in all_stories:
        headline    = story.get("podcast_headline", story.get("headline", ""))
        companies   = json.dumps(story.get("companies_mentioned", []))
        fingerprint = _extract_keywords(headline)
        conn.execute(
            """INSERT INTO covered_stories
               (episode_num, episode_date, edition, headline, category,
                topic_fingerprint, companies, covered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (episode_num, episode_date, edition.lower(), headline, category,
             fingerprint, companies, datetime.now().isoformat()),
        )
    conn.commit()
    conn.close()
    log.info(f"  Recorded {len(all_stories)} stories to memory ({edition.upper()})")


# ─── Read ─────────────────────────────────────────────────────────────────────

def get_recently_covered(days: int = 5, edition: str = None) -> list:
    """Stories from the last N days, optionally filtered by edition."""
    init_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(DB_PATH)
    if edition:
        rows = conn.execute(
            """SELECT episode_date, edition, headline, category, companies
               FROM covered_stories WHERE covered_at > ? AND edition = ?
               ORDER BY covered_at DESC""",
            (cutoff, edition.lower()),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT episode_date, edition, headline, category, companies
               FROM covered_stories WHERE covered_at > ?
               ORDER BY covered_at DESC""",
            (cutoff,),
        ).fetchall()
    conn.close()
    return [
        {"date": r[0], "edition": r[1], "headline": r[2],
         "category": r[3], "companies": json.loads(r[4])}
        for r in rows
    ]


def get_am_story_headlines(episode_date: str) -> list:
    """
    Return AM headlines already covered today.
    Used by the PM curator to avoid repetition.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT headline FROM covered_stories
           WHERE episode_date = ? AND edition = 'am'
           ORDER BY id DESC""",
        (episode_date,),
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_yesterday_pm_recap(today_date: str) -> list:
    """
    Return yesterday's PM stories for the AM recap segment.
    Returns up to 3, balanced across categories.
    """
    init_db()
    yesterday = (datetime.strptime(today_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """SELECT headline, category, companies FROM covered_stories
           WHERE episode_date = ? AND edition = 'pm'
           ORDER BY id DESC LIMIT 10""",
        (yesterday,),
    ).fetchall()
    conn.close()
    if not rows:
        return []
    results, seen_cats = [], set()
    for row in rows:
        cat = row[1]
        if cat not in seen_cats or len(results) < 2:
            results.append({
                "headline":  row[0],
                "category":  cat,
                "companies": json.loads(row[2]),
            })
            seen_cats.add(cat)
        if len(results) >= 3:
            break
    return results


def build_recently_covered_summary(days: int = 3) -> str:
    """Formatted string for the curator prompt (both editions combined)."""
    recent = get_recently_covered(days)
    if not recent:
        return "No recent episode history available."
    lines = [f"RECENTLY COVERED (last {days} days — avoid repeating these topics):"]
    by_key = {}
    for r in recent:
        key = f"{r['date']} {r['edition'].upper()}"
        by_key.setdefault(key, []).append(r)
    for key, stories in sorted(by_key.items(), reverse=True):
        lines.append(f"\n  {key}:")
        for s in stories:
            co = f" [{', '.join(s['companies'][:3])}]" if s["companies"] else ""
            lines.append(f"    • [{s['category'].upper()}] {s['headline']}{co}")
    return "\n".join(lines)


def get_callback_opportunities(brief: dict) -> list:
    """Find connections between today's stories and past coverage."""
    init_db()
    recent = get_recently_covered(days=7)
    if not recent:
        return []
    all_current = (
        brief.get("business_stories", [])
        + brief.get("tech_stories", [])
        + brief.get("overlap_stories", [])
    )
    current_text = json.dumps([s.get("podcast_headline", "") for s in all_current], indent=2)
    recent_text  = json.dumps([r["headline"] for r in recent[:15]], indent=2)

    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{"role": "user", "content": f"""Find story connections.

TODAY:
{current_text}

RECENT:
{recent_text}

Return JSON array max 3, or []:
[{{"today_story":"...","past_story":"...","connection":"One sentence","days_ago":2}}]"""}],
    )
    try:
        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].split("```")[0].strip()
            if text.startswith("json"): text = text[4:].strip()
        return json.loads(text)
    except Exception:
        return []


def _extract_keywords(text: str) -> str:
    words = re.findall(r"\b[A-Za-z]{4,}\b", text.lower())
    stop  = {"that", "this", "with", "from", "have", "been", "will", "more",
              "also", "after", "their", "what", "about", "which", "when"}
    return " ".join(w for w in words if w not in stop)[:200]
