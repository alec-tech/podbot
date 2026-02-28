"""
orchestrator.py — Multi-Show Podcast Pipeline

Supports multiple shows (e.g., the-signal, the-rough) via --show flag.
Supports partial re-runs via --start-from flag.
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

from agents.show_loader import load_show, ShowConfig
from agents.curator import CuratorAgent
from agents.scriptwriter import ScriptwriterAgent
from agents.voice_producer import VoiceProducerAgent
from agents.publisher import PublisherAgent
from agents.publisher_website import generate_episode_json, update_episodes_json, generate_rss_feed
from agents.story_memory import record_covered_stories, get_callback_opportunities
from agents.inject_stories import get_pending_injections

log = logging.getLogger("orchestrator")

STAGES = ["curate", "script", "audio", "publish"]


def _setup_logging(show: ShowConfig, edition: str, episode_date: str):
    log_dir = show.log_dir()
    log_path = log_dir / f"episode_{episode_date}_{edition}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_path),
            logging.StreamHandler(),
        ],
        force=True,
    )


def load_active_sponsors(show: ShowConfig, edition: str, episode_date: str) -> list:
    """Load sponsors that are active for this show/edition/date."""
    today = episode_date
    return [
        s for s in show.sponsors
        if s.get("active", True)
        and edition in s.get("editions", [])
        and s.get("start_date", "2000-01-01") <= today
        and s.get("end_date", "2099-12-31") >= today
    ]


def run_pipeline(
    show: ShowConfig,
    edition: str = None,
    start_from: str = "curate",
    dry_run: bool = False,
    skip_audio: bool = False,
    episode_date: str = None,
    force_episode_num: int = None,
):
    """
    Run one complete episode pipeline for the given show and edition.
    Supports resuming from any stage via start_from.
    """
    edition = _resolve_edition(edition, show)
    now_est = datetime.now(EST)
    episode_date = episode_date or now_est.strftime("%Y-%m-%d")
    edition_label = edition.capitalize()

    _setup_logging(show, edition, episode_date)

    episode_num = force_episode_num or _get_episode_number(show)
    start_time = time.time()

    # Handle deprecated --skip-audio
    if skip_audio and start_from == "curate":
        start_from = "publish"

    start_idx = STAGES.index(start_from) if start_from in STAGES else 0

    log.info(
        f"{'🧪 DRY RUN — ' if dry_run else ''}"
        f"🎙️  {show.name} | Episode {episode_num} | {episode_date} {edition_label}"
        f"{f' | Resuming from {start_from}' if start_idx > 0 else ''}"
    )

    # ── Output paths ──────────────────────────────────────────────────────────
    brief_path = str(show.output_dir("briefs") / f"brief_{episode_date}_{edition}.json")
    script_path = str(show.output_dir("scripts") / f"script_{episode_date}_{edition}.txt")
    script_meta_path = str(show.output_dir("scripts") / f"script_{episode_date}_{edition}.json")
    audio_path = str(show.output_dir("audio") / f"episode_{episode_date}_{edition}.mp3")

    brief = None
    script = None

    # ── Load prior artifacts if resuming ──────────────────────────────────────
    if start_idx >= 1:  # script or later — need brief
        brief = _load_json(brief_path)
        if not brief:
            raise FileNotFoundError(f"Cannot resume from {start_from}: no brief at {brief_path}")
        log.info(f"  Loaded existing brief: {brief_path}")

    if start_idx >= 2:  # audio or later — need script
        script = _load_json(script_meta_path)
        if not script:
            # Try loading just the text
            script_text = _load_text(script_path)
            if script_text:
                script = {"full_script": script_text, "estimated_minutes": 12, "edition": edition}
            else:
                raise FileNotFoundError(f"Cannot resume from {start_from}: no script at {script_path}")
        log.info(f"  Loaded existing script: {script_path}")

    if start_idx >= 3:  # publish — need audio
        if not Path(audio_path).exists():
            raise FileNotFoundError(f"Cannot resume from {start_from}: no audio at {audio_path}")
        log.info(f"  Loaded existing audio: {audio_path}")

    # ── Pending injections ────────────────────────────────────────────────────
    if start_idx == 0:
        pending = get_pending_injections(episode_date, edition, show_slug=show.slug)
        if pending:
            must = [i for i in pending if i["priority"] == "must_include"]
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
    if start_idx <= 0:
        log.info(f"\n📰 STAGE 1: Curating {edition_label} stories...")
        curator = CuratorAgent(show)
        try:
            brief = curator.run(episode_date, edition)
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
            brief = _load_fallback_brief(show, episode_date, edition)
            if not brief:
                _send_alert(show, f"CRITICAL: {edition_label} curation failed, no fallback: {e}")
                raise

        callbacks = get_callback_opportunities(brief, show)
        if callbacks:
            brief["callback_opportunities"] = callbacks
            log.info(f"  🔗 {len(callbacks)} callback opportunity/ies")

        # Sponsor injection
        sponsors = load_active_sponsors(show, edition, episode_date)
        if sponsors:
            brief["sponsors"] = sponsors
            log.info(f"  💰 {len(sponsors)} active sponsor(s) loaded")
        else:
            log.info(f"  📢 No active sponsors — using placeholders")

    if dry_run:
        log.info(f"\n🧪 DRY RUN complete. Brief → {brief_path}")
        return {"status": "dry_run", "brief": brief, "edition": edition, "show": show.slug}

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: SCRIPT
    # ═══════════════════════════════════════════════════════════════════════════
    if start_idx <= 1:
        pipeline = show.pipeline_config
        script_target = pipeline.get("target_duration_minutes", 12)
        script_min = pipeline.get("min_duration_minutes", 10)
        script_max = pipeline.get("max_duration_minutes", 15)

        log.info(f"\n✍️  STAGE 2: Writing {script_target}-min {edition_label} script...")
        writer = ScriptwriterAgent(show)
        try:
            script = writer.run(brief, episode_num, episode_date, edition)
            _save_text(script["full_script"], script_path)
            _save_json(script, script_meta_path)
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
            _send_alert(show, f"Script failed — {edition_label} Ep {episode_num}: {e}")
            raise

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: AUDIO
    # ═══════════════════════════════════════════════════════════════════════════
    if start_idx <= 2:
        if skip_audio:
            if not Path(audio_path).exists():
                raise FileNotFoundError(f"--skip-audio set but no file at {audio_path}")
            log.info(f"\n🎧 STAGE 3: Skipped — using existing {audio_path}")
        else:
            log.info(f"\n🎧 STAGE 3: Producing audio...")
            producer = VoiceProducerAgent(show)
            pipeline = show.pipeline_config
            audio_min_dur = pipeline.get("audio_min_duration_minutes", 7)
            audio_max_dur = pipeline.get("audio_max_duration_minutes", 18)
            try:
                audio_path = producer.run(script, episode_date, edition)
                dur_min = producer.get_duration(audio_path) / 60
                log.info(f"  ✅ Audio: {audio_path} ({dur_min:.1f} min)")
                if dur_min < audio_min_dur:
                    _send_alert(show, f"{edition_label} Ep {episode_num} audio too short ({dur_min:.1f} min)")
                    raise ValueError("Audio too short")
                elif dur_min > audio_max_dur:
                    log.warning(f"  ⚠️  Slightly long ({dur_min:.1f} min) — publishing anyway")
            except Exception as e:
                log.error(f"  ❌ Audio failed: {e}")
                _send_alert(show, f"Audio failed — {edition_label} Ep {episode_num}: {e}")
                raise

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 4: PUBLISH + WEBSITE
    # ═══════════════════════════════════════════════════════════════════════════
    if start_idx <= 3:
        log.info(f"\n🚀 STAGE 4: Publishing {edition_label}...")
        publisher = PublisherAgent(show)
        episode_url = None
        try:
            metadata = publisher.generate_metadata(
                brief, script, episode_num, episode_date,
                edition=edition,
            )
            episode_title = metadata.get("TITLE", show.name)
            episode_url = publisher.upload(audio_path, metadata)
            log.info(f"  ✅ Live : {episode_url}")
            log.info(f"  🏷️  Title: {episode_title}")

            ep_json = generate_episode_json(
                brief, script, metadata, episode_url,
                episode_num, episode_date, edition=edition, show=show,
            )
            json_path = update_episodes_json(ep_json, show=show)
            log.info(f"  ✅ Website data: {json_path}")

            with open(str(json_path)) as f:
                all_episodes = json.load(f)
            generate_rss_feed(all_episodes, show=show)
            log.info("  ✅ RSS updated")

            publisher.post_social(metadata, episode_url, edition=edition)

        except Exception as e:
            log.error(f"  ❌ Publishing failed: {e}")
            _save_json(
                {"brief": brief, "audio_path": audio_path, "edition": edition},
                str(show.output_dir() / f"emergency_backup_{episode_date}_{edition}.json"),
            )
            _send_alert(show, f"Publishing failed — {edition_label} Ep {episode_num}: {e}")

        # Story memory
        record_covered_stories(brief, episode_num, episode_date, edition, show=show)
        log.info("  ✅ Story memory updated")

    elapsed = (time.time() - start_time) / 60
    log.info(f"\n🏁 Done in {elapsed:.1f} min")
    return {"status": "success", "show": show.slug, "edition": edition,
            "episode_num": episode_num, "url": episode_url if start_idx <= 3 else None}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_edition(edition, show: ShowConfig):
    valid = show.valid_editions
    if edition and edition.lower() in valid:
        return edition.lower()
    env = os.getenv("EPISODE_EDITION", "").lower()
    if env in valid:
        return env
    # Auto-detect based on clock (only works for time-based shows)
    if len(valid) == 1:
        return valid[0]
    hour = datetime.now(EST).hour
    if hour < 10:
        return valid[0]
    elif hour < 16:
        return valid[1] if len(valid) > 1 else valid[0]
    else:
        return valid[-1]


def _get_episode_number(show: ShowConfig):
    db_path = show.database_dir() / "episodes.db"
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


def _load_json(path):
    p = Path(path)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


def _load_text(path):
    p = Path(path)
    if p.exists():
        return p.read_text()
    return None


def _load_fallback_brief(show: ShowConfig, episode_date, edition):
    briefs_dir = show.output_dir("briefs")
    for p in [
        briefs_dir / f"brief_{episode_date}_{edition}.json",
        *sorted(briefs_dir.glob(f"brief_*_{edition}.json"), reverse=True),
        *sorted(briefs_dir.glob("brief_*.json"), reverse=True),
    ]:
        if p.exists():
            with open(p) as f:
                brief = json.load(f)
            log.warning(f"  ⚠️  Fallback brief: {p.name}")
            return brief
    return None


def _send_alert(show: ShowConfig, message):
    webhook = os.getenv("SLACK_WEBHOOK_URL")
    if webhook:
        try:
            import requests as req
            req.post(webhook, json={"text": f"🚨 {show.name}:\n{message}"}, timeout=5)
        except Exception:
            pass
    log.error(f"ALERT: {message}")


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Run podcast episode pipeline")
    p.add_argument("--show", default="the-signal",
                   help="Show slug (default: the-signal)")
    p.add_argument("--edition",
                   help="Edition to produce (default: auto-detect from clock)")
    p.add_argument("--start-from", choices=STAGES, default="curate",
                   help="Resume pipeline from this stage (default: curate = full run)")
    p.add_argument("--dry-run", action="store_true",
                   help="Curate + brief only — no audio, no publish")
    p.add_argument("--skip-audio", action="store_true",
                   help="Skip TTS, use existing audio file (deprecated: use --start-from publish)")
    p.add_argument("--date", default=None,
                   help="Override date YYYY-MM-DD (default: today EST)")
    p.add_argument("--episode-num", type=int, default=None,
                   help="Override episode number")
    args = p.parse_args()

    show = load_show(args.show)

    run_pipeline(
        show=show,
        edition=args.edition,
        start_from=args.start_from,
        dry_run=args.dry_run or os.getenv("DRY_RUN", "").lower() in ("true", "1"),
        skip_audio=args.skip_audio,
        episode_date=args.date,
        force_episode_num=args.episode_num,
    )
