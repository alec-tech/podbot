"""
agents/show_loader.py — Multi-Show Configuration Loader

Single source of truth for show configuration. Each show lives in shows/{slug}/
with its own config, personas, feeds, prompts, and sponsors.

Usage:
    from agents.show_loader import load_show, list_shows
    show = load_show("the-signal")
    show.name  # "The Signal"
    show.personas["chuck"]["name"]  # "Chuck Leblanc"
"""

import json
import logging
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
            "business_stories": 2, "overlap_stories": 1, "tech_stories": 2,
        })

    @property
    def topic_domains(self) -> list:
        return self.config.get("show", {}).get("topic_domains", ["business", "tech", "policy"])

    @property
    def newsapi_config(self) -> dict:
        return self.config.get("show", {}).get("newsapi", {
            "mode": "categories",
            "categories": ["business", "technology"],
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


def load_show(slug: str = "the-signal") -> ShowConfig:
    """Load a show's full configuration from shows/{slug}/."""
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
