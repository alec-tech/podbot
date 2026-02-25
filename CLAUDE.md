# CLAUDE.md — The Signal

## What This Is

The Signal is a fully autonomous, AI-powered twice-daily podcast covering business and tech news. Two editions run on weekdays: AM (4 AM EST, ~33 min) and PM (1 PM EST, ~11 min). Three AI hosts — Alex Chen (business anchor), Morgan Lee (tech correspondent), and Drew Vasquez (strategy analyst, AM crossover only). Zero human intervention after setup.

## Project Structure

```
orchestrator.py          # Main pipeline entry point — runs all 4 stages sequentially
agents/
  curator.py             # Stage 1: RSS + NewsAPI gathering, Claude-powered curation
  scriptwriter.py        # Stage 2: Script generation with host personas, duration targeting
  voice_producer.py      # Stage 3: ElevenLabs TTS + FFmpeg assembly and LUFS normalization
  publisher.py           # Stage 4: Buzzsprout upload, metadata generation, social posting
  publisher_website.py   # Website data export: episodes.json, RSS feed generation
  story_memory.py        # SQLite-backed story tracking (3-day cooldown, cross-edition dedup)
  inject_stories.py      # Manual story injection system (must_include / consider / background)
config/show_config.json  # Master config: voices, durations, audio specs, edition settings
data/sponsors.json       # Active sponsor definitions with scripts, slots, date ranges
website/                 # Netlify-deployed static site (index.html, dashboard.html, episodes.json)
.github/workflows/daily_episode.yml  # Cron: 9AM UTC (AM) + 6PM UTC (PM), weekdays only
```

## How the Pipeline Works

`orchestrator.py` runs one edition per invocation through 4 stages:

1. **Curation** — `CuratorAgent` gathers RSS/NewsAPI stories within the edition's time window, loads injections, builds a brief via Claude (claude-sonnet-4-6). AM gets a yesterday recap block; PM excludes AM stories.
2. **Scriptwriting** — `ScriptwriterAgent` generates a full script (claude-opus-4-6), then auto-expands or trims (claude-sonnet-4-6) to hit duration targets. AM: 31-36 min, PM: 8-15 min.
3. **Audio Production** — `VoiceProducerAgent` parses `[HOST - direction]: "dialogue"` lines, synthesizes each via ElevenLabs, assembles with FFmpeg (concat + loudnorm to -16 LUFS).
4. **Publishing** — `PublisherAgent` uploads to Buzzsprout, generates metadata via Claude (claude-haiku-4-5), posts to Twitter/LinkedIn, updates `website/episodes.json` and RSS feed.

Story memory (`database/story_memory.db`) persists across runs so editions don't repeat stories within a 3-day window. AM pulls yesterday's PM headlines for the recap segment; PM excludes today's AM headlines.

## Key Commands

```bash
# Run a full episode pipeline
python orchestrator.py --edition am
python orchestrator.py --edition pm

# Dry run (curation only, no audio/publishing)
python orchestrator.py --edition am --dry-run

# Skip audio generation (reuse existing file)
python orchestrator.py --edition pm --skip-audio

# Override date or episode number
python orchestrator.py --edition am --date 2026-02-25 --episode-num 42

# Inject a story
python agents/inject_stories.py --url "https://..." --priority must_include --edition am
python agents/inject_stories.py --topic "Fed rate decision" --priority consider --edition both
python agents/inject_stories.py --list  # Show pending injections
```

## Claude Model Usage

- **Curator** (story selection): claude-sonnet-4-6
- **Scriptwriter** (main draft): claude-opus-4-6
- **Scriptwriter** (expand/trim): claude-sonnet-4-6
- **Publisher** (metadata/SEO): claude-haiku-4-5
- **Story Memory** (callback detection): claude-haiku-4-5
- **Inject Stories** (enrichment): claude-haiku-4-5
- **Publisher Website** (company extraction): claude-haiku-4-5

## Environment Variables

Required: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ALEX`, `ELEVENLABS_VOICE_MORGAN`, `ELEVENLABS_VOICE_DREW`, `BUZZSPROUT_API_KEY`, `BUZZSPROUT_PODCAST_ID`

Recommended: `NEWS_API_KEY`, `SLACK_WEBHOOK_URL`

Optional: Twitter credentials, LinkedIn credentials, AWS S3/R2 for audio storage, `PODCAST_WEBSITE_URL`

See `.env.example` for the full list.

## Edition Differences

| | AM Edition | PM Edition |
|---|---|---|
| Time | 4:00 AM EST | 1:00 PM EST |
| Duration | 31-36 min | 8-15 min |
| Hosts | Alex, Morgan, Drew | Alex, Morgan only |
| Story type | Deep + medium dives | Quick highlights |
| Sponsor slots | 2 (mid-roll + outro) | 1 (post-roll) |
| Recap | Yes (yesterday's PM) | No |
| News window | ~15 hrs (prev 1 PM to 4 AM) | ~9 hrs (4 AM to 1 PM) |

## Script Format

All scripts use the format: `[HOST_NAME - acting direction]: "dialogue"`

The voice producer parses this with regex to extract host, direction, and dialogue. Sponsor spots use the exact script from `data/sponsors.json` verbatim — the designated host reads it as-is.

## Conventions

- All times are EST (America/New_York). UTC is only used in the GitHub Actions cron.
- Output files follow the pattern: `{type}_{YYYY-MM-DD}_{edition}.{ext}`
- The website (`website/`) is deployed via Netlify. `episodes.json` and `feed.xml` are committed to git and auto-deployed.
- Sponsors are stored in `data/sponsors.json` and filtered by edition, date range, and active flag at runtime.
- Story injections live in `data/injected_stories.json` and are archived after 14 days.
- The pipeline has fallback logic: if curation fails, it tries loading a previous brief. If publishing fails, it saves an emergency backup JSON.
- Slack alerts fire on failures and must_include injections.
- The GitHub Actions workflow caches `database/` and `data/injected_stories.json` across runs for state persistence.

## Things to Be Careful About

- **Never commit `.env`** — it contains API keys. The `.gitignore` already excludes it.
- **Sponsor scripts are read verbatim** — the scriptwriter and voice producer must not modify sponsor copy.
- **Story memory is critical for dedup** — the SQLite DB in `database/` must persist across runs. In CI, this is handled by actions/cache.
- **Audio generation is expensive** — ElevenLabs charges per character. Use `--dry-run` or `--skip-audio` when testing.
- **Duration QA matters** — the pipeline validates script and audio durations against min/max targets per edition. Scripts that are too short get expanded; too long get trimmed.
- `outputs/` contains generated artifacts (briefs, scripts, audio) and is gitignored except for `website/episodes.json`.
