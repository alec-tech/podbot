"""
admin.py — Local Admin Server for Multi-Show Podcast Pipeline

FastAPI server with:
  - Show config management (CRUD for show.json, personas, feeds, prompts, sponsors)
  - Pipeline trigger + resume from any stage
  - Live log streaming via SSE
  - Story injection
  - Auto git commit + push on config save

Usage:
    python admin.py
    # Server at http://localhost:8000
    # API docs at http://localhost:8000/docs
"""

import os
import json
import logging
import subprocess
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from agents.show_loader import (
    load_show, list_shows, save_show_config, ShowConfig,
    create_show, build_default_config, build_default_personas,
    show_exists, delete_show, validate_slug,
    DEFAULT_CURATOR_PROMPT, DEFAULT_SCRIPTWRITER_PROMPT, DEFAULT_PUBLISHER_PROMPT,
)

log = logging.getLogger("admin")

app = FastAPI(title="Show Admin", version="1.0")

# ─── Run tracking ─────────────────────────────────────────────────────────────

RUNS_DIR = Path("data/admin")
RUNS_DIR.mkdir(parents=True, exist_ok=True)
RUNS_FILE = RUNS_DIR / "runs.json"
RUNS_LOG_DIR = RUNS_DIR / "logs"
RUNS_LOG_DIR.mkdir(exist_ok=True)

_active_runs: dict[str, dict] = {}


def _load_runs() -> list:
    if RUNS_FILE.exists():
        with open(RUNS_FILE) as f:
            return json.load(f)
    return []


def _save_runs(runs: list):
    with open(RUNS_FILE, "w") as f:
        json.dump(runs, f, indent=2)


def _update_run(run_id: str, updates: dict):
    runs = _load_runs()
    for r in runs:
        if r["id"] == run_id:
            r.update(updates)
            break
    _save_runs(runs)


# ─── Pydantic models ─────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    show: str = ""
    edition: str = ""
    start_from: str = "curate"
    dry_run: bool = False
    date: Optional[str] = None


class InjectRequest(BaseModel):
    url: Optional[str] = None
    text: Optional[str] = None
    topic: Optional[str] = None
    priority: str = "consider"
    edition: str = "all"
    note: str = ""


class HostVoiceProvider(BaseModel):
    provider: str  # "openai", "cartesia", "elevenlabs"
    voice_id: str = "alloy"
    instructions: str = ""
    speed: float = 1.0


class HostInput(BaseModel):
    name: str
    key: Optional[str] = None
    role: str = "Host"
    type: str = "static"  # "static" or "rotating"
    personality: str = ""
    speech_patterns: list[str] = []
    avoid: list[str] = []
    topic_keywords: list[str] = []
    voice_providers: list[HostVoiceProvider] = []


class EditionInput(BaseModel):
    name: str
    publish_time_est: str = "06:00"
    target_duration_minutes: int = 12
    min_duration_minutes: int = 10
    max_duration_minutes: int = 15
    news_window_hours: int = 24


class CreateShowRequest(BaseModel):
    slug: str
    name: str
    tagline: str = ""
    description: str = ""
    category: str = "News"
    subcategory: str = ""
    topic_domains: list[str] = ["general"]
    story_quotas: dict[str, int] = {}
    newsapi: Optional[dict] = None
    editions: list[EditionInput] = []
    hosts: list[HostInput] = []
    feeds: dict[str, list[str]] = {}


# ─── Show management endpoints ───────────────────────────────────────────────

@app.get("/api/shows")
def api_list_shows():
    slugs = list_shows()
    shows = []
    for slug in slugs:
        try:
            show = load_show(slug)
            shows.append({
                "slug": slug,
                "name": show.name,
                "editions": list(show.valid_editions),
                "hosts": len(show.personas),
                "feeds": sum(len(v) for v in show.feeds.items()),
            })
        except Exception as e:
            shows.append({"slug": slug, "name": slug, "error": str(e)})
    return shows


@app.post("/api/shows")
def api_create_show(req: CreateShowRequest):
    """Create a new show from wizard input."""
    # Validate slug
    err = validate_slug(req.slug)
    if err:
        raise HTTPException(400, err)
    if show_exists(req.slug):
        raise HTTPException(409, f"Show already exists: {req.slug}")

    # Validate basic requirements
    if len(req.name) < 2 or len(req.name) > 100:
        raise HTTPException(400, "Name must be 2-100 characters")
    static_hosts = [h for h in req.hosts if h.type == "static"]
    if len(static_hosts) < 2:
        raise HTTPException(400, "At least 2 static hosts are required")

    # Build editions dict from list
    editions_dict = {}
    if req.editions:
        for ed in req.editions:
            editions_dict[ed.name] = {
                "publish_time_est": ed.publish_time_est,
                "target_duration_minutes": ed.target_duration_minutes,
                "min_duration_minutes": ed.min_duration_minutes,
                "max_duration_minutes": ed.max_duration_minutes,
                "news_window_hours": ed.news_window_hours,
                "title_format": "{date} - {hook}",
                "includes_recap": False,
            }
    else:
        editions_dict = None  # build_default_config will use defaults

    # Convert hosts to dicts for builder
    hosts_data = [h.model_dump() for h in req.hosts]
    for h in hosts_data:
        h["voice_providers"] = [vp for vp in h["voice_providers"]]

    # Build config
    config = build_default_config(
        name=req.name,
        slug=req.slug,
        tagline=req.tagline,
        description=req.description,
        category=req.category,
        subcategory=req.subcategory,
        topic_domains=req.topic_domains,
        story_quotas=req.story_quotas or None,
        newsapi=req.newsapi,
        editions=editions_dict,
        hosts=hosts_data,
    )

    # Build personas
    personas = build_default_personas(hosts_data)

    # Build prompts (use defaults)
    prompts = {
        "curator": DEFAULT_CURATOR_PROMPT,
        "scriptwriter": DEFAULT_SCRIPTWRITER_PROMPT,
        "publisher": DEFAULT_PUBLISHER_PROMPT,
    }

    # Create the show
    show = create_show(
        slug=req.slug,
        config=config,
        personas=personas,
        feeds=req.feeds,
        prompts=prompts,
    )

    # Git commit
    _git_commit_show(req.slug, "initial creation")

    return {
        "slug": show.slug,
        "name": show.name,
        "editions": list(show.valid_editions),
        "hosts": len(show.personas),
    }


@app.get("/api/shows/{slug}/exists")
def api_show_exists(slug: str):
    """Check if a show slug already exists."""
    return {"exists": show_exists(slug)}


@app.delete("/api/shows/{slug}")
def api_delete_show(slug: str):
    """Delete a show's config directory."""
    if not show_exists(slug):
        raise HTTPException(404, f"Show not found: {slug}")

    try:
        delete_show(slug)
        # Git commit the deletion
        try:
            import subprocess
            subprocess.run(
                ["git", "add", "-A", f"shows/{slug}/"],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "commit", "-m", f"Delete show: {slug}"],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["git", "push"],
                capture_output=True, timeout=30,
            )
        except Exception as e:
            log.warning(f"Git commit/push after deletion failed: {e}")

        return {"status": "deleted", "slug": slug}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/shows/{slug}/config")
def api_get_config(slug: str):
    try:
        show = load_show(slug)
        return show.config
    except FileNotFoundError:
        raise HTTPException(404, f"Show not found: {slug}")


@app.put("/api/shows/{slug}/config")
async def api_put_config(slug: str, request: Request):
    data = await request.json()
    save_show_config(slug, "config", data)
    _git_commit_show(slug, "config")
    return {"status": "saved"}


@app.get("/api/shows/{slug}/personas")
def api_get_personas(slug: str):
    try:
        show = load_show(slug)
        return show.personas
    except FileNotFoundError:
        raise HTTPException(404, f"Show not found: {slug}")


@app.put("/api/shows/{slug}/personas")
async def api_put_personas(slug: str, request: Request):
    data = await request.json()
    save_show_config(slug, "personas", data)
    _git_commit_show(slug, "personas")
    return {"status": "saved"}


@app.get("/api/shows/{slug}/feeds")
def api_get_feeds(slug: str):
    try:
        show = load_show(slug)
        return show.feeds
    except FileNotFoundError:
        raise HTTPException(404, f"Show not found: {slug}")


@app.put("/api/shows/{slug}/feeds")
async def api_put_feeds(slug: str, request: Request):
    data = await request.json()
    save_show_config(slug, "feeds", data)
    _git_commit_show(slug, "feeds")
    return {"status": "saved"}


@app.get("/api/shows/{slug}/sponsors")
def api_get_sponsors(slug: str):
    try:
        show = load_show(slug)
        return {"sponsors": show.sponsors}
    except FileNotFoundError:
        raise HTTPException(404, f"Show not found: {slug}")


@app.put("/api/shows/{slug}/sponsors")
async def api_put_sponsors(slug: str, request: Request):
    data = await request.json()
    save_show_config(slug, "sponsors", data)
    _git_commit_show(slug, "sponsors")
    return {"status": "saved"}


@app.get("/api/shows/{slug}/prompts/{name}")
def api_get_prompt(slug: str, name: str):
    try:
        show = load_show(slug)
        text = show.prompts.get(name, "")
        if not text:
            raise HTTPException(404, f"Prompt not found: {name}")
        return {"name": name, "text": text}
    except FileNotFoundError:
        raise HTTPException(404, f"Show not found: {slug}")


@app.put("/api/shows/{slug}/prompts/{name}")
async def api_put_prompt(slug: str, name: str, request: Request):
    data = await request.json()
    text = data.get("text", "")
    save_show_config(slug, f"prompts/{name}", text)
    _git_commit_show(slug, f"prompts/{name}")
    return {"status": "saved"}


# ─── Pipeline control ────────────────────────────────────────────────────────

@app.post("/api/runs")
def api_start_run(req: RunRequest):
    run_id = str(uuid.uuid4())[:8]
    log_path = RUNS_LOG_DIR / f"{run_id}.log"

    run_record = {
        "id": run_id,
        "show": req.show,
        "edition": req.edition,
        "start_from": req.start_from,
        "dry_run": req.dry_run,
        "date": req.date,
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
        "error": None,
        "log_file": str(log_path),
    }

    runs = _load_runs()
    runs.insert(0, run_record)
    runs = runs[:100]  # Keep last 100 runs
    _save_runs(runs)

    _active_runs[run_id] = run_record

    # Run pipeline in background thread
    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(run_id, req),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/runs")
def api_list_runs(show: Optional[str] = None, limit: int = 20):
    runs = _load_runs()
    if show:
        runs = [r for r in runs if r.get("show") == show]
    return runs[:limit]


@app.get("/api/runs/{run_id}")
def api_get_run(run_id: str):
    # Check active runs first
    if run_id in _active_runs:
        return _active_runs[run_id]
    # Check persisted runs
    runs = _load_runs()
    for r in runs:
        if r["id"] == run_id:
            return r
    raise HTTPException(404, f"Run not found: {run_id}")


@app.get("/api/runs/{run_id}/logs")
def api_get_run_logs(run_id: str):
    """Stream log output via Server-Sent Events."""
    log_path = RUNS_LOG_DIR / f"{run_id}.log"

    def event_stream():
        # Wait for file to appear
        import time
        waited = 0
        while not log_path.exists() and waited < 10:
            time.sleep(0.5)
            waited += 0.5

        if not log_path.exists():
            yield f"data: Log file not found\n\n"
            return

        with open(log_path) as f:
            while True:
                line = f.readline()
                if line:
                    yield f"data: {line.rstrip()}\n\n"
                else:
                    # Check if run is still active
                    if run_id not in _active_runs:
                        # Read any remaining lines
                        remaining = f.read()
                        if remaining:
                            for l in remaining.strip().split("\n"):
                                yield f"data: {l}\n\n"
                        yield f"data: [END]\n\n"
                        return
                    time.sleep(0.3)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ─── Story injection ─────────────────────────────────────────────────────────

@app.post("/api/shows/{slug}/inject")
def api_inject_story(slug: str, req: InjectRequest):
    from agents.inject_stories import inject_from_url, inject_from_text, inject_from_topic

    try:
        if req.url:
            r = inject_from_url(req.url, req.priority, req.note, "admin", req.edition, slug)
        elif req.text:
            r = inject_from_text(req.text, req.priority, req.note, "admin", req.edition, slug)
        elif req.topic:
            r = inject_from_topic(req.topic, req.priority, req.note, "admin", req.edition, slug)
        else:
            raise HTTPException(400, "Must provide url, text, or topic")
        return {"status": "injected", "headline": r["story"]["headline"]}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/shows/{slug}/injections")
def api_list_injections(slug: str, date: Optional[str] = None, edition: str = "all"):
    from agents.inject_stories import get_pending_injections
    from datetime import date as date_cls
    target = date or str(date_cls.today())
    return get_pending_injections(target, edition, slug)


# ─── Static files ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    html_path = Path("admin/index.html")
    if html_path.exists():
        return html_path.read_text()
    return "<h1>Admin dashboard not found</h1><p>Create admin/index.html</p>"


# ─── Pipeline runner ─────────────────────────────────────────────────────────

def _run_pipeline_thread(run_id: str, req: RunRequest):
    """Execute the pipeline in a background thread with logging to file."""
    import time
    log_path = RUNS_LOG_DIR / f"{run_id}.log"

    # Set up file logging for this run
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    root_logger.setLevel(logging.INFO)

    try:
        show = load_show(req.show)

        # Import here to avoid circular imports at module level
        from orchestrator import run_pipeline

        result = run_pipeline(
            show=show,
            edition=req.edition,
            start_from=req.start_from,
            dry_run=req.dry_run,
            episode_date=req.date,
        )

        _update_run(run_id, {
            "status": "success",
            "finished_at": datetime.now().isoformat(),
        })

    except Exception as e:
        logging.getLogger("admin").error(f"Pipeline failed: {e}")
        _update_run(run_id, {
            "status": "failed",
            "finished_at": datetime.now().isoformat(),
            "error": str(e),
        })

    finally:
        root_logger.removeHandler(file_handler)
        file_handler.close()
        _active_runs.pop(run_id, None)


# ─── Git helpers ──────────────────────────────────────────────────────────────

def _git_commit_show(slug: str, section: str):
    """Auto-commit and push config changes."""
    try:
        show_dir = f"shows/{slug}/"
        subprocess.run(
            ["git", "add", show_dir],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Update {slug} {section} config"],
            capture_output=True, timeout=10,
        )
        result = subprocess.run(
            ["git", "push"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warning(f"Git push failed: {result.stderr}")
    except Exception as e:
        log.warning(f"Git commit/push failed: {e}")


# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    shows = list_shows()
    print(f"🎛️  Show Admin running at http://localhost:8000")
    print(f"📡 Shows loaded: {', '.join(shows)}")
    print(f"📖 API docs at http://localhost:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
