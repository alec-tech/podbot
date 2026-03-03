"""
agents/show_loader.py — Multi-Show Configuration Loader

Single source of truth for show configuration. Each show lives in shows/{slug}/
with its own config, personas, feeds, prompts, and sponsors.

Usage:
    from agents.show_loader import load_show, list_shows
    show = load_show("example-show")
    show.name       # "Example Show"
    show.personas   # {...}
"""

import json
import logging
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("show_loader")

SHOWS_DIR = Path(__file__).parent.parent / "shows"


@dataclass
class ShowConfig:
    slug: str
    name: str
    config: dict = field(default_factory=dict)
    personas: dict = field(default_factory=dict)
    feeds: dict = field(default_factory=dict)
    prompts: dict = field(default_factory=dict)
    sponsors: list = field(default_factory=list)

    @property
    def editions(self) -> dict:
        return self.config.get("show", {}).get("editions", {})

    @property
    def valid_editions(self) -> tuple:
        return tuple(self.editions.keys())

    @property
    def edition_order(self) -> list:
        return self.config.get("show", {}).get("edition_order", list(self.editions.keys()))

    @property
    def voices(self) -> dict:
        return self.config.get("voices", {})

    @property
    def tts_config(self) -> dict:
        return self.config.get("tts", {})

    @property
    def audio_config(self) -> dict:
        return self.config.get("audio", {})

    @property
    def pipeline_config(self) -> dict:
        return self.config.get("pipeline", {})

    @property
    def story_quotas(self) -> dict:
        return self.config.get("show", {}).get("story_quotas", {
            "general_stories": 3, "topic_stories": 2,
        })

    @property
    def topic_domains(self) -> list:
        return self.config.get("show", {}).get("topic_domains", ["general"])

    @property
    def newsapi_config(self) -> dict:
        return self.config.get("show", {}).get("newsapi", {
            "mode": "categories",
            "categories": ["general"],
        })

    @property
    def source_tiers(self) -> dict:
        return self.config.get("show", {}).get("source_tiers", {})

    @property
    def tagline(self) -> str:
        return self.config.get("show", {}).get("tagline", "")

    @property
    def description(self) -> str:
        return self.config.get("show", {}).get("description", "")

    @property
    def category(self) -> str:
        cat = self.config.get("show", {}).get("category", "News")
        sub = self.config.get("show", {}).get("subcategory", "")
        return f"{cat} > {sub}" if sub else cat

    @property
    def language(self) -> str:
        return self.config.get("show", {}).get("language", "en")

    @property
    def rotating_hosts(self) -> list:
        return [k for k, v in self.personas.items() if v.get("type") == "rotating"]

    @property
    def static_hosts(self) -> list:
        return [k for k, v in self.personas.items() if v.get("type") == "static"]

    # ── Path helpers ──────────────────────────────────────────────────────────

    @property
    def show_dir(self) -> Path:
        return SHOWS_DIR / self.slug

    def output_dir(self, subdir: str = "") -> Path:
        p = Path("outputs") / self.slug / subdir
        p.mkdir(parents=True, exist_ok=True)
        return p

    def database_dir(self) -> Path:
        p = Path("database") / self.slug
        p.mkdir(parents=True, exist_ok=True)
        return p

    def data_dir(self) -> Path:
        p = Path("data") / self.slug
        p.mkdir(parents=True, exist_ok=True)
        return p

    def log_dir(self) -> Path:
        p = Path("logs") / self.slug
        p.mkdir(parents=True, exist_ok=True)
        return p

    def website_dir(self) -> Path:
        p = Path("website") / self.slug
        p.mkdir(parents=True, exist_ok=True)
        return p


def _resolve_default_show() -> str:
    """Pick the first available show slug, or raise a helpful error."""
    shows = list_shows()
    if not shows:
        raise FileNotFoundError(
            "No shows found. Create one in shows/{slug}/ with a show.json, "
            "or use the admin wizard at http://localhost:8000."
        )
    return shows[0]


def load_show(slug: str = None) -> ShowConfig:
    """Load a show's full configuration from shows/{slug}/."""
    if slug is None:
        slug = _resolve_default_show()
    show_dir = SHOWS_DIR / slug
    if not show_dir.exists():
        raise FileNotFoundError(f"Show directory not found: {show_dir}")

    # Load show.json
    config = _load_json(show_dir / "show.json")
    name = config.get("show", {}).get("name", slug)

    # Load personas.json
    personas = _load_json(show_dir / "personas.json")

    # Load feeds.json
    feeds = _load_json(show_dir / "feeds.json")

    # Load sponsors.json
    sponsors_path = show_dir / "sponsors.json"
    sponsors = _load_json(sponsors_path).get("sponsors", []) if sponsors_path.exists() else []

    # Load prompt templates
    prompts = {}
    prompts_dir = show_dir / "prompts"
    if prompts_dir.exists():
        for f in prompts_dir.glob("*.txt"):
            prompts[f.stem] = f.read_text()

    show = ShowConfig(
        slug=slug,
        name=name,
        config=config,
        personas=personas,
        feeds=feeds,
        prompts=prompts,
        sponsors=sponsors,
    )

    log.info(f"Loaded show: {name} ({slug}) — {len(show.valid_editions)} editions, "
             f"{len(personas)} hosts, {sum(len(v) for v in feeds.values())} feeds")
    return show


def list_shows() -> list[str]:
    """Return slugs for all available shows."""
    if not SHOWS_DIR.exists():
        return []
    return sorted(
        d.name for d in SHOWS_DIR.iterdir()
        if d.is_dir() and (d / "show.json").exists()
    )


def save_show_config(slug: str, section: str, data) -> Path:
    """
    Write a config section back to disk.

    section: "config" -> show.json, "personas" -> personas.json,
             "feeds" -> feeds.json, "sponsors" -> sponsors.json,
             "prompts/{name}" -> prompts/{name}.txt
    """
    show_dir = SHOWS_DIR / slug
    show_dir.mkdir(parents=True, exist_ok=True)

    if section == "config":
        path = show_dir / "show.json"
        _save_json(data, path)
    elif section == "personas":
        path = show_dir / "personas.json"
        _save_json(data, path)
    elif section == "feeds":
        path = show_dir / "feeds.json"
        _save_json(data, path)
    elif section == "sponsors":
        path = show_dir / "sponsors.json"
        _save_json(data, path)
    elif section.startswith("prompts/"):
        name = section.split("/", 1)[1]
        prompts_dir = show_dir / "prompts"
        prompts_dir.mkdir(exist_ok=True)
        path = prompts_dir / f"{name}.txt"
        path.write_text(data if isinstance(data, str) else str(data))
    else:
        raise ValueError(f"Unknown config section: {section}")

    log.info(f"Saved {slug}/{section}: {path}")
    return path


def show_exists(slug: str) -> bool:
    """Check if a show directory already exists."""
    return (SHOWS_DIR / slug / "show.json").exists()


def validate_slug(slug: str) -> str | None:
    """Validate a show slug. Returns error message or None if valid."""
    if not slug:
        return "Slug is required"
    if len(slug) < 3 or len(slug) > 50:
        return "Slug must be 3-50 characters"
    if not re.match(r"^[a-z0-9-]+$", slug):
        return "Slug must contain only lowercase letters, numbers, and hyphens"
    if slug.startswith("-") or slug.endswith("-"):
        return "Slug must not start or end with a hyphen"
    return None


def create_show(slug: str, config: dict, personas: dict, feeds: dict,
                prompts: dict, sponsors: list | None = None) -> ShowConfig:
    """
    Create a new show by writing all config files to shows/{slug}/.

    Initializes website/{slug}/episodes.json as [] and creates empty sponsors
    if none provided. Raises FileExistsError if slug already exists.
    """
    err = validate_slug(slug)
    if err:
        raise ValueError(err)

    show_dir = SHOWS_DIR / slug
    if show_dir.exists():
        raise FileExistsError(f"Show already exists: {slug}")

    # Create show directory structure
    show_dir.mkdir(parents=True)
    prompts_dir = show_dir / "prompts"
    prompts_dir.mkdir()

    # Write show.json
    _save_json(config, show_dir / "show.json")

    # Write personas.json
    _save_json(personas, show_dir / "personas.json")

    # Write feeds.json
    _save_json(feeds, show_dir / "feeds.json")

    # Write sponsors.json
    _save_json({"sponsors": sponsors or []}, show_dir / "sponsors.json")

    # Write prompt templates
    for name, text in prompts.items():
        (prompts_dir / f"{name}.txt").write_text(text)

    # Initialize website directory with empty episodes.json
    website_dir = Path("website") / slug
    website_dir.mkdir(parents=True, exist_ok=True)
    episodes_path = website_dir / "episodes.json"
    if not episodes_path.exists():
        _save_json([], episodes_path)

    log.info(f"Created new show: {config.get('show', {}).get('name', slug)} ({slug})")
    return load_show(slug)


def delete_show(slug: str):
    """Remove a show's config directory. Does NOT remove outputs/database/website data."""
    import shutil
    show_dir = SHOWS_DIR / slug
    if not show_dir.exists():
        raise FileNotFoundError(f"Show not found: {slug}")
    shutil.rmtree(show_dir)
    log.info(f"Deleted show: {slug}")


def build_default_config(
    name: str,
    slug: str,
    tagline: str = "",
    description: str = "",
    category: str = "News",
    subcategory: str = "",
    topic_domains: list | None = None,
    story_quotas: dict | None = None,
    newsapi: dict | None = None,
    editions: dict | None = None,
    hosts: list | None = None,
) -> dict:
    """
    Build a complete show.json dict from wizard input with smart defaults.

    Returns a dict ready to be written as show.json.
    """
    topic_domains = topic_domains or ["general"]
    hosts = hosts or []

    # Default story quotas: 2 + 1 + 2 pattern
    if not story_quotas:
        if len(topic_domains) >= 2:
            story_quotas = {
                f"{topic_domains[0]}_stories": 2,
                "crossover_stories": 1,
                f"{topic_domains[1]}_stories": 2,
            }
        else:
            story_quotas = {f"{topic_domains[0]}_stories": 3, "general_stories": 2}

    # Default edition
    if not editions:
        editions = {
            "daily": {
                "publish_time_est": "06:00",
                "publish_time_utc": "11:00",
                "target_duration_minutes": 12,
                "min_duration_minutes": 10,
                "max_duration_minutes": 15,
                "title_format": "{date} - {hook}",
                "news_window_hours": 24,
                "includes_recap": False,
            }
        }
    else:
        # Ensure all editions have required fields with defaults
        for ed_name, ed in editions.items():
            ed.setdefault("target_duration_minutes", 12)
            ed.setdefault("min_duration_minutes", 10)
            ed.setdefault("max_duration_minutes", 15)
            ed.setdefault("title_format", "{date} - {hook}")
            ed.setdefault("news_window_hours", 24)
            ed.setdefault("includes_recap", False)
            # Auto-compute UTC from EST if not provided
            if "publish_time_est" in ed and "publish_time_utc" not in ed:
                h, m = ed["publish_time_est"].split(":")
                utc_h = (int(h) + 5) % 24  # EST -> UTC (+5)
                ed["publish_time_utc"] = f"{utc_h:02d}:{m}"

    # Default NewsAPI config
    if not newsapi:
        if topic_domains and topic_domains[0] not in ("business", "technology", "science", "health", "sports", "entertainment", "general"):
            # Niche topic — use keyword search
            newsapi = {
                "mode": "keywords",
                "queries": [f"{d} news" for d in topic_domains[:4]],
            }
        else:
            newsapi = {
                "mode": "categories",
                "categories": [d for d in topic_domains[:2] if d in (
                    "business", "technology", "science", "health", "sports", "entertainment", "general"
                )] or ["general"],
            }

    # Build host names list
    host_names = [h["name"] for h in hosts]

    # Build voices dict from host data
    voices = {}
    for h in hosts:
        key = h.get("key") or h["name"].split()[0].lower()
        voice_entry = {
            "description": h.get("role", "Host"),
            "type": h.get("type", "static"),
        }
        if h.get("topic_keywords"):
            voice_entry["topic_keywords"] = h["topic_keywords"]
        # Build provider configs
        providers = {}
        for provider_cfg in h.get("voice_providers", []):
            provider = provider_cfg["provider"]
            if provider == "openai":
                providers["openai"] = {
                    "voice_id": provider_cfg.get("voice_id", "alloy"),
                    "model": "gpt-4o-mini-tts",
                    "instructions": provider_cfg.get("instructions", h.get("role", "Natural podcast host.")),
                }
            elif provider == "cartesia":
                providers["cartesia"] = {
                    "voice_id": provider_cfg.get("voice_id", ""),
                    "model_id": "sonic-3",
                    "speed": provider_cfg.get("speed", 1.0),
                }
            elif provider == "elevenlabs":
                providers["elevenlabs"] = {
                    "voice_id": provider_cfg.get("voice_id", ""),
                    "stability": 0.50,
                    "similarity_boost": 0.75,
                    "style": 0.40,
                }
        # Default to OpenAI if no providers specified
        if not providers:
            providers["openai"] = {
                "voice_id": "alloy",
                "model": "gpt-4o-mini-tts",
                "instructions": h.get("role", "Natural podcast host."),
            }
        voice_entry["providers"] = providers
        voices[key] = voice_entry

    # Determine TTS provider order from what hosts have configured
    all_providers = set()
    for v in voices.values():
        all_providers.update(v.get("providers", {}).keys())
    # OpenAI first for new shows (easiest setup)
    provider_order = []
    for p in ["openai", "cartesia", "elevenlabs"]:
        if p in all_providers:
            provider_order.append(p)

    config = {
        "show": {
            "name": name,
            "tagline": tagline,
            "description": description,
            "host_names": host_names,
            "sponsor_slots": 3,
            "language": "en",
            "explicit": False,
            "category": category,
            "subcategory": subcategory,
            "topic_domains": topic_domains,
            "story_quotas": story_quotas,
            "edition_order": list(editions.keys()),
            "newsapi": newsapi,
            "source_tiers": {"tier1": [], "tier2": []},
            "editions": editions,
        },
        "voices": voices,
        "tts": {
            "provider_order": provider_order or ["openai"],
            "retries_per_provider": [3] + [2] * (len(provider_order) - 1) if len(provider_order) > 1 else [3],
        },
        "audio": {
            "output_format": "mp3",
            "bitrate": "192k",
            "sample_rate": 44100,
            "target_lufs": -16,
            "true_peak_dbtp": -1.5,
            "intro_music_duration_seconds": 8,
            "outro_music_duration_seconds": 10,
            "silence_between_lines_seconds": 0.35,
        },
        "pipeline": {
            "min_duration_minutes": 10,
            "max_duration_minutes": 15,
            "target_duration_minutes": 12,
            "retry_attempts": 3,
            "story_cooldown_days": 3,
            "fallback_to_previous_brief": True,
            "stories_per_episode": sum(story_quotas.values()),
            "wpm": 140,
            "audio_min_duration_minutes": 7,
            "audio_max_duration_minutes": 18,
        },
    }
    return config


def build_default_personas(hosts: list) -> dict:
    """Build a personas.json dict from wizard host data."""
    personas = {}
    for h in hosts:
        key = h.get("key") or h["name"].split()[0].lower()
        persona = {
            "name": h["name"],
            "role": h.get("role", "Host"),
            "type": h.get("type", "static"),
            "personality": h.get("personality", ""),
            "speech_patterns": h.get("speech_patterns", []),
            "avoid": h.get("avoid", []),
        }
        if h.get("topic_keywords"):
            persona["topic_keywords"] = h["topic_keywords"]
        personas[key] = persona
    return personas


# ─── Default prompt templates for new shows ───────────────────────────────────

DEFAULT_CURATOR_PROMPT = """You are the senior editorial producer for "{show_name}," a {show_tagline} podcast.

You are curating the {edition_label} EDITION ({publish_time} EST). All editions follow the same format:
  * {target_duration} minutes of content ({total_stories} stories)
  * {quota_block}
  * Each story ~2 minutes

TOPIC FOCUS: This show covers {topic_summary}. Only select stories relevant to these domains.

EDITION TONE: Concise, conversational, and smart. Each story gets a punchy headline, key context,
and one sharp insight. Keep it moving — the listener wants the signal, not the noise.

STORY QUOTAS (strict):
{quota_block}
Total: {total_stories} stories, all uniform format

HOOK: Generate a 3-5 word punchy episode hook.
  Good examples: "Markets Open Under Pressure" / "AI Chips Change Everything"
  Bad examples: "Daily Edition Episode" / "Today's News"

PRIORITY RULES:
  MUST_INCLUDE injected stories -> always include, improve framing, never drop
  CONSIDER injected stories     -> high-priority tip, include if stronger than organic option
  BACKGROUND injected stories   -> use as context only

DEDUPLICATION:
  Do NOT cover stories from the last 3 days unless a major new development warrants UPDATE: framing.
  If earlier editions today covered a story, you MAY revisit it with UPDATE framing if there are
  significant new developments. Otherwise, find fresh stories.

OUTPUT: Valid JSON only, exact schema below."""

DEFAULT_SCRIPTWRITER_PROMPT = """You are the head writer for "{show_name}," a {show_tagline} podcast.

{edition_label} EDITION ({publish_time} EST) — {target_minutes} minutes target (~{word_target} words spoken at {wpm} wpm)

EDITION IDENTITY — CRITICAL:
This is the {edition_word} edition. Hosts MUST say "{edition_word} edition" in the intro.
NEVER call this the "morning edition" or "morning episode" unless this IS the morning edition.

HOSTS: {static_host_1} ({static_role_1}) and {static_host_2} ({static_role_2}) are in every episode.
The crossover host for this episode is {guest_name} ({guest_role}).

STRUCTURE:

[PRE-INTRO SPONSOR — 0:00–0:30 — ~70 words]  (if sponsor provided for this slot)
The designated host reads the provided sponsor script verbatim. Format: [HOST_NAME - reading sponsor]: "script text"

[INTRO — 0:30–1:00 — ~70 words]
Quick, energetic open. "Welcome to {show_name} {edition_word} edition." Date and episode number, fast.
Introduce today's crossover guest briefly.

[POST-INTRO SPONSOR — 1:00–1:30 — ~70 words]  (if sponsor provided for this slot)
The designated host reads the provided sponsor script verbatim. Format: [HOST_NAME - reading sponsor]: "script text"

{content_blocks}

[PRE-OUTRO SPONSOR — {pre_outro_timestamp} — ~70 words]  (if sponsor provided for this slot)
The designated host reads the provided sponsor script verbatim. Format: [HOST_NAME - reading sponsor]: "script text"

[WRAP + SIGNOFF — {signoff_start}–{target_minutes}:00 — ~140 words]
What to watch next. Quick callback to the sharpest exchange.
Warm but quick signoff.

NATURALNESS — THIS IS CRITICAL:
The listener should NOT feel like the hosts are reading from a script. Write dialogue that
sounds like smart people talking to each other over coffee.
- Use contractions always (it's, don't, we're, that's)
- Incomplete thoughts are fine: "So the thing about this is—" "Right, exactly."
- Reactions mid-sentence: "Wait, hold on—" "Yeah so—" "Okay but—"
- Let hosts interrupt each other naturally
- Short sentences. Fragments are fine. "Big number." "Not great." "Classic move."
- Avoid formal transitions. No "Moving on to our next story" — just pivot naturally.
- Sprinkle in casual filler: "I mean," "look," "honestly," "here's the thing"

DIALOGUE RULES:
- NEVER: "Great point," "Absolutely," "Exactly," "That's fascinating," "Good question"
- NEVER: formal transitions, segment announcements, reading-from-a-script energy
- DO: interruptions, half-sentences, "Hold on—", "Actually—", real tension
- 2+ data points per story. At least 2 genuine disagreements total.

SPOKEN TEXT ONLY — CRITICAL:
Everything inside the quotation marks after the colon is sent directly to a text-to-speech engine.
If you put a direction inside the quotes, the AI voice will literally read it aloud.

WRONG — direction leaks into audio:
  [HOST - laughing]: "(laughs) That number is absurd."
  [HOST - excited]: "*turning to someone* You need to see these numbers."

CORRECT — direction stays in brackets, quotes contain only spoken words:
  [HOST - laughing]: "That number is absurd."
  [HOST - excited]: "You need to see these numbers."

NO parenthetical directions (laughs), NO bracketed directions [beat], NO asterisk actions *sighs*,
NO bare direction words like "laughs" or "chuckles" at the start of dialogue.
All acting cues go ONLY in the bracket before the colon: [HOST - direction]: "dialogue"
The quotes contain ONLY words the host says out loud.

SPONSOR RULES:
- Sponsors specify a "voice" and a "script" field. Use the designated host and read the script verbatim.
- Only include sponsor spots for slots that have sponsors provided. Skip empty slots.

FORMAT: [HOST_NAME - acting direction]: "dialogue"
Return complete script only. No headers or commentary outside the script."""

DEFAULT_PUBLISHER_PROMPT = """Generate metadata for today's podcast episode.

Show: {show_name}
Episode: {episode_num} ({edition_label} edition)
Date: {episode_date}
Theme: {show_theme}
Stories covered: {story_titles}

Generate a JSON object with these keys:
1. TITLE: A compelling, concise episode title (max 80 chars). This should be an overarching tagline that captures the theme across the stories discussed. Do NOT include the date, episode number, or edition name — just a punchy headline.
2. DESCRIPTION: 200-250 word show notes. Include: what we cover, why it matters, approximate timestamps, keywords for SEO. No fluff.
3. CHAPTERS: List with timestamps (approximate based on {target_minutes}-min show structure)
4. TAGS: 8-10 relevant tags for podcast directories
5. TWEET: 240 char tweet announcing the episode (include 3 key topics, no hashtag spam)
6. LINKEDIN_POST: 3-4 sentence professional LinkedIn announcement

Return as JSON."""


class SafeFormatter(string.Formatter):
    """A string formatter that leaves unknown {variables} intact instead of raising KeyError.

    This allows existing show-specific templates to keep working unchanged while
    generic templates can use additional variables.
    """
    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            return kwargs.get(key, "{" + key + "}")
        return super().get_value(key, args, kwargs)

    def format_field(self, value, format_spec):
        if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            return value
        return super().format_field(value, format_spec)


safe_format = SafeFormatter().format


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_json(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
