# PodBot

A fully autonomous, open-source AI podcast platform. Define your show — hosts, topics, RSS feeds — and PodBot curates stories, writes multi-host scripts, synthesizes voices, and publishes episodes. Zero human intervention after setup.

**License:** AGPLv3

### Example of a REAL podcast Built With PodBot as a Proof of Concept

**[The Signal](https://podcasts.apple.com/us/podcast/the-signal/id1879902505)** — Three-daily AI business & tech news. Fully autonomous, zero human intervention.

[Apple Podcasts](https://podcasts.apple.com/us/podcast/the-signal/id1879902505) · [Spotify](https://open.spotify.com/show/04pO5buMHJjZljvgGK1dQs) · [Amazon Music](https://music.amazon.com/podcasts/3b8c2c9c-7c7c-495a-84ce-63a9f70722c2/the-signal)

---

## Prerequisites

Before you start, make sure you have:

- **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/)
- **FFmpeg** — Required for audio assembly
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt-get install -y ffmpeg`
  - Windows: [ffmpeg.org/download](https://ffmpeg.org/download.html)
- **API keys** — See the [API Keys](#api-keys) section below

## Setup

### 1. Clone and install

```bash
git clone https://github.com/alec-tech/podbot.git
cd podbot
chmod +x setup.sh && ./setup.sh
```

The setup script creates a virtual environment, installs dependencies, and sets up runtime directories.

### 2. Open the admin panel

```bash
source .venv/bin/activate
python admin.py
```

Opens at **http://localhost:8000** (API docs at `/docs`). No API keys needed — the admin panel works entirely with local config files. Use it to create and configure shows, manage hosts and personas, set up RSS feeds, manage sponsors, and trigger pipeline runs. Sponsor management is done exclusively through the admin panel.

The admin panel can also trigger dry runs and full pipeline runs directly from the browser, so **steps 4 and 5 below are optional** — they're the CLI equivalents if you prefer the command line.

### 3. Configure your API keys

Add your API keys as **GitHub repository Secrets** (Settings → Secrets and variables → Actions). The pipeline runs via GitHub Actions, so keys live there — not in a local file. At minimum you need:

| Secret | Required? |
|--------|-----------|
| `ANTHROPIC_API_KEY` | Yes — powers all AI tasks |
| `BUZZSPROUT_API_KEY` | Yes for publishing (skip if just testing with `--dry-run`) |
| `BUZZSPROUT_PODCAST_ID` | Yes for publishing |
| `CARTESIA_API_KEY` or `OPENAI_API_KEY` or `ELEVENLABS_API_KEY` | At least one — TTS provider for audio production |

See the full [API Keys](#api-keys) reference below for where to get each key.

### 4. Run a dry run (CLI alternative)

A dry run executes only the curation stage — it gathers news and builds an editorial brief without generating audio or publishing. No TTS cost. You can also trigger this from the admin panel.

```bash
python orchestrator.py --show example-show --edition morning --dry-run
```

The output brief is saved to `outputs/example-show/briefs/`. Open it to see the curated stories and editorial structure.

### 5. Run a full episode (CLI alternative)

Once your TTS and Buzzsprout keys are configured in GitHub Secrets. You can also trigger this from the admin panel.

```bash
python orchestrator.py --show example-show --edition morning
```

This runs all 4 stages: curation, scriptwriting, voice production, and publishing. The final MP3 is saved to `outputs/example-show/audio/` and uploaded to Buzzsprout.

---

## API Keys

### Required

| Key | What it does | Where to get it |
|-----|-------------|----------------|
| `ANTHROPIC_API_KEY` | Powers all AI tasks (curation, scriptwriting, metadata) | [console.anthropic.com](https://console.anthropic.com) |
| `BUZZSPROUT_API_KEY` | Uploads episodes to your podcast host | [buzzsprout.com](https://www.buzzsprout.com/) — Settings → API |
| `BUZZSPROUT_PODCAST_ID` | Identifies which podcast to publish to | Your Buzzsprout URL: `buzzsprout.com/YOUR_ID` |

### TTS Providers (at least one required)

The voice producer tries providers in order and falls back automatically. You only need one, but having multiple gives you redundancy.

| Key | Provider | Where to get it | Notes |
|-----|----------|-----------------|-------|
| `CARTESIA_API_KEY` | Cartesia (primary) | [play.cartesia.ai](https://play.cartesia.ai) | Highest quality; requires voice IDs in `show.json` |
| `OPENAI_API_KEY` | OpenAI (fallback 1) | [platform.openai.com](https://platform.openai.com) | Works out of the box with preset voice names |
| `ELEVENLABS_API_KEY` | ElevenLabs (fallback 2) | [elevenlabs.io](https://elevenlabs.io) | Requires voice IDs in `show.json` |

**Voice IDs:** OpenAI uses preset names (`onyx`, `nova`, `echo`, etc.) that work immediately. Cartesia and ElevenLabs require you to browse their voice libraries, pick voices, and paste the IDs into your show's `show.json` under `voices → {host} → providers → {provider} → voice_id`. Leave `voice_id` empty to skip that provider.

### Recommended

| Key | What it does | Where to get it |
|-----|-------------|----------------|
| `NEWS_API_KEY` | Supplements RSS feeds with trending stories | [newsapi.org](https://newsapi.org) — free tier: 100 req/day |
| `SLACK_WEBHOOK_URL` | Sends alerts on failures and must-include injections | [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks) |

### Optional

| Key | What it does | Where to get it |
|-----|-------------|----------------|
| `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET` | Auto-posts episodes to Twitter/X | [developer.twitter.com](https://developer.twitter.com) (Elevated access) |
| `LINKEDIN_ACCESS_TOKEN`, `LINKEDIN_PERSON_ID` | Auto-posts episodes to LinkedIn | [linkedin.com/developers](https://www.linkedin.com/developers) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET` | Cloud audio storage (instead of Buzzsprout-only) | [AWS Console](https://aws.amazon.com/s3/) |
| `PODCAST_WEBSITE_URL` | Your podcast's website URL for RSS feed metadata | — |

---

## Create Your Show

### Option 1: Admin Wizard

Start the admin server (`python admin.py`) and use the "Create Show" wizard at `http://localhost:8000`. It walks you through naming, editions, hosts, and voice configuration.

### Option 2: Manual Configuration

```bash
# Copy the example show as a starting point
cp -r shows/example-show shows/my-show

# Edit the config files:
#   shows/my-show/show.json      — name, editions, topic domains, story quotas
#   shows/my-show/personas.json  — host personalities and speech patterns
#   shows/my-show/feeds.json     — RSS feed URLs by category
#   shows/my-show/sponsors.json  — sponsor definitions (optional)
#   shows/my-show/prompts/       — prompt templates for curator/scriptwriter/publisher

# Run your show
python orchestrator.py --show my-show --edition daily --dry-run
```

## How the Pipeline Works

`orchestrator.py --show {slug}` runs one episode through 4 stages:

1. **Curation** — Gathers RSS + NewsAPI stories within the edition's time window. Claude selects and structures stories into an editorial brief. Story memory prevents repeats within a 3-day window.

2. **Scriptwriting** — Claude generates a full multi-host script using persona definitions and prompt templates. Auto-expands or trims to hit the show's duration target.

3. **Voice Production** — Parses `[HOST - direction]: "dialogue"` lines, synthesizes via fallback TTS chain (Cartesia → OpenAI → ElevenLabs), assembles with FFmpeg (concat + loudnorm to -16 LUFS).

4. **Publishing** — Generates dynamic episode title and metadata, uploads to Buzzsprout, posts to Twitter/LinkedIn, updates the show's website data and RSS feed.

## Configuration

### Per-Show Directory Structure

```
shows/{slug}/
  show.json          # Master config: editions, voices, quotas, pipeline settings
  personas.json      # Host personalities, speech patterns
  feeds.json         # RSS feed URLs by category
  sponsors.json      # Sponsor definitions with scripts and slots
  prompts/           # Prompt templates (curator.txt, scriptwriter.txt, publisher.txt)
```

### Runtime Paths (auto-created)

```
outputs/{slug}/briefs/    # Curated story briefs
outputs/{slug}/scripts/   # Generated scripts
outputs/{slug}/audio/     # Final MP3 episodes
database/{slug}/          # SQLite story memory
data/{slug}/              # Injected stories
logs/{slug}/              # Pipeline logs
website/{slug}/           # episodes.json, feed.xml
```

### Key Commands

```bash
# Run pipeline
python orchestrator.py --show my-show --edition daily
python orchestrator.py --show my-show --edition morning --dry-run

# Resume from a specific stage
python orchestrator.py --show my-show --edition daily --start-from script
python orchestrator.py --show my-show --edition daily --start-from audio
python orchestrator.py --show my-show --edition daily --start-from publish

# Inject a story
python agents/inject_stories.py --show my-show --url "https://..." --priority must_include --edition daily
python agents/inject_stories.py --show my-show --topic "Breaking news topic" --priority consider --edition all
python agents/inject_stories.py --show my-show --list

# Admin server
python admin.py
```

## Deployment

### GitHub Actions

The included `.github/workflows/run_show.yml` workflow supports both manual and scheduled runs.

**Setup:** Your API keys should already be configured as repository Secrets (see [step 2](#2-configure-your-api-keys) above). The variable names match those in `.env.example` for reference.

**Manual runs:**

1. Go to Actions → Run Show → Run workflow
2. Enter your show slug and edition

**Scheduled runs (cron):**

To run episodes automatically on a schedule, edit `.github/workflows/run_show.yml`:

1. Set `DEFAULT_SHOW` to your show slug (e.g. `my-show`)
2. Set `EDITION_SCHEDULE` to map UTC hours to editions (e.g. `12=morning 18=midday 22=evening`)
3. Uncomment the `schedule` block and set your cron times to match:

```yaml
schedule:
  - cron: '0 12 * * 1-5'   # Morning: 7:00 AM EST, weekdays
  - cron: '0 18 * * 1-5'   # Midday:  1:00 PM EST, weekdays
  - cron: '0 22 * * 1-5'   # Evening: 5:00 PM EST, weekdays
```

When a cron fires, the workflow checks the current UTC hour against `EDITION_SCHEDULE` to determine which edition to produce. All times are UTC — convert from your timezone (EST = UTC - 5, PST = UTC - 8).

### Netlify

The `website/` directory deploys as a static site via Netlify. Per-show `episodes.json` and `feed.xml` are committed to git and auto-deployed.

## Cost Estimate (Per Episode)

| Component | Cost |
|-----------|------|
| Claude API (curation + script + metadata) | ~$0.15–0.40 |
| TTS (Cartesia/OpenAI, ~12 min episode) | ~$0.10–0.30 |
| Buzzsprout hosting | From $12/mo (unlimited episodes) |
| NewsAPI | Free tier (100 req/day) |
| **Total per episode** | **~$0.25–0.70** |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and PR process.

## License

AGPLv3 — see [LICENSE](LICENSE).

## After Forking

1. **Update GitHub links** — Replace `alec-tech/podbot` in `website/index.html` with your fork's repo URL
2. **Create your first show** — Use the admin wizard or copy `shows/example-show/`
3. **Configure TTS voices** — Browse [Cartesia](https://play.cartesia.ai) or [ElevenLabs](https://elevenlabs.io/voice-library) voice libraries and add IDs to your show's `show.json` (OpenAI voices work out of the box)
4. **Set up GitHub Actions** — Add API keys as repo secrets, uncomment the cron schedule in `.github/workflows/run_show.yml`
5. **Deploy the website** — Connect `website/` to Netlify (or any static host)
