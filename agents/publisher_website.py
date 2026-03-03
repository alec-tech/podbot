"""
agents/publisher_website.py v5 — Multi-Show Website Data Export
Generates episodes.json consumed by the podcast website
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic

log = logging.getLogger("publisher_website")


def _get_client():
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generate_episode_json(brief: dict, script_data: dict, metadata: dict,
                          audio_url: str, episode_num: int, episode_date: str,
                          edition: str = "morning", show=None) -> dict:
    """
    Generate the episode JSON record for the website.
    """
    sponsors = brief.get("sponsors", script_data.get("sponsors", []))
    companies = extract_companies_from_brief(brief, show)
    chapters = build_chapters(sponsors, show)

    duration_seconds = int(script_data.get("estimated_minutes", 12) * 60)
    mins = duration_seconds // 60
    secs = duration_seconds % 60

    # Build story data from configured categories
    story_data = {}
    if show:
        for cat_key in show.story_quotas.keys():
            story_data[cat_key] = format_stories_for_web(brief.get(cat_key, []))
    else:
        story_data = {}

    result = {
        "id": episode_num,
        "episode_num": episode_num,
        "date": episode_date,
        "edition": edition,
        "title": metadata.get("TITLE", f"Episode {episode_num}"),
        "description": metadata.get("DESCRIPTION", "")[:300],
        "audio_url": audio_url,
        "duration_seconds": duration_seconds,
        "duration_display": f"{mins}:{secs:02d}",
        "theme": brief.get("show_theme", ""),
        "categories": determine_categories(brief, show),
        "sponsors": format_sponsors_for_web(sponsors),
        "chapters": chapters,
        **story_data,
        "companies": companies,
        "crossover_host": script_data.get("crossover_host", ""),
        "transcript_url": metadata.get("TRANSCRIPT_URL", ""),
        "tags": metadata.get("TAGS", []),
        "created_at": datetime.now().isoformat()
    }

    if show:
        result["show"] = show.slug

    return result


def build_chapters(sponsors: list, show=None) -> list:
    chapters = []

    pre_intro = next((s for s in sponsors if s.get("slot") == "pre-intro"), None)
    post_intro = next((s for s in sponsors if s.get("slot") == "post-intro"), None)
    pre_outro = next((s for s in sponsors if s.get("slot") == "pre-outro"), None)

    t = 0
    if pre_intro and pre_intro.get("name") != "SPONSOR_PLACEHOLDER":
        chapters.append({"time": t, "label": f"Pre-Intro: {pre_intro['name']}"})
        t = 30

    chapters.append({"time": t, "label": "Intro"})
    t = max(t + 30, 30)

    if post_intro and post_intro.get("name") != "SPONSOR_PLACEHOLDER":
        chapters.append({"time": t, "label": f"Post-Intro: {post_intro['name']}"})
        t += 30

    # Build content block chapters dynamically from story quotas
    if show:
        items = list(show.story_quotas.items())
        mid_idx = len(items) // 2
        for i, (cat_key, count) in enumerate(items):
            label = cat_key.replace("_stories", "").replace("_", " ").title()
            if i == mid_idx and len(items) > 1:
                label += " (Crossover)"
            chapters.append({"time": t, "label": f"{label} Block"})
            t += count * 120  # ~2 min per story
    else:
        chapters.append({"time": t, "label": "Stories"})
        t += 540

    if pre_outro and pre_outro.get("name") != "SPONSOR_PLACEHOLDER":
        chapters.append({"time": t, "label": f"Pre-Outro: {pre_outro['name']}"})
        chapters.append({"time": t + 30, "label": "Wrap & Signoff"})
    else:
        chapters.append({"time": t, "label": "Wrap & Signoff"})

    return chapters


def determine_categories(brief: dict, show=None) -> list:
    if show:
        cats = []
        for cat_key in show.story_quotas.keys():
            if brief.get(cat_key):
                cats.append(cat_key.replace("_stories", ""))
        return cats
    return ["general"]


def extract_companies_from_brief(brief: dict, show=None) -> list:
    """Extract all company names from the brief using Claude"""
    text_parts = [str(brief.get("show_theme", ""))]

    if show:
        for cat_key in show.story_quotas.keys():
            text_parts.append(
                " ".join(s.get("podcast_headline","") + " " + s.get("context","")
                         for s in brief.get(cat_key, []))
            )
    else:
        pass  # No show config — use just the theme text

    all_text = " ".join(text_parts)[:3000]

    response = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Extract all company and organization names from this text.
Return ONLY a JSON array of strings, no commentary.
Only include real organizations (not generic terms like 'startup' or 'company').
Max 20 companies. Sort by prominence in the text.

TEXT: {all_text}"""
        }]
    )

    text = response.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
        if text.startswith("json"):
            text = text[4:].strip()

    try:
        return json.loads(text)
    except Exception:
        return []


def format_stories_for_web(stories: list) -> list:
    return [{
        "headline": s.get("podcast_headline", s.get("headline", "")),
        "excerpt": s.get("context", s.get("summary", ""))[:300],
    } for s in stories[:3]]


def format_sponsors_for_web(sponsors: list) -> list:
    return [{
        "slot": s.get("slot", "pre-outro"),
        "name": s.get("name", ""),
        "tagline": s.get("tagline", ""),
        "url": s.get("url", "#"),
        "logo_text": s.get("logo_text", s.get("name", "?")[:1].upper())
    } for s in sponsors if s.get("name") and s.get("name") != "SPONSOR_PLACEHOLDER"]


def update_episodes_json(new_episode: dict, show=None,
                         json_path: str = None):
    """Add new episode to episodes.json and save."""
    if json_path is None:
        if show:
            json_path = str(show.website_dir() / "episodes.json")
        else:
            json_path = "website/episodes.json"

    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)

    if json_file.exists():
        with open(json_file) as f:
            episodes = json.load(f)
    else:
        episodes = []

    episodes = [e for e in episodes if e.get("episode_num") != new_episode["episode_num"]]
    episodes.insert(0, new_episode)
    episodes = episodes[:200]

    with open(json_file, "w") as f:
        json.dump(episodes, f, indent=2)

    log.info(f"  Updated episodes.json — {len(episodes)} total episodes")
    return json_file


def generate_rss_feed(episodes: list, show=None, config: dict = None,
                      output_path: str = None):
    """Generate a full RSS 2.0 podcast feed from episode data"""
    from xml.sax.saxutils import escape

    if output_path is None:
        if show:
            output_path = str(show.website_dir() / "feed.xml")
        else:
            output_path = "website/feed.xml"

    if config is None and show:
        config = {
            "name": show.name,
            "description": show.description,
            "website_url": os.getenv("PODCAST_WEBSITE_URL", ""),
        }
    elif config is None:
        config = {
            "name": "Podcast",
            "description": "",
            "website_url": "",
        }

    items = []
    for ep in episodes:
        duration_str = ep.get("duration_display", "12:00")
        ep_num = ep.get("episode_num", 0)
        guid_prefix = (show.slug if show else "episode").replace("-", "")
        items.append(f"""
    <item>
      <title>{escape(ep['title'])}</title>
      <description><![CDATA[{ep['description']}]]></description>
      <enclosure url="{ep['audio_url']}" length="0" type="audio/mpeg"/>
      <guid isPermaLink="false">{guid_prefix}-ep-{ep_num}</guid>
      <pubDate>{format_rss_date(ep['date'])}</pubDate>
      <itunes:episode>{ep_num}</itunes:episode>
      <itunes:duration>{duration_str}</itunes:duration>
      <itunes:summary>{escape(ep['description'])}</itunes:summary>
    </item>""")

    show_category = show.category if show else "News > Business News"
    cat_parts = show_category.split(" > ")
    cat_xml = f'<itunes:category text="{escape(cat_parts[0])}">'
    if len(cat_parts) > 1:
        cat_xml += f'\n      <itunes:category text="{escape(cat_parts[1])}"/>'
    cat_xml += "\n    </itunes:category>"

    author = config.get("name", show.name if show else "Podcast")
    explicit = "false"
    if show:
        explicit = "true" if show.config.get("show", {}).get("explicit", False) else "false"

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{escape(config.get('name', 'Podcast'))}</title>
    <description>{escape(config.get('description', ''))}</description>
    <link>{config.get('website_url', '')}</link>
    <language>en-us</language>
    <itunes:author>{escape(author)}</itunes:author>
    {cat_xml}
    <itunes:explicit>{explicit}</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    {''.join(items)}
  </channel>
</rss>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(rss)
    log.info(f"  Generated RSS feed: {output_path}")


def format_rss_date(date_str: str) -> str:
    from email.utils import formatdate
    from datetime import datetime
    import time
    d = datetime.strptime(date_str, "%Y-%m-%d")
    return formatdate(time.mktime(d.timetuple()))
