# 🎙️ The Signal — Complete Setup & Operations Guide

> A fully autonomous AI-powered **three-daily** podcast covering business, tech, and policy news.
> Three 10-15 minute editions. Three optional sponsor slots per episode. Zero human intervention after setup.

---

## How It Works

| Edition | Time (EST) | News Window | Title Format |
|---------|-----------|-------------|-------------|
| **Morning** | 7:00 AM | Prev 6 PM → 7 AM (~14 hrs) | `2026-02-24 Morning - Markets Brace For Impact` |
| **Midday** | 1:00 PM | 7 AM → 1 PM (~7 hrs) | `2026-02-24 Midday - Fed Breaks From Script` |
| **Evening** | 5:30 PM | 1 PM → 5:30 PM (~5 hrs) | `2026-02-24 Evening - AI Chips Change Everything` |

**Unified episode structure (all editions, ~12 min):**
```
0:00–0:30   Pre-Intro Sponsor (optional)
0:30–1:00   Intro
1:00–1:30   Post-Intro Sponsor (optional)
1:30–4:30   Business Block (2 stories, Alex leads)
4:30–7:30   Crossover Segment (rotating guest joins)
7:30–10:30  Tech Block (2 stories, Morgan leads)
10:30–11:00 Pre-Outro Sponsor (optional)
11:00–12:00 Wrap + Signoff
```

**Hosts:** Alex Chen (business) and Morgan Lee (tech) anchor every episode, joined by one rotating crossover guest: Drew Vasquez (geopolitics), Priya Nair (AI/deep tech), Marcus Cole (policy), Sam Torres (startups), or Jordan Blake (consumer/culture).

**How the editions stay in sync:**
- Soft dedup: earlier same-day stories provide context, not hard exclusion
- Stories CAN be revisited with UPDATE framing if major new developments occur
- 3-day cooldown applies across all editions combined

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Account Setup](#2-account-setup)
3. [Installation](#3-installation)
4. [Configuration](#4-configuration)
5. [Choosing Voices](#5-choosing-voices)
6. [First Episode Test](#6-first-episode-test)
7. [Going Live](#7-going-live)
8. [Deploying the Website](#8-deploying-the-website)
9. [GitHub Actions Automation](#9-github-actions-automation)
10. [Injecting Stories](#10-injecting-stories)
11. [Editorial Dashboard](#11-editorial-dashboard)
12. [Sponsor Management](#12-sponsor-management)
13. [Troubleshooting](#13-troubleshooting)
14. [Cost Breakdown](#14-cost-breakdown)
15. [File Reference](#15-file-reference)
16. [Quick Start Checklist](#16-quick-start-checklist)

---

## 1. Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.10+ | https://python.org |DONE
| FFmpeg | Any | See below |DONE
| Git | Any | https://git-scm.com |DONE

```bash
# macOS
brew install ffmpeg DONE

# Ubuntu / Debian
sudo apt-get install -y ffmpeg

# Windows: https://ffmpeg.org/download.html → add C:\ffmpeg\bin to PATH

# Verify
python3 --version && ffmpeg -version | head -1 DONE
```

---

## 2. Account Setup

### 2.1 Anthropic (Required) done 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
1. https://console.anthropic.com → API Keys → Create Key
2. Settings → Billing → add card, set monthly limit (~$100)

**Est. cost: $25–50/month** (two episodes/day)

### 2.2 ElevenLabs (Required) done sk_b95ea517c5f696366518055235e326c6d4e4473bcb9a47a8
1. https://elevenlabs.io → **Creator plan** ($22/month)
2. Profile → API Keys → copy key

### 2.3 Buzzsprout (Required) done
1. https://buzzsprout.com → new podcast "The Signal" → **$18/month plan**
2. My Account → API Access → copy key 176da6e94e51100209b5d39d0b91d520 + note Podcast ID from URL 2598725

### 2.4 NewsAPI (Free) done 9f9f71aa4e7f45d0bb5b11f678a034fd
1. https://newsapi.org → register → copy key

### 2.5 GitHub (Required for Automation) DONE
1. Create a **private** repo called `the-signal`

### 2.6 Netlify (Required for Website)
1. https://netlify.com → sign up with GitHub

### 2.7 Slack (Optional — alerts)
1. https://api.slack.com/messaging/webhooks → create webhook URL

---

## 3. Installation

```bash
cd the-signal
chmod +x setup.sh
./setup.sh

# Activate every new terminal session:
source .venv/bin/activate    # macOS/Linux
.venv\Scripts\activate       # Windows
```

---

## 4. Configuration

### 4.1 Edit `.env`

```bash
nano .env    # or: code .env
```

**Required:**
```
ANTHROPIC_API_KEY=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
ELEVENLABS_API_KEY=sk_b95ea517c5f696366518055235e326c6d4e4473bcb9a47a8
ELEVENLABS_VOICE_ALEX=3jR9BuQAOPMWUjWpi0ll
ELEVENLABS_VOICE_MORGAN=yj30vwTGJxSHezdAGsv9
ELEVENLABS_VOICE_DREW=dllHSct4GokGc1AH9JwT
BUZZSPROUT_API_KEY=176da6e94e51100209b5d39d0b91d520
BUZZSPROUT_PODCAST_ID=2598725
PODCAST_WEBSITE_URL=https://the-beacon.netlify.app
CARTESIA_API_KEY=sk_car_oHbuEyw9iUwZtZ96Lf9XQv
```

**Recommended:**
```
NEWS_API_KEY=9f9f71aa4e7f45d0bb5b11f678a034fd
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
```

### 4.2 Add audio assets

Place these in `assets/`:
```
intro_music.mp3    (8 seconds, royalty-free)
outro_music.mp3    (10 seconds, royalty-free)
cover_art.jpg      (exactly 3000×3000 pixels)
```

Free music: https://pixabay.com/music/ — search "news intro"
AI music: https://suno.com — prompt: *"Professional news podcast intro, 8 seconds, no vocals"*

---

## 5. Choosing Voices

### 5.1 Browse ElevenLabs
1. https://elevenlabs.io → Voice Library → filter: Premade, News
2. Add 3 voices to My Voices

### 5.2 What to listen for

**Alex Chen (Business anchor):** Authoritative, measured, confident. Male, American, News.

**Morgan Lee (Tech correspondent):** Warm, energetic, conversational. Female, neutral accent.

**Drew Vasquez (Crossover analyst):** Deliberate, gravitas, intelligent. Male, neutral.

### 5.3 Get Voice IDs
1. My Voices → click each voice → copy the **Voice ID**
2. Paste into `.env` as `ELEVENLABS_VOICE_ALEX`, etc.

### 5.4 Test a voice
```python
# python3 (with .venv active)
from elevenlabs import ElevenLabs
import os; from dotenv import load_dotenv; load_dotenv()
client = ElevenLabs(api_key=os.getenv("ELEVENLABS_API_KEY"))
audio = client.text_to_speech.convert(
    voice_id=os.getenv("ELEVENLABS_VOICE_ALEX"),
    text="Welcome to The Signal morning edition. I'm Alex Chen.",
    model_id="eleven_multilingual_v2"
)
with open("test_alex.mp3", "wb") as f:
    [f.write(c) for c in audio]
# Play test_alex.mp3
```

---

## 6. First Episode Test

### Step 1 — Run PM first (so AM has recap data)

```bash
source .venv/bin/activate

# PM dry run (no audio, ~$0.10)
python orchestrator.py --edition pm --dry-run

# Check the brief
cat outputs/briefs/brief_$(date +%Y-%m-%d)_pm.json | python3 -m json.tool | head -60

# Full PM episode (15-25 min)
python orchestrator.py --edition pm
```

### Step 2 — Run AM (now has PM memory for recap)

```bash
# AM dry run
python orchestrator.py --edition am --dry-run

# Check that yesterday_recap is populated
cat outputs/briefs/brief_$(date +%Y-%m-%d)_am.json | python3 -m json.tool | grep -A 20 yesterday_recap

# Full AM episode
python orchestrator.py --edition am
```

The episode titles will look like:
- `2026-02-24 AM - Markets Brace For Impact`
- `2026-02-24 PM - Fed Breaks From Script`

---

## 7. Going Live

Submit your Buzzsprout RSS feed to platforms:

1. **RSS URL:** Buzzsprout → Settings → RSS Feed → copy URL
2. **Apple Podcasts:** https://podcastsconnect.apple.com → Add Show (24–72hr review)
3. **Spotify:** https://podcasters.spotify.com → Submit podcast (24–48hr)
4. **Amazon Music:** https://podcasters.amazon.com → Submit (24–48hr)

---

## 8. Deploying the Website

### 8.1 Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/the-signal.git
git push -u origin main
```

### 8.2 Deploy to Netlify

1. https://netlify.com → **Add new site → Import from Git**
2. Connect GitHub → select `the-signal`
3. Build command: *(blank)*, Publish directory: `website`
4. Deploy

Every time GitHub Actions commits updated `episodes.json`, Netlify redeploys automatically. Both editions appear on the site.

### 8.3 Dashboard access

Open `website/dashboard.html` locally, or password-protect it in Netlify (Site settings → Access control).

---

## 9. GitHub Actions Automation

### 9.1 How the schedule works

The workflow has two cron triggers:
```yaml
- cron: '0 9  * * 1-5'    # 9 AM UTC = 4 AM EST → AM edition
- cron: '0 18 * * 1-5'    # 6 PM UTC = 1 PM EST → PM edition
```

The script auto-detects which edition based on UTC hour. Both editions run the same `orchestrator.py` with different `--edition` flags.

### 9.2 Add GitHub Secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**

**Required:**
| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | From console.anthropic.com |
| `ELEVENLABS_API_KEY` | From elevenlabs.io |
| `ELEVENLABS_VOICE_ALEX` | Voice ID from My Voices |
| `ELEVENLABS_VOICE_MORGAN` | Voice ID from My Voices |
| `ELEVENLABS_VOICE_DREW` | Voice ID from My Voices |
| `BUZZSPROUT_API_KEY` | From Buzzsprout account |
| `BUZZSPROUT_PODCAST_ID` | Number from Buzzsprout URL |
| `PODCAST_WEBSITE_URL` | Your Netlify URL |

**Recommended:**
| Secret | Value |
|--------|-------|
| `NEWS_API_KEY` | From newsapi.org |
| `SLACK_WEBHOOK_URL` | From Slack webhook setup |

### 9.3 Test automation

1. GitHub → **Actions** → **Daily Episodes** → **Run workflow**
2. Select edition: `am`, enable **Dry run**, click **Run workflow**
3. Watch live logs

### 9.4 Manual trigger via API (for dashboard buttons)

```bash
curl -X POST \
  -H "Authorization: token YOUR_GITHUB_PAT" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/repos/YOUR_USERNAME/the-signal/actions/workflows/daily_episode.yml/dispatches \
  -d '{"ref":"main","inputs":{"edition":"pm","dry_run":"true"}}'
```

---

## 10. Injecting Stories

### 10.1 CLI usage

```bash
source .venv/bin/activate

# Inject into both editions (default)
python agents/inject_stories.py \
  --url "https://techcrunch.com/2026/02/24/openai-raises-40b" \
  --priority must_include \
  --by "Alec"

# Target AM only (overnight story — inject before 4 AM)
python agents/inject_stories.py \
  --topic "TSMC Arizona fab yields" \
  --priority consider \
  --edition am \
  --note "Lead the overnight tech block"

# Target PM only (morning development — inject before 1 PM)
python agents/inject_stories.py \
  --text "Microsoft canceled three data center leases this morning." \
  --priority must_include \
  --edition pm \
  --note "Breaking — PM business block lead"

# View the queue
python agents/inject_stories.py --list
python agents/inject_stories.py --list --edition pm
```

### 10.2 Priority levels

| Level | Effect |
|-------|--------|
| `must_include` | Cannot be dropped. Triggers Slack alert. |
| `consider` | High-priority — in if it beats organic. |
| `background` | Context only — enriches related stories. |

### 10.3 Edition targeting

| Flag | Effect |
|------|--------|
| `--edition both` | Both AM and PM (default) |
| `--edition am` | 4:00 AM edition only |
| `--edition pm` | 1:00 PM edition only |

### 10.4 Deadlines

- **AM injections:** before 4:00 AM EST
- **PM injections:** before 1:00 PM EST

---

## 11. Editorial Dashboard

Open `website/dashboard.html` in your browser.

Features:
- View today's AM or PM brief with all stories expanded
- Inject via URL, text, or topic with edition selector (AM / PM / Both)
- See injection queue with priority and edition badges
- Trigger dry run or full episode (wired via GitHub API)
- Export brief as JSON

---

## 12. Sponsor Management

### 12.1 Slot timing

| Edition | Spot 1 | Spot 2 |
|---------|--------|--------|
| AM | 7:30 (Alex, post-recap) | 40:00 (Morgan) |
| PM | 15:00 (Alex, post-business) | 40:00 (Morgan) |

### 12.2 Add a sponsor

Create `data/sponsors_active.json`:
```json
[
  {
    "slot": "mid",
    "name": "Notion",
    "tagline": "Build your company wiki, beautifully.",
    "product_description": "Notion is the all-in-one workspace.",
    "cta": "Try free at notion.com/signal",
    "editions": ["am", "pm"],
    "start_date": "2026-02-24",
    "end_date": "2026-02-28"
  }
]
```

Set `"editions": ["pm"]` to run sponsor in the afternoon edition only (e.g., business-hours SaaS tools).

### 12.3 Without a sponsor

Both spots run house ads promoting the show (subscribe, review, tip a story). Slots never go silent.

---

## 13. Troubleshooting

**"AM has no yesterday recap"**
Normal on first run — no PM memory exists yet. Run the PM edition first:
```bash
python orchestrator.py --edition pm    # populates memory
python orchestrator.py --edition am    # now has recap data
```

**"PM is covering AM stories"**
Check that AM ran successfully and logged "Story memory updated." If AM failed mid-pipeline, memory may not have been written. Re-run AM with `--dry-run` to check, then run fully.

**"Edition auto-detect wrong when running locally"**
Always pass `--edition` explicitly when running locally:
```bash
python orchestrator.py --edition am
python orchestrator.py --edition pm
```
The clock-based auto-detect is only for the GitHub Actions environment.

**"Script too short"**
The overnight window (AM) has fewer breaking stories by design — AM naturally runs a bit leaner on the overnight block and compensates with the recap depth. If consistently short, the scriptwriter expand pass will add dialogue. Check logs for the final estimated duration.

**"FFmpeg not found on GitHub Actions"**
The workflow installs it via `apt-get`. If it fails, it's usually a temporary mirror issue — re-run the workflow.

**"Both editions uploading to wrong Buzzsprout slot"**
Both editions go to the same Buzzsprout podcast feed — they appear as separate episodes in chronological order, which is correct. Listeners get both AM and PM episodes in their feed. If you want separate feeds, create two Buzzsprout podcasts and use separate `BUZZSPROUT_PODCAST_ID` values per edition (requires code change in `publisher.py`).

---

## 14. Cost Breakdown

### Monthly at launch (~44 episodes/month, 2/day weekdays)

| Service | Plan | Monthly |
|---------|------|---------|
| Anthropic | Pay-per-use | $25–45 |
| ElevenLabs | Creator | $22 |
| Buzzsprout | Pro | $18 |
| NewsAPI | Free | $0 |
| GitHub | Free | $0 |
| Netlify | Free | $0 |
| **Total** | | **$65–85/month** |

### Revenue potential

With 2 episodes/day and 2 sponsor slots each (= 4 sponsor spots/day):
- 1,000 downloads/episode → ~$50 revenue/day at $25 CPM → break-even at ~1,700 downloads
- 5,000 downloads/episode → ~$250 revenue/day → ~$5,000/month profit
- 10,000 downloads/episode → ~$500 revenue/day → ~$13,000/month profit

---

## 15. File Reference

```
the-signal/
├── orchestrator.py              ← Main runner — --edition am or pm
├── setup.sh
├── requirements.txt
├── .env.example → .env          ← Your API keys
│
├── agents/
│   ├── curator.py               ← Edition-aware curation
│   │                               AM: 16hr window, pulls PM recap from memory
│   │                               PM: 10hr window, excludes AM stories
│   ├── scriptwriter.py          ← Edition-aware scripts
│   │                               AM: Recap segment + overnight blocks
│   │                               PM: Standard 7-story structure
│   ├── voice_producer.py        ← TTS + FFmpeg
│   ├── publisher.py             ← Buzzsprout + social
│   ├── publisher_website.py     ← episodes.json + RSS
│   ├── inject_stories.py        ← --edition am|pm|both flag
│   └── story_memory.py          ← SQLite with edition column
│                                   get_am_story_headlines() for PM exclusion
│                                   get_yesterday_pm_recap() for AM recap
│
├── config/show_config.json      ← Per-edition timing, sponsor slots
├── website/index.html           ← Public site (shows both editions)
├── website/dashboard.html       ← Private editorial dashboard
├── website/episodes.json        ← Auto-updated by pipeline
│
├── .github/workflows/
│   └── daily_episode.yml        ← 9 AM UTC (AM) + 6 PM UTC (PM) cron
│
├── outputs/
│   ├── briefs/brief_DATE_am.json, brief_DATE_pm.json
│   ├── scripts/script_DATE_am.txt, script_DATE_pm.txt
│   └── audio/episode_DATE_am.mp3, episode_DATE_pm.mp3
│
└── logs/
    ├── episode_DATE_am.log
    └── episode_DATE_pm.log
```

### Key commands

```bash
# Setup (once)
chmod +x setup.sh && ./setup.sh && source .venv/bin/activate

# Dry runs
python orchestrator.py --edition pm --dry-run
python orchestrator.py --edition am --dry-run

# Full episodes (run PM first to build recap memory for AM)
python orchestrator.py --edition pm
python orchestrator.py --edition am

# Injection examples
python agents/inject_stories.py --url "https://..." --priority must_include
python agents/inject_stories.py --topic "EU AI Act enforcement" --edition pm --priority consider
python agents/inject_stories.py --list --edition am

# Push to GitHub
git add . && git commit -m "Update" && git push
```

---

## 16. Quick Start Checklist

- [ ] Python 3.10+ installed
- [ ] FFmpeg installed
- [ ] Anthropic API key
- [ ] ElevenLabs Creator plan + API key
- [ ] 3 voices selected, Voice IDs copied
- [ ] Buzzsprout account + API key + Podcast ID
- [ ] NewsAPI key (free)
- [ ] GitHub private repo created
- [ ] `./setup.sh` run successfully
- [ ] `.env` filled in with all required keys
- [ ] `assets/intro_music.mp3` and `outro_music.mp3` added
- [ ] `assets/cover_art.jpg` added (3000×3000px)
- [ ] `python orchestrator.py --edition pm --dry-run` ✓
- [ ] `python orchestrator.py --edition pm` — first full PM episode ✓
- [ ] `python orchestrator.py --edition am --dry-run` — recap block shows PM stories ✓
- [ ] `python orchestrator.py --edition am` — full AM with recap ✓
- [ ] Episode titles formatted correctly (e.g., `2026-02-24 AM - Markets Brace For Impact`)
- [ ] Code pushed to GitHub
- [ ] All GitHub Secrets added (Required + Recommended)
- [ ] GitHub Actions AM dry-run test passed ✓
- [ ] GitHub Actions PM dry-run test passed ✓
- [ ] Website deployed to Netlify
- [ ] `PODCAST_WEBSITE_URL` updated in `.env` and GitHub Secrets
- [ ] RSS submitted to Apple Podcasts
- [ ] RSS submitted to Spotify
- [ ] Dashboard opens at `website/dashboard.html` ✓
- [ ] Both cron jobs visible in GitHub Actions schedule ✓

---

*Built with Claude. The Signal — autonomous journalism, twice daily.*
