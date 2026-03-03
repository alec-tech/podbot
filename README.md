# PodBot

A fully autonomous, open-source AI podcast platform. Define your show — hosts, topics, RSS feeds — and PodBot curates stories, writes multi-host scripts, synthesizes voices, and publishes episodes. Zero human intervention after setup.

**License:** AGPLv3

### Built With PodBot

**[The Signal](https://podcasts.apple.com/us/podcast/the-signal/id1879902505)** — Three-daily AI business & tech news. Fully autonomous, zero human intervention.

[Apple Podcasts](https://podcasts.apple.com/us/podcast/the-signal/id1879902505) · [Spotify](https://open.spotify.com/show/04pO5buMHJjZljvgGK1dQs) · [Amazon Music](https://music.amazon.com/podcasts/3b8c2c9c-7c7c-495a-84ce-63a9f70722c2/the-signal)

## Quick Start

```bash
# Clone and setup
git clone https://github.com/your-org/podbot.git
cd podbot
chmod +x setup.sh && ./setup.sh

# Configure API keys
# Edit .env with at least ANTHROPIC_API_KEY and one TTS provider key

# Dry run (curation only — no TTS cost, no publishing)
source .venv/bin/activate
python orchestrator.py --show example-show --edition morning --dry-run

# Full episode
python orchestrator.py --show example-show --edition morning

# Admin dashboard
python admin.py   # http://localhost:8000
```

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

The included `.github/workflows/run_show.yml` workflow runs any show via `workflow_dispatch`:

1. Set your API keys as GitHub Secrets
2. Go to Actions → Run Show → Run workflow
3. Enter your show slug and edition

To schedule automated runs, uncomment the `schedule` block in the workflow file and set your cron times.

### Netlify

The `website/` directory deploys as a static site via Netlify. Per-show `episodes.json` and `feed.xml` are committed to git and auto-deployed.

## Environment Variables

**Required:** `ANTHROPIC_API_KEY`, `BUZZSPROUT_API_KEY`, `BUZZSPROUT_PODCAST_ID`

**TTS (at least one):** `CARTESIA_API_KEY`, `OPENAI_API_KEY`, `ELEVENLABS_API_KEY`

**Recommended:** `NEWS_API_KEY`, `SLACK_WEBHOOK_URL`

**Optional:** Twitter credentials, LinkedIn credentials, AWS S3/R2 for audio storage

See `.env.example` for the full list.

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

## Next Steps After Forking

1. **Replace placeholder URLs** — Update `your-org/podbot` in this README and `website/index.html` with your actual GitHub repo
2. **Create your first show** — Use the admin wizard or copy `shows/example-show/`
3. **Configure TTS voices** — Add Cartesia/ElevenLabs voice IDs to your show's `show.json` (OpenAI voices work out of the box)
4. **Set up GitHub Actions** — Add API keys as repo secrets, uncomment the cron schedule in `.github/workflows/run_show.yml`
5. **Deploy the website** — Connect `website/` to Netlify (or any static host)
6. **Tag v1.0.0** — Create your first release once your show is publishing
