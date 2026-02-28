"""
agents/story_memory.py v5 — Multi-Show Edition-Aware Story Coverage Memory

Per-show database paths: database/{slug}/story_memory.db
Dynamic edition order from ShowConfig.
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


def _get_db_path(show=None) -> Path:
    if show:
        db_dir = show.database_dir()
    else:
        db_dir = Path("database")
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "story_memory.db"


def init_db(show=None):
    db_path = _get_db_path(show)
    conn = sqlite3.connect(db_path)
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
    cols = [r[1] for r in conn.execute("PRAGMA table_info(covered_stories)").fetchall()]
    if "edition" not in cols:
        conn.execute("ALTER TABLE covered_stories ADD COLUMN edition TEXT DEFAULT 'unknown'")
    conn.commit()
    conn.close()


# ─── Write ────────────────────────────────────────────────────────────────────

def record_covered_stories(brief: dict, episode_num: int, episode_date: str,
                           edition: str, show=None):
    """Persist all curated stories for this edition to the memory DB."""
    init_db(show)
    db_path = _get_db_path(show)
    conn = sqlite3.connect(db_path)

    # Collect stories from all configured categories
    all_stories = []
    if show:
        for cat_key in show.story_quotas.keys():
            cat_label = cat_key.replace("_stories", "")
            for s in brief.get(cat_key, []):
                all_stories.append((s, cat_label))
    else:
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

def get_recently_covered(days: int = 5, edition: str = None, show=None) -> list:
    """Stories from the last N days, optionally filtered by edition."""
    init_db(show)
    db_path = _get_db_path(show)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = sqlite3.connect(db_path)
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


def get_earlier_edition_headlines(episode_date: str, current_edition: str, show=None) -> list:
    """
    Return headlines from earlier editions on the same day.
    Edition order is read from show config (dynamic per show).
    """
    init_db(show)
    db_path = _get_db_path(show)

    if show:
        edition_order = show.edition_order
    else:
        edition_order = ["morning", "midday", "evening"]

    current_idx = edition_order.index(current_edition.lower()) if current_edition.lower() in edition_order else 0
    earlier_editions = edition_order[:current_idx]

    if not earlier_editions:
        return []

    conn = sqlite3.connect(db_path)
    placeholders = ",".join("?" for _ in earlier_editions)
    rows = conn.execute(
        f"""SELECT headline, edition FROM covered_stories
           WHERE episode_date = ? AND edition IN ({placeholders})
           ORDER BY id DESC""",
        (episode_date, *earlier_editions),
    ).fetchall()
    conn.close()
    return [{"headline": r[0], "edition": r[1]} for r in rows]


def build_recently_covered_summary(days: int = 3, show=None) -> str:
    """Formatted string for the curator prompt (all editions combined)."""
    recent = get_recently_covered(days, show=show)
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
            lines.append(f"    * [{s['category'].upper()}] {s['headline']}{co}")
    return "\n".join(lines)


def get_callback_opportunities(brief: dict, show=None) -> list:
    """Find connections between today's stories and past coverage."""
    init_db(show)
    recent = get_recently_covered(days=7, show=show)
    if not recent:
        return []

    all_current = []
    if show:
        for cat_key in show.story_quotas.keys():
            all_current.extend(brief.get(cat_key, []))
    else:
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
