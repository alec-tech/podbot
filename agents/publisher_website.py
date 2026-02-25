"""
agents/publisher_website.py — Website Data Export Extension
Generates episodes.json consumed by the podcast website
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from anthropic import Anthropic

log = logging.getLogger("publisher_website")
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def generate_episode_json(brief: dict, script_data: dict, metadata: dict,
                          audio_url: str, episode_num: int, episode_date: str,
                          edition: str = "morning") -> dict:
    """
    Generate the episode JSON record for the website.
    Extracts companies, builds chapters, structures all story data.
    """
    sponsors = brief.get("sponsors", script_data.get("sponsors", []))

    # Extract companies from all stories
    companies = extract_companies_from_brief(brief)

    # Build chapter list based on unified show structure
    chapters = build_chapters(sponsors)

    # Estimate duration in seconds (12 min default for all editions)
    duration_seconds = int(script_data.get("estimated_minutes", 12) * 60)
    mins = duration_seconds // 60
    secs = duration_seconds % 60

    return {
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
        "categories": determine_categories(brief),
        "sponsors": format_sponsors_for_web(sponsors),
        "chapters": chapters,
        "business_stories": format_stories_for_web(brief.get("business_stories", [])),
        "overlap_stories": format_stories_for_web(brief.get("overlap_stories", [])),
        "tech_stories": format_stories_for_web(brief.get("tech_stories", [])),
        "companies": companies,
        "crossover_host": script_data.get("crossover_host", ""),
        "transcript_url": metadata.get("TRANSCRIPT_URL", ""),
        "tags": metadata.get("TAGS", []),
        "created_at": datetime.now().isoformat()
    }


def build_chapters(sponsors: list) -> list:
    """Build chapter timestamps based on unified show structure (all editions: ~12 min)"""
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

    chapters.append({"time": t, "label": "Business Block"})
    chapters.append({"time": t + 180, "label": "Crossover Segment"})
    chapters.append({"time": t + 360, "label": "Tech Block"})

    pre_outro_time = t + 540
    if pre_outro and pre_outro.get("name") != "SPONSOR_PLACEHOLDER":
        chapters.append({"time": pre_outro_time, "label": f"Pre-Outro: {pre_outro['name']}"})
        chapters.append({"time": pre_outro_time + 30, "label": "Wrap & Signoff"})
    else:
        chapters.append({"time": pre_outro_time, "label": "Wrap & Signoff"})

    return chapters


def determine_categories(brief: dict) -> list:
    cats = ["business", "tech"]
    if brief.get("overlap_stories"):
        cats.append("overlap")
    return cats


def extract_companies_from_brief(brief: dict) -> list:
    """Extract all company names from the brief using Claude"""
    all_text = " ".join([
        str(brief.get("show_theme", "")),
        " ".join(s.get("podcast_headline","") + " " + s.get("context","") for s in brief.get("business_stories",[])),
        " ".join(s.get("podcast_headline","") + " " + s.get("context","") for s in brief.get("tech_stories",[])),
        " ".join(s.get("podcast_headline","") + " " + s.get("context","") for s in brief.get("overlap_stories",[])),
    ])[:3000]

    response = client.messages.create(
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
    except:
        # Fallback: simple extraction
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


def update_episodes_json(new_episode: dict, json_path: str = "website/episodes.json"):
    """
    Add new episode to episodes.json and save.
    Keeps most recent 200 episodes. Used by the website.
    """
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)

    if json_file.exists():
        with open(json_file) as f:
            episodes = json.load(f)
    else:
        episodes = []

    # Remove existing entry for same episode_num if re-running
    episodes = [e for e in episodes if e.get("episode_num") != new_episode["episode_num"]]

    # Prepend new episode (newest first)
    episodes.insert(0, new_episode)

    # Keep last 200 episodes max
    episodes = episodes[:200]

    with open(json_file, "w") as f:
        json.dump(episodes, f, indent=2)

    log.info(f"  Updated episodes.json — {len(episodes)} total episodes")
    return json_file


def generate_rss_feed(episodes: list, config: dict, output_path: str = "website/feed.xml"):
    """Generate a full RSS 2.0 podcast feed from episode data"""
    from xml.sax.saxutils import escape

    items = []
    for ep in episodes:
        duration_str = ep.get("duration_display", "12:00")
        items.append(f"""
    <item>
      <title>{escape(ep['title'])}</title>
      <description><![CDATA[{ep['description']}]]></description>
      <enclosure url="{ep['audio_url']}" length="0" type="audio/mpeg"/>
      <guid isPermaLink="false">signal-ep-{ep['episode_num']}</guid>
      <pubDate>{format_rss_date(ep['date'])}</pubDate>
      <itunes:episode>{ep['episode_num']}</itunes:episode>
      <itunes:duration>{duration_str}</itunes:duration>
      <itunes:summary>{escape(ep['description'])}</itunes:summary>
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
  xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{escape(config.get('name', 'The Signal'))}</title>
    <description>{escape(config.get('description', 'Three-daily business, tech, and policy news, curated by AI'))}</description>
    <link>{config.get('website_url', '')}</link>
    <language>en-us</language>
    <itunes:author>The Signal</itunes:author>
    <itunes:category text="News">
      <itunes:category text="Business News"/>
    </itunes:category>
    <itunes:explicit>false</itunes:explicit>
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
