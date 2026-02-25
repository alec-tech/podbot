"""
orchestrator.py v4 — The Signal
Three editions per day:
  Morning (7:00 AM EST): Overnight + early morning news   — "{date} Morning - {hook}"
  Midday  (1:00 PM EST): Morning-to-noon fresh news       — "{date} Midday - {hook}"
  Evening (5:30 PM EST): Afternoon developments            — "{date} Evening - {hook}"
"""

import os
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

EST = ZoneInfo("America/New_York")
Path("logs").mkdir(exist_ok=True)

VALID_EDITIONS = ("morning", "midday", "evening")


def _setup_logging(edition: str, episode_date: str):
    log_path = f"logs/episode_{episode_date}_{edition}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(),
        ],
        force=True,
    )


log = logging.getLogger("orchestrator")

from agents.curator import CuratorAgent
from agents.scriptwriter import ScriptwriterAgent
from agents.voice_producer import VoiceProducerAgent
from agents.publisher import PublisherAgent
from agents.publisher_website import generate_episode_json, update_episodes_json, generate_rss_feed
from agents.story_memory import record_covered_stories, get_callback_opportunities
from agents.inject_stories import get_pending_injections


def load_active_sponsors(edition: str, episode_date: str) -> list:
    """Load sponsors from data/sponsors.json that are active for this edition+date."""
    path = Path("data/sponsors.json")
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    today = episode_date  # "YYYY-MM-DD"
    return [
        s for s in data.get("sponsors", [])
        if s.get("active", True)
        and edition in s.get("editions", [])
        and s.get("start_date", "2000-01-01") <= today
        and s.get("end_date", "2099-12-31") >= today
    ]


def run_pipeline(
    edition: str = None,
    dry_run: bool = False,
    skip_audio: bool = False,
    episode_date: str = None,
    force_episode_num: int = None,
):
    """
    Run one complete episode pipeline for the given edition.

    Edition behaviour
    ─────────────────
    Morning (7:00 AM EST)
      • News window  : previous 6:00 PM EST → today 7:00 AM EST  (~14 hrs)
      • Title        : {date} Morning - {three-to-five word hook}

    Midday (1:00 PM EST)
      • News window  : today 7:00 AM EST → today 1:00 PM EST     (~7 hrs)
      • Title        : {date} Midday - {three-to-five word hook}

    Evening (5:30 PM EST)
      • News window  : today 1:00 PM EST → today 5:30 PM EST     (~5 hrs)
      • Title        : {date} Evening - {three-to-five word hook}

    All editions: 10-15 min target (12 min ideal, ~1680 words at 140 wpm).
    Soft dedup: earlier same-day stories can be revisited with UPDATE framing.
    """
    edition = _resolve_edition(edition)
    now_est = datetime.now(EST)
    episode_date = episode_date or now_est.strftime("%Y-%m-%d")
    edition_label = edition.capitalize()

    _setup_logging(edition, episode_date)

    episode_num = force_episode_num or _get_episode_number()
    start_time = time.time()

    log.info(
        f"{'🧪 DRY RUN — ' if dry_run else ''}🎙️  "
        f"Episode {episode_num} | {episode_date} {edition_label}"
    )

    # ── Pending injections for this edition ──────────────────────────────────
    pending = get_pending_injections(episode_date, edition)
    if pending:
        must    = [i for i in pending if i["priority"] == "must_include"]
        consider = [i for i in pending if i["priority"] == "consider"]
        log.info(
            f"📌 Injections: {len(must)} MUST_INCLUDE, {len(consider)} CONSIDER, "
            f"{len(pending)-len(must)-len(consider)} BACKGROUND"
        )
        for i in must:
            log.info(f"   🔴 MUST: {i['story']['headline']}")
    else:
        log.info(f"  No injections queued — fully autonomous {edition_label}")

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1: CURATION
    # ═══════════════════════════════════════════════════════════════════════════
    log.info(f"\n📰 STAGE 1: Curating {edition_label} stories...")
    curator = CuratorAgent()
    try:
        brief = curator.run(episode_date, edition)
        brief_path = f"outputs/briefs/brief_{episode_date}_{edition}.json"
        _save_json(brief, brief_path)

        b = len(brief.get("business_stories", []))
        t = len(brief.get("tech_stories", []))
        o = len(brief.get("overlap_stories", []))
        log.info(f"  ✅ Brief: {b} business + {t} tech + {o} overlap")
        log.info(f"  📖 Theme : {brief.get('show_theme', 'N/A')}")
        log.info(f"  🏷️  Hook  : {brief.get('episode_hook', 'N/A')}")
        if brief.get("editorial_note"):
            log.info(f"  📝 Note  : {brief['editorial_note']}")
    except Exception as e:
        log.error(f"  ❌ Curation failed: {e}")
        brief = _load_fallback_brief(episode_date, edition)
        if not brief:
            _send_alert(f"CRITICAL: {edition_label} curation failed, no fallback: {e}")
            raise

    callbacks = get_callback_opportunities(brief)
    if callbacks:
        brief["callback_opportunities"] = callbacks
        log.info(f"  🔗 {len(callbacks)} callback opportunity/ies")

    # ── Sponsor injection ──────────────────────────────────────────────────
    sponsors = load_active_sponsors(edition, episode_date)
    if sponsors:
        brief["sponsors"] = sponsors
        log.info(f"  💰 {len(sponsors)} active sponsor(s) loaded")
    else:
        log.info(f"  📢 No active sponsors — using placeholders")

    if dry_run:
        log.info(f"\n🧪 DRY RUN complete. Brief → {brief_path}")
        return {"status": "dry_run", "brief": brief, "edition": edition}

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: SCRIPT
    # ═══════════════════════════════════════════════════════════════════════════
    script_target, script_min, script_max = 12, 10, 15

    log.info(f"\n✍️  STAGE 2: Writing {script_target}-min {edition_label} script...")
    writer = ScriptwriterAgent()
    try:
        script = writer.run(brief, episode_num, episode_date, edition)
        script_path = f"outputs/scripts/script_{episode_date}_{edition}.txt"
        _save_text(script["full_script"], script_path)
        est = script.get("estimated_minutes", 0)
        log.info(f"  ✅ Script: {est:.1f} min estimated")
        if est < script_min:
            log.warning(f"  ⚠️  {script_min - est:.1f} min short of target")
        elif est > script_max:
            log.warning(f"  ⚠️  {est - script_target:.1f} min over target")
        else:
            log.info(f"  ✅ Duration QA passed")
    except Exception as e:
        log.error(f"  ❌ Script failed: {e}")
        _send_alert(f"Script failed — {edition_label} Ep {episode_num}: {e}")
        raise

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: AUDIO
    # ═══════════════════════════════════════════════════════════════════════════
    audio_path = f"outputs/audio/episode_{episode_date}_{edition}.mp3"

    if skip_audio:
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"--skip-audio set but no file at {audio_path}")
        log.info(f"\n🎧 STAGE 3: Skipped — using existing {audio_path}")
    else:
        log.info(f"\n🎧 STAGE 3: Producing audio...")
        producer = VoiceProducerAgent()
        audio_min_dur = 7
        audio_max_dur = 18
        try:
            audio_path = producer.run(script, episode_date, edition)
            dur_min = producer.get_duration(audio_path) / 60
            log.info(f"  ✅ Audio: {audio_path} ({dur_min:.1f} min)")
            if dur_min < audio_min_dur:
                _send_alert(f"{edition_label} Ep {episode_num} audio too short ({dur_min:.1f} min)")
                raise ValueError("Audio too short")
            elif dur_min > audio_max_dur:
                log.warning(f"  ⚠️  Slightly long ({dur_min:.1f} min) — publishing anyway")
        except Exception as e:
            log.error(f"  ❌ Audio failed: {e}")
            _send_alert(f"Audio failed — {edition_label} Ep {episode_num}: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 4: PUBLISH + WEBSITE
    # ═══════════════════════════════════════════════════════════════════════════
    log.info(f"\n🚀 STAGE 4: Publishing {edition_label}...")
    publisher = PublisherAgent()
    episode_url = None
    try:
        hook = brief.get("episode_hook", "Today in Business and Tech")
        episode_title = f"{episode_date} {edition_label} - {hook}"

        metadata = publisher.generate_metadata(
            brief, script, episode_num, episode_date,
            edition=edition, episode_title=episode_title,
        )
        episode_url = publisher.upload(audio_path, metadata)
        log.info(f"  ✅ Live : {episode_url}")
        log.info(f"  🏷️  Title: {episode_title}")

        ep_json = generate_episode_json(
            brief, script, metadata, episode_url,
            episode_num, episode_date, edition=edition,
        )
        json_path = update_episodes_json(ep_json)
        log.info(f"  ✅ Website data: {json_path}")

        with open(str(json_path)) as f:
            all_episodes = json.load(f)
        generate_rss_feed(all_episodes, {
            "name": "The Signal",
            "description": "Three-daily AI-produced business, tech, and policy news.",
            "website_url": os.getenv("PODCAST_WEBSITE_URL", ""),
        })
        log.info("  ✅ RSS updated")

        publisher.post_social(metadata, episode_url, edition=edition)

    except Exception as e:
        log.error(f"  ❌ Publishing failed: {e}")
        _save_json(
            {"brief": brief, "audio_path": audio_path, "edition": edition},
            f"outputs/emergency_backup_{episode_date}_{edition}.json",
        )
        _send_alert(f"Publishing failed — {edition_label} Ep {episode_num}: {e}")

    # ── Story memory ──────────────────────────────────────────────────────────
    record_covered_stories(brief, episode_num, episode_date, edition)
    log.info("  ✅ Story memory updated")

    elapsed = (time.time() - start_time) / 60
    log.info(f"\n🏁 Done in {elapsed:.1f} min")
    return {"status": "success", "edition": edition, "episode_num": episode_num, "url": episode_url}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_edition(edition):
    if edition and edition.lower() in VALID_EDITIONS:
        return edition.lower()
    env = os.getenv("EPISODE_EDITION", "").lower()
    if env in VALID_EDITIONS:
        return env
    hour = datetime.now(EST).hour
    if hour < 10:
        return "morning"
    elif hour < 16:
        return "midday"
    else:
        return "evening"


def _get_episode_number():
    db_path = Path("database/episodes.db")
    if not db_path.exists():
        return 1
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] + 1
    except Exception:
        return 1
    finally:
        conn.close()


def _save_json(data, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _save_text(text, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def _load_fallback_brief(episode_date, edition):
    for p in [
        Path(f"outputs/briefs/brief_{episode_date}_{edition}.json"),
        *sorted(Path("outputs/briefs").glob(f"brief_*_{edition}.json"), reverse=True),
        *sorted(Path("outputs/briefs").glob("brief_*.json"), reverse=True),
    ]:
        if p.exists():
            with open(p) as f:
                brief = json.load(f)
            log.warning(f"  ⚠️  Fallback brief: {p.name}")
            return brief
    return None


def _send_alert(message):
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if webhook:
        try:
            import requests as req
            req.post(webhook, json={"text": f"🚨 The Signal:\n{message}"}, timeout=5)
        except Exception:
            pass
    log.error(f"ALERT: {message}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run The Signal episode pipeline")
    p.add_argument("--edition", choices=["morning", "midday", "evening"],
                   help="Edition to produce (default: auto-detect from clock)")
    p.add_argument("--dry-run", action="store_true",
                   help="Curate + brief only — no audio, no publish")
    p.add_argument("--skip-audio", action="store_true",
                   help="Skip TTS, use existing audio file")
    p.add_argument("--date", default=None,
                   help="Override date YYYY-MM-DD (default: today EST)")
    p.add_argument("--episode-num", type=int, default=None,
                   help="Override episode number")
    args = p.parse_args()

    run_pipeline(
        edition=args.edition,
        dry_run=args.dry_run or os.getenv("DRY_RUN", "").lower() in ("true", "1"),
        skip_audio=args.skip_audio,
        episode_date=args.date,
        force_episode_num=args.episode_num,
    )
