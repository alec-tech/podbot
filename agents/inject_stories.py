"""
agents/inject_stories.py v5 — Multi-Show Edition-Aware Story Injection

Per-show injection data: data/{slug}/injected_stories.json
"""

import os
import json
import logging
import requests
from pathlib import Path
from datetime import datetime, date, timedelta
from anthropic import Anthropic
from typing import Optional

log = logging.getLogger("inject_stories")
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PRIORITY_LEVELS = {"must_include", "consider", "background"}
EDITION_VALUES = {"morning", "midday", "evening", "daily", "all"}


def _injections_file(show_slug: str = "the-signal") -> Path:
    return Path("data") / show_slug / "injected_stories.json"


def _archive_dir(show_slug: str = "the-signal") -> Path:
    return Path("data") / show_slug / "injection_archive"


# ─── Public API ───────────────────────────────────────────────────────────────

def inject_from_url(url: str, priority: str = "consider", note: str = "",
                    submitted_by: str = "producer", edition: str = "all",
                    show_slug: str = "the-signal") -> dict:
    priority = _validate_priority(priority)
    edition  = _validate_edition(edition)
    raw      = _fetch_url_content(url)
    enriched = _enrich_story(raw, url=url, note=note)
    record   = _build_record(enriched, priority, submitted_by, edition, source_url=url, note=note)
    _save_injection(record, show_slug)
    log.info(f"Injected URL [{priority.upper()} / {edition.upper()}]: {enriched['headline']}")
    return record


def inject_from_text(text: str, priority: str = "consider", note: str = "",
                     submitted_by: str = "producer", edition: str = "all",
                     show_slug: str = "the-signal") -> dict:
    priority = _validate_priority(priority)
    edition  = _validate_edition(edition)
    enriched = _enrich_story(text, url="", note=note)
    record   = _build_record(enriched, priority, submitted_by, edition, note=note)
    _save_injection(record, show_slug)
    log.info(f"Injected text [{priority.upper()} / {edition.upper()}]: {enriched['headline']}")
    return record


def inject_from_topic(topic: str, priority: str = "consider", note: str = "",
                      submitted_by: str = "producer", edition: str = "all",
                      show_slug: str = "the-signal") -> dict:
    priority = _validate_priority(priority)
    edition  = _validate_edition(edition)
    enriched = _research_topic(topic, note)
    record   = _build_record(enriched, priority, submitted_by, edition, note=note)
    _save_injection(record, show_slug)
    log.info(f"Injected topic [{priority.upper()} / {edition.upper()}]: {enriched['headline']}")
    return record


def get_pending_injections(episode_date: str, edition: str = "all",
                           show_slug: str = "the-signal") -> list:
    """Return injections relevant to this date + edition."""
    _archive_old_injections(show_slug)
    inj_file = _injections_file(show_slug)
    if not inj_file.exists():
        return []
    with open(inj_file) as f:
        all_injections = json.load(f)
    edition = edition.lower()
    pending = []
    for inj in all_injections:
        if inj.get("used"):
            continue
        if inj.get("target_date") not in (episode_date, None, ""):
            continue
        inj_ed = inj.get("edition", "all").lower()
        if inj_ed in ("all", "both") or inj_ed == edition:
            pending.append(inj)
    return pending


def mark_injections_used(episode_date: str, edition: str,
                         show_slug: str = "the-signal"):
    """Mark matching injections as consumed by this edition."""
    inj_file = _injections_file(show_slug)
    if not inj_file.exists():
        return
    with open(inj_file) as f:
        all_injections = json.load(f)
    edition = edition.lower()
    for inj in all_injections:
        if inj.get("used"):
            continue
        if inj.get("target_date") not in (episode_date, None, ""):
            continue
        inj_ed = inj.get("edition", "all").lower()
        if inj_ed in ("all", "both") or inj_ed == edition:
            inj["used"]            = True
            inj["used_at"]         = datetime.now().isoformat()
            inj["used_by_edition"] = edition
    with open(inj_file, "w") as f:
        json.dump(all_injections, f, indent=2)


def list_pending_injections(episode_date: str = None, edition: str = "all",
                            show_slug: str = "the-signal"):
    target = episode_date or str(date.today())
    pending = get_pending_injections(target, edition, show_slug)
    if not pending:
        print(f"No pending injections for {target} ({edition.upper()}) [{show_slug}]")
        return
    print(f"\n{'='*60}")
    print(f"  Pending — {target} | {edition.upper()} | {show_slug}")
    print(f"{'='*60}")
    for i, inj in enumerate(pending, 1):
        s = inj["story"]
        print(f"\n  [{i}] {inj['priority'].upper()} | {inj.get('edition','all').upper()}")
        print(f"  Headline : {s['headline']}")
        if inj.get("note"): print(f"  Note     : {inj['note']}")
        print(f"  By       : {inj['submitted_by']} @ {inj['submitted_at'][:16]}")
    print(f"\n{'='*60}\n")


# ─── Enrichment ───────────────────────────────────────────────────────────────

def _fetch_url_content(url: str) -> str:
    try:
        resp = requests.get(url, timeout=15,
                            headers={"User-Agent": "Mozilla/5.0 (TheSignalBot/3.0)"})
        from html.parser import HTMLParser
        class _Strip(HTMLParser):
            def __init__(self): super().__init__(); self.text = []
            def handle_data(self, d): self.text.append(d)
        p = _Strip(); p.feed(resp.text)
        return " ".join(p.text)[:4000]
    except Exception as e:
        return f"Could not fetch {url}: {e}"


def _enrich_story(raw_content: str, url: str = "", note: str = "") -> dict:
    prompt = f"""You are an editorial producer for a podcast.
Analyze and create a structured podcast brief.

Content:
{raw_content[:3000]}
URL: {url}
Note: {note}

Return JSON:
{{
  "headline": "Punchy 8-12 word podcast headline",
  "category": "business|tech|overlap",
  "summary": "2-3 sentence plain-English summary",
  "context": "3-4 sentences background and stakes",
  "extrapolation": "2-3 sentences on what happens next",
  "talking_points": ["4-6 specific debatable points"],
  "debate_angle": "Core business vs tech tension",
  "companies_mentioned": ["Companies"],
  "data_points": ["Key numbers / dates"]
}}"""
    r = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1200,
                                messages=[{"role": "user", "content": prompt}])
    text = r.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].split("```")[0]
        if text.startswith("json"): text = text[4:]
    return json.loads(text.strip())


def _research_topic(topic: str, note: str = "") -> dict:
    prompt = f"""You are an editorial producer for a podcast.
Build a story brief from your knowledge of this topic: "{topic}"
Note: {note}

Return JSON:
{{
  "headline": "Punchy 8-12 word podcast headline",
  "category": "business|tech|overlap",
  "summary": "2-3 sentence summary",
  "context": "3-4 sentences background",
  "extrapolation": "2-3 sentences what happens next",
  "talking_points": ["4-6 debatable points"],
  "debate_angle": "Core tension",
  "companies_mentioned": ["Relevant companies"],
  "data_points": ["Key facts / numbers"]
}}"""
    r = client.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1200,
                                messages=[{"role": "user", "content": prompt}])
    text = r.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].split("```")[0]
        if text.startswith("json"): text = text[4:]
    return json.loads(text.strip())


# ─── Storage helpers ──────────────────────────────────────────────────────────

def _build_record(enriched: dict, priority: str, submitted_by: str, edition: str,
                  source_url: str = "", note: str = "") -> dict:
    return {
        "id":              f"inj_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "submitted_at":    datetime.now().isoformat(),
        "submitted_by":    submitted_by,
        "priority":        priority,
        "edition":         edition,
        "target_date":     str(date.today()),
        "note":            note,
        "source_url":      source_url,
        "story":           enriched,
        "used":            False,
        "used_at":         None,
        "used_by_edition": None,
    }


def _save_injection(record: dict, show_slug: str = "the-signal"):
    inj_file = _injections_file(show_slug)
    inj_file.parent.mkdir(parents=True, exist_ok=True)
    injections = []
    if inj_file.exists():
        with open(inj_file) as f:
            injections = json.load(f)
    injections.append(record)
    with open(inj_file, "w") as f:
        json.dump(injections, f, indent=2)
    if record["priority"] == "must_include":
        _send_must_include_alert(record)


def _archive_old_injections(show_slug: str = "the-signal"):
    inj_file = _injections_file(show_slug)
    if not inj_file.exists():
        return
    with open(inj_file) as f:
        injections = json.load(f)
    cutoff = (date.today() - timedelta(days=14)).isoformat()
    current, archive = [], []
    for inj in injections:
        (archive if (inj.get("target_date") or "") < cutoff else current).append(inj)
    if archive:
        archive_dir = _archive_dir(show_slug)
        archive_dir.mkdir(parents=True, exist_ok=True)
        with open(archive_dir / f"archive_{date.today()}.json", "w") as f:
            json.dump(archive, f, indent=2)
        with open(inj_file, "w") as f:
            json.dump(current, f, indent=2)


def _send_must_include_alert(record: dict):
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    try:
        headline = record["story"].get("headline", "Unknown")
        edition  = record.get("edition", "all").upper()
        note     = record.get("note", "")
        msg = (f"*MUST INCLUDE* — {edition} edition\n*{headline}*\n"
               f"By: {record['submitted_by']}"
               + (f"\nNote: {note}" if note else ""))
        requests.post(webhook, json={"text": msg}, timeout=5)
    except Exception:
        pass


def _validate_priority(p: str) -> str:
    p = p.lower().replace("-", "_")
    if p not in PRIORITY_LEVELS:
        raise ValueError(f"Priority must be one of {PRIORITY_LEVELS}")
    return p


def _validate_edition(e: str) -> str:
    e = e.lower()
    if e not in EDITION_VALUES:
        raise ValueError(f"Edition must be one of {EDITION_VALUES}")
    return e


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    from dotenv import load_dotenv
    load_dotenv()

    p = argparse.ArgumentParser(description="Inject a story into a podcast show")
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--url",   help="Inject from a URL")
    grp.add_argument("--text",  help="Inject from raw text")
    grp.add_argument("--topic", help="Inject by topic (AI researches)")
    grp.add_argument("--list",  action="store_true", help="List pending injections")

    p.add_argument("--show", default="the-signal",
                   help="Show slug (default: the-signal)")
    p.add_argument("--priority", default="consider",
                   choices=["must_include", "consider", "background"])
    p.add_argument("--edition", default="all",
                   choices=["morning", "midday", "evening", "daily", "all"],
                   help="Which edition to target (default: all)")
    p.add_argument("--note", default="")
    p.add_argument("--by",   default="producer")
    p.add_argument("--date", default=None, help="Target date YYYY-MM-DD")

    args = p.parse_args()

    if args.list:
        list_pending_injections(args.date, args.edition, args.show)
    elif args.url:
        r = inject_from_url(args.url, args.priority, args.note, args.by, args.edition, args.show)
        print(f"[{args.priority.upper()} / {args.edition.upper()}]: {r['story']['headline']}")
    elif args.text:
        r = inject_from_text(args.text, args.priority, args.note, args.by, args.edition, args.show)
        print(f"[{args.priority.upper()} / {args.edition.upper()}]: {r['story']['headline']}")
    elif args.topic:
        r = inject_from_topic(args.topic, args.priority, args.note, args.by, args.edition, args.show)
        print(f"[{args.priority.upper()} / {args.edition.upper()}]: {r['story']['headline']}")
    else:
        p.print_help()
