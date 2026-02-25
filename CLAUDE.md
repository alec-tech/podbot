# CLAUDE.md — The Signal

## What This Is

The Signal is a fully autonomous, AI-powered three-daily podcast covering business, tech, and policy news. Three editions run on weekdays: Morning (7 AM EST), Midday (1 PM EST), and Evening (5:30 PM EST). All editions are 10-15 minutes. Two static AI hosts — Alex Chen (business anchor) and Morgan Lee (tech correspondent) — appear in every episode, joined by one of five rotating crossover guests. Zero human intervention after setup.

## Project Structure

```
orchestrator.py          # Main pipeline entry point — runs all 4 stages sequentially
agents/
  curator.py             # Stage 1: RSS + NewsAPI gathering, Claude-powered curation
  scriptwriter.py        # Stage 2: Script generation with host personas, duration targeting
  voice_producer.py      # Stage 3: TTS (Cartesia/OpenAI/ElevenLabs fallback) + FFmpeg assembly
  publisher.py           # Stage 4: Buzzsprout upload, metadata generation, social posting
  publisher_website.py   # Website data export: episodes.json, RSS feed generation
  story_memory.py        # SQLite-backed story tracking (3-day cooldown, soft cross-edition dedup)
  inject_stories.py      # Manual story injection system (must_include / consider / background)
  tts/                   # TTS provider abstraction with fallback chain
    __init__.py           # FallbackTTSChain, load_voice_config()
    base.py               # TTSProvider ABC, VoiceConfig dataclass
    cartesia_provider.py  # Primary — Cartesia SDK, sonic-3 model
    openai_provider.py    # Fallback 1 — OpenAI SDK, gpt-4o-mini-tts
    elevenlabs_provider.py # Fallback 2 — ElevenLabs SDK
config/show_config.json  # Master config: voices (per-provider), durations, audio specs, editions
data/sponsors.json       # Active sponsor definitions with scripts, slots, date ranges
website/                 # Netlify-deployed static site (index.html, dashboard.html, episodes.json)
.github/workflows/daily_episode.yml  # Cron: 12PM/6PM/10:30PM UTC, weekdays only
```

## How the Pipeline Works

`orchestrator.py` runs one edition per invocation through 4 stages:

1. **Curation** — `CuratorAgent` gathers RSS/NewsAPI stories within the edition's time window, loads injections, builds a brief via Claude (claude-sonnet-4-6). Politics stories included only when they impact business/tech. Soft dedup: earlier same-day stories provide context, not hard exclusion.
2. **Scriptwriting** — `ScriptwriterAgent` generates a full script (claude-opus-4-6) with Alex + Morgan + a topic-matched rotating guest, then auto-expands or trims (claude-sonnet-4-6) to hit 10-15 min target.
3. **Audio Production** — `VoiceProducerAgent` parses `[HOST - direction]: "dialogue"` lines, synthesizes via fallback TTS chain (Cartesia → OpenAI → ElevenLabs), assembles with FFmpeg (concat + loudnorm to -16 LUFS).
4. **Publishing** — `PublisherAgent` uploads to Buzzsprout, generates metadata via Claude (claude-haiku-4-5), posts to Twitter/LinkedIn, updates `website/episodes.json` and RSS feed.

Story memory (`database/story_memory.db`) persists across runs so editions don't repeat stories within a 3-day window. Earlier editions' headlines provide soft context to later editions.

## Key Commands

```bash
# Run a full episode pipeline
python orchestrator.py --edition morning
python orchestrator.py --edition midday
python orchestrator.py --edition evening

# Dry run (curation only, no audio/publishing)
python orchestrator.py --edition morning --dry-run

# Skip audio generation (reuse existing file)
python orchestrator.py --edition midday --skip-audio

# Override date or episode number
python orchestrator.py --edition morning --date 2026-02-25 --episode-num 42

# Inject a story
python agents/inject_stories.py --url "https://..." --priority must_include --edition morning
python agents/inject_stories.py --topic "Fed rate decision" --priority consider --edition all
python agents/inject_stories.py --list  # Show pending injections
```

## TTS Provider Chain

The voice producer uses a fallback chain: Cartesia (primary) → OpenAI (fallback 1) → ElevenLabs (fallback 2). Per-line retries: 3/2/2. Providers skip initialization if their API key is missing. Voice IDs and per-provider settings are in `config/show_config.json` (not env vars).

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

See `.env.example` for the full list.

## Edition Details

| | Morning Edition | Midday Edition | Evening Edition |
|---|---|---|---|
| Time | 7:00 AM EST | 1:00 PM EST | 5:30 PM EST |
| Duration | 10-15 min (12 ideal) | 10-15 min (12 ideal) | 10-15 min (12 ideal) |
| Static Hosts | Alex, Morgan | Alex, Morgan | Alex, Morgan |
| Crossover Guest | 1 rotating | 1 rotating | 1 rotating |
| Stories | 5 (2 biz + 1 overlap + 2 tech) | 5 (2 biz + 1 overlap + 2 tech) | 5 (2 biz + 1 overlap + 2 tech) |
| Sponsor slots | 3 optional | 3 optional | 3 optional |
| News window | ~14 hrs | ~7 hrs | ~5 hrs |

## Host Roster

**Static (every episode):**
- **Alex Chen** — Business anchor
- **Morgan Lee** — Tech correspondent

**Rotating crossover guests (one per episode, topic-matched):**
- **Drew Vasquez** — Geopolitics & trade analyst
- **Priya Nair** — AI & emerging tech specialist
- **Marcus Cole** — Policy & regulation correspondent
- **Sam Torres** — Startup & venture correspondent
- **Jordan Blake** — Consumer & culture analyst

## Episode Structure (all editions)

```
[PRE-INTRO SPONSOR  — 0:00-0:30]   optional
[INTRO              — 0:30-1:00]
[POST-INTRO SPONSOR — 1:00-1:30]   optional
[BUSINESS BLOCK     — 1:30-4:30]   2 stories, Alex leads
[CROSSOVER SEGMENT  — 4:30-7:30]   1 story, rotating guest joins
[TECH BLOCK         — 7:30-10:30]  2 stories, Morgan leads
[PRE-OUTRO SPONSOR  — 10:30-11:00] optional
[WRAP + SIGNOFF     — 11:00-12:00]
```

## Script Format

All scripts use the format: `[HOST_NAME - acting direction]: "dialogue"`

The voice producer parses this with regex to extract host, direction, and dialogue. Sponsor spots use the exact script from `data/sponsors.json` verbatim — the designated host reads it as-is.

## Conventions

- All times are EST (America/New_York). UTC is only used in the GitHub Actions cron.
- Output files follow the pattern: `{type}_{YYYY-MM-DD}_{edition}.{ext}`
- The website (`website/`) is deployed via Netlify. `episodes.json` and `feed.xml` are committed to git and auto-deployed.
- Sponsors are stored in `data/sponsors.json` with 3 optional slots: `pre-intro`, `post-intro`, `pre-outro`.
- Story injections live in `data/injected_stories.json` and are archived after 14 days. Edition values: `morning`, `midday`, `evening`, `all`.
- The pipeline has fallback logic: if curation fails, it tries loading a previous brief. If publishing fails, it saves an emergency backup JSON.
- Slack alerts fire on failures and must_include injections.
- The GitHub Actions workflow caches `database/` and `data/injected_stories.json` across runs for state persistence.

## Things to Be Careful About

- **Never commit `.env`** — it contains API keys. The `.gitignore` already excludes it.
- **Sponsor scripts are read verbatim** — the scriptwriter and voice producer must not modify sponsor copy.
- **Story memory is critical for dedup** — the SQLite DB in `database/` must persist across runs. In CI, this is handled by actions/cache.
- **Audio generation is expensive** — TTS providers charge per character. Use `--dry-run` or `--skip-audio` when testing.
- **Duration QA matters** — the pipeline validates script and audio durations against 10-15 min targets. Scripts that are too short get expanded; too long get trimmed.
- `outputs/` contains generated artifacts (briefs, scripts, audio) and is gitignored except for `website/episodes.json`.
- **Voice IDs in config, not env** — Voice IDs are in `config/show_config.json` per-provider. Only API keys go in `.env`.
