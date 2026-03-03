# CLAUDE.md — PodBot: Multi-Show AI Podcast Platform

## What This Is

A fully autonomous, open-source AI podcast platform that produces multiple shows with zero human intervention. Each show has its own hosts, RSS feeds, topic domains, and publishing config. Shows are defined declaratively in `shows/{slug}/` and run through a shared four-stage pipeline. Licensed under AGPLv3.

### Example Show

| Show | Slug | Editions | Hosts | Topic |
|---|---|---|---|---|
| **Example Show** | `example-show` | Morning / Midday / Evening | Chuck, Jessica + 5 rotating | Business, tech, policy |

## Project Structure

```
orchestrator.py              # Main pipeline — runs all 4 stages for any show
admin.py                     # FastAPI admin server (config CRUD, pipeline runs, SSE logs)
admin/index.html             # Admin dashboard UI (vanilla JS)
requirements.txt             # Python dependencies
setup.sh                     # Initial setup script
netlify.toml                 # Netlify deploy config (publish dir: website)
.env.example                 # Environment variable template
LICENSE                      # AGPLv3
CONTRIBUTING.md              # Contributor guide
agents/
  show_loader.py             # ShowConfig dataclass, load/save/list shows
  curator.py                 # Stage 1: RSS + NewsAPI gathering, Claude-powered curation
  scriptwriter.py            # Stage 2: Script generation with host personas, duration targeting
  voice_producer.py          # Stage 3: TTS (Cartesia/OpenAI/ElevenLabs fallback) + FFmpeg assembly
  publisher.py               # Stage 4: Buzzsprout upload, metadata generation, social posting
  publisher_website.py       # Website data export: episodes.json, RSS feed generation
  story_memory.py            # SQLite-backed story tracking (3-day cooldown, soft cross-edition dedup)
  inject_stories.py          # Manual story injection system (must_include / consider / background)
  tts/                       # TTS provider abstraction with fallback chain
    __init__.py              # FallbackTTSChain, load_voice_config()
    base.py                  # TTSProvider ABC, VoiceConfig dataclass
    cartesia_provider.py     # Primary — Cartesia SDK, sonic-3 model
    openai_provider.py       # Fallback 1 — OpenAI SDK, gpt-4o-mini-tts
    elevenlabs_provider.py   # Fallback 2 — ElevenLabs SDK
shows/
  example-show/              # Example show config (demonstrates the system)
    show.json                # Master config: voices, editions, durations, audio specs, pipeline
    personas.json            # Host personalities, speech patterns, avoids
    feeds.json               # RSS feed URLs by category
    sponsors.json            # Example sponsor (inactive)
    prompts/                 # Prompt templates (curator.txt, scriptwriter.txt, publisher.txt)
website/                     # Netlify-deployed static site
  index.html                 # PodBot landing page
  dashboard.html             # Episode dashboard
  {show-slug}/               # Per-show website data
    episodes.json            # Episode metadata (committed to git)
    feed.xml                 # RSS feed (committed to git)
.github/workflows/
  run_show.yml               # Generic workflow — any show via workflow_dispatch
.github/ISSUE_TEMPLATE/
  bug_report.yml             # Bug report form
  feature_request.yml        # Feature request form
```

### Per-Show Runtime Paths

Each show gets isolated directories (created automatically):

```
outputs/{slug}/briefs/       # Curated story briefs
outputs/{slug}/scripts/      # Generated scripts + metadata JSON
outputs/{slug}/audio/        # Final MP3 episodes
database/{slug}/             # SQLite story memory
data/{slug}/                 # Injected stories, runtime state
logs/{slug}/                 # Pipeline logs
website/{slug}/              # episodes.json, feed.xml
```

## How the Pipeline Works

`orchestrator.py --show {slug}` runs one edition per invocation through 4 stages:

1. **Curation** — `CuratorAgent(show)` gathers RSS/NewsAPI stories within the edition's time window, loads injections, builds a brief via Claude (claude-sonnet-4-6). Topic filtering is show-specific. Soft dedup: earlier same-day stories provide context, not hard exclusion.
2. **Scriptwriting** — `ScriptwriterAgent(show)` generates a full script (claude-opus-4-6) using the show's personas and prompt templates, then auto-expands or trims (claude-sonnet-4-6) to hit the show's duration target.
3. **Audio Production** — `VoiceProducerAgent(show)` parses `[HOST - direction]: "dialogue"` lines, synthesizes via fallback TTS chain (Cartesia → OpenAI → ElevenLabs) using the show's voice config, assembles with FFmpeg (concat + loudnorm to -16 LUFS).
4. **Publishing** — `PublisherAgent(show)` generates a dynamic episode title and metadata via Claude (claude-haiku-4-5), uploads to Buzzsprout, posts to Twitter/LinkedIn, updates the show's `website/{slug}/episodes.json` and RSS feed.

Story memory (`database/{slug}/story_memory.db`) persists across runs so editions don't repeat stories within a 3-day window. Earlier editions' headlines provide soft context to later editions.

## Key Commands

```bash
# Run a full episode pipeline
python orchestrator.py --show example-show --edition morning

# Dry run (curation only, no audio/publishing)
python orchestrator.py --show example-show --edition morning --dry-run

# Resume from a specific stage
python orchestrator.py --show example-show --edition midday --start-from script
python orchestrator.py --show example-show --edition midday --start-from audio
python orchestrator.py --show example-show --edition midday --start-from publish

# Override date or episode number
python orchestrator.py --show example-show --edition morning --date 2026-02-25 --episode-num 42

# Inject a story
python agents/inject_stories.py --show example-show --url "https://..." --priority must_include --edition morning
python agents/inject_stories.py --show example-show --topic "Breaking story" --priority consider --edition all
python agents/inject_stories.py --show example-show --list

# Admin server
python admin.py  # http://localhost:8000, API docs at /docs
```

## ShowConfig System

All agents accept a `ShowConfig` dataclass (from `agents/show_loader.py`). `load_show()` with no arguments auto-detects the first available show. Key properties:

```python
show = load_show("example-show")  # or load_show() for auto-detect
show.name           # "Example Show"
show.slug           # "example-show"
show.valid_editions # ("morning", "midday", "evening")
show.personas       # {"chuck": {...}, "jessica": {...}, ...}
show.voices         # Per-provider voice config from show.json
show.feeds          # RSS feed URLs by category
show.sponsors       # Active sponsor list
show.prompts        # {"curator": "...", "scriptwriter": "...", ...}
show.story_quotas   # {"business_stories": 2, ...}
show.topic_domains  # ["business", "tech", "policy"]
show.pipeline_config # Duration targets, WPM, retry settings
show.output_dir("briefs")  # Path("outputs/example-show/briefs")
show.database_dir()        # Path("database/example-show")
show.website_dir()         # Path("website/example-show")
```

## Admin Server

`admin.py` is a FastAPI server for managing shows without touching files directly:

- **GET** `/api/shows` — List all shows
- **GET/PUT** `/api/shows/{slug}/config` — Show config (show.json)
- **GET/PUT** `/api/shows/{slug}/personas` — Host personalities
- **GET/PUT** `/api/shows/{slug}/feeds` — RSS feed URLs
- **GET/PUT** `/api/shows/{slug}/sponsors` — Sponsor definitions
- **GET/PUT** `/api/shows/{slug}/prompts/{name}` — Prompt templates
- **POST** `/api/runs` — Trigger a pipeline run (any show/edition/stage)
- **GET** `/api/runs` — List runs (filterable by show)
- **GET** `/api/runs/{id}` — Get run status/details
- **GET** `/api/runs/{id}/logs` — SSE log streaming for a run
- **POST** `/api/shows/{slug}/inject` — Inject a story
- **GET** `/api/shows/{slug}/injections` — List pending injections

Config saves auto-commit and push to git. The UI is at `admin/index.html`.

## TTS Provider Chain

The voice producer uses a fallback chain: Cartesia (primary) → OpenAI (fallback 1) → ElevenLabs (fallback 2). Per-line retries: 3/2/2. Providers skip initialization if their API key is missing. Voice IDs and per-provider settings are in each show's `show.json` under `voices` (not env vars).

## Claude Model Usage

- **Curator** (story selection): claude-sonnet-4-6
- **Scriptwriter** (main draft): claude-opus-4-6
- **Scriptwriter** (expand/trim): claude-sonnet-4-6
- **Publisher** (metadata/SEO): claude-haiku-4-5
- **Story Memory** (callback detection): claude-haiku-4-5
- **Inject Stories** (enrichment): claude-haiku-4-5
- **Publisher Website** (company extraction): claude-haiku-4-5

## Environment Variables

Required: `ANTHROPIC_API_KEY`, `BUZZSPROUT_API_KEY`, `BUZZSPROUT_PODCAST_ID`

TTS (at least one): `CARTESIA_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`

Recommended: `NEWS_API_KEY`, `SLACK_WEBHOOK_URL`

Optional: Twitter credentials, LinkedIn credentials, AWS S3/R2 for audio storage, `PODCAST_WEBSITE_URL`

Per-show Buzzsprout overrides (e.g. `BUZZSPROUT_PODCAST_ID_MY_SHOW`) are supported via env var naming convention.

See `.env.example` for the full list.

## Script Format

All scripts use the format: `[HOST_NAME - acting direction]: "dialogue"`

The voice producer parses this with regex to extract host, direction, and dialogue. Sponsor spots use the exact script from the show's `sponsors.json` verbatim — the designated host reads it as-is.

## Conventions

- All times are EST (America/New_York). UTC is only used in the GitHub Actions cron.
- Output files follow the pattern: `{type}_{YYYY-MM-DD}_{edition}.{ext}`
- The website (`website/`) is deployed via Netlify. Per-show `episodes.json` and `feed.xml` are committed to git and auto-deployed.
- Sponsors are stored per-show in `shows/{slug}/sponsors.json` with 3 optional slots: `pre-intro`, `post-intro`, `pre-outro`.
- Story injections live in `data/{slug}/injected_stories.json` and are archived after 14 days.
- The pipeline has fallback logic: if curation fails, it tries loading a previous brief. If publishing fails, it saves an emergency backup JSON.
- Slack alerts fire on failures and must_include injections.
- GitHub Actions workflow caches `database/{slug}/` and `data/{slug}/injected_stories.json` per-show.
- All agents use lazy client init (`_get_client()`) to avoid import-time crashes when API keys aren't set.
- `load_show()` with no arguments auto-detects the first available show. `inject_stories.py --show` is required (no default).

## Things to Be Careful About

- **Never commit `.env`** — it contains API keys. The `.gitignore` already excludes it.
- **Sponsor scripts are read verbatim** — the scriptwriter and voice producer must not modify sponsor copy.
- **Story memory is critical for dedup** — the SQLite DB in `database/{slug}/` must persist across runs. In CI, this is handled by actions/cache.
- **Audio generation is expensive** — TTS providers charge per character. Use `--dry-run` or `--start-from` when testing.
- **Duration QA matters** — the pipeline validates script and audio durations against the show's targets. Scripts that are too short get expanded; too long get trimmed.
- `outputs/` contains generated artifacts (briefs, scripts, audio) and is gitignored.
- **Voice IDs in show config, not env** — Voice IDs are in `shows/{slug}/show.json` per-provider. Only API keys go in `.env`.
- **Show isolation** — Each show has its own database, output dir, website dir, and injection data. Don't cross-contaminate.
