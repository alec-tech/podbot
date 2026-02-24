"""
agents/publisher.py — Agent 4: Publishing and Syndication
Uploads episode to Buzzsprout, generates metadata, posts to social
"""

import os
import re
import json
import logging
import requests
from anthropic import Anthropic
from datetime import datetime

log = logging.getLogger("publisher")
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

SHOW_CONFIG = {
    "name": "The Signal",
    "tagline": "Daily business and tech news, curated by AI",
    "category": "News > Business News",
    "language": "en",
    "website": os.getenv("PODCAST_WEBSITE_URL", ""),
    "buzzsprout_podcast_id": os.getenv("BUZZSPROUT_PODCAST_ID", ""),
}


class PublisherAgent:
    
    def generate_metadata(self, brief: dict, script_data: dict, episode_num: int,
                          episode_date: str, edition: str = "am", episode_title: str = "") -> dict:
        """Use Claude to generate SEO-optimized episode metadata"""

        story_titles = (
            [s["podcast_headline"] for s in brief.get("business_stories", [])] +
            [s["podcast_headline"] for s in brief.get("overlap_stories", [])] +
            [s["podcast_headline"] for s in brief.get("tech_stories", [])]
        )

        edition_label = edition.upper()
        prompt = f"""Generate metadata for today's podcast episode.

Show: The Signal
Episode: {episode_num} ({edition_label} edition)
Date: {episode_date}
Title: {episode_title}
Theme: {brief.get("show_theme", "")}
Stories covered: {json.dumps(story_titles, indent=2)}

Generate:
1. TITLE: Use this exact title: "{episode_title}" (or if empty, create one max 80 chars with episode number)
2. DESCRIPTION: 200-250 word show notes. Include: what we cover, why it matters, timestamps (approximate), keywords for SEO. No fluff.
3. CHAPTERS: List with timestamps (approximate based on show structure: cold open @0:00, business @2:00, crossover @14:00, tech @20:00, wrap @30:00)
4. TAGS: 8-10 relevant tags for podcast directories
5. TWEET: 240 char tweet announcing the episode (include 3 key topics, no hashtag spam)
6. LINKEDIN_POST: 3-4 sentence professional LinkedIn announcement

Return as JSON."""
        
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        
        try:
            metadata = json.loads(text.strip())
        except:
            # Fallback metadata
            metadata = {
                "TITLE": f"Ep {episode_num}: {brief.get('show_theme', 'The Signal')}",
                "DESCRIPTION": f"Today on The Signal: {'. '.join(story_titles[:3])}",
                "TAGS": ["business", "technology", "news", "ai"],
                "TWEET": f"New episode of The Signal is live! Episode {episode_num}: {brief.get('show_theme', '')} 🎙️",
                "LINKEDIN_POST": f"Today's episode of The Signal covers: {'. '.join(story_titles[:3])}"
            }
        
        metadata["episode_num"] = episode_num
        metadata["episode_date"] = episode_date
        return metadata
    
    def upload(self, audio_path: str, metadata: dict) -> str:
        """Upload episode to Buzzsprout via API"""
        api_key = os.environ["BUZZSPROUT_API_KEY"]
        podcast_id = SHOW_CONFIG["buzzsprout_podcast_id"]
        base_url = f"https://www.buzzsprout.com/api/{podcast_id}/episodes"
        
        with open(audio_path, 'rb') as audio_file:
            response = requests.post(
                base_url,
                headers={
                    "Authorization": f"Token token={api_key}",
                    "User-Agent": "TheSignal/1.0",
                },
                data={
                    "title": metadata.get("TITLE", "New Episode"),
                    "description": metadata.get("DESCRIPTION", ""),
                    "tags": ",".join(metadata.get("TAGS", [])),
                    "explicit": "false",
                    "private": "false",
                },
                files={"audio_file": (f"episode_{metadata['episode_date']}.mp3", audio_file, "audio/mpeg")},
                timeout=120
            )
        
        if response.status_code in (200, 201):
            episode_data = response.json()
            episode_url = episode_data.get("share_url", episode_data.get("audio_url", ""))
            log.info(f"  Episode uploaded: {episode_url}")
            self._save_episode_record(metadata, episode_url, audio_path)
            return episode_url
        else:
            raise RuntimeError(f"Buzzsprout upload failed: {response.status_code} — {response.text}")
    
    def post_social(self, metadata: dict, episode_url: str, edition: str = "am"):
        """Post announcements to social media"""
        self._post_twitter(metadata.get("TWEET", ""), episode_url)
        self._post_linkedin(metadata.get("LINKEDIN_POST", ""), episode_url)
    
    def _post_twitter(self, tweet_text: str, url: str):
        bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
        api_key = os.getenv("TWITTER_API_KEY")
        if not api_key:
            log.info("  Twitter: no credentials configured, skipping")
            return
        try:
            # Twitter API v2 tweet creation
            import tweepy
            auth = tweepy.OAuth1UserHandler(
                os.getenv("TWITTER_API_KEY"),
                os.getenv("TWITTER_API_SECRET"),
                os.getenv("TWITTER_ACCESS_TOKEN"),
                os.getenv("TWITTER_ACCESS_TOKEN_SECRET")
            )
            api = tweepy.API(auth)
            full_tweet = f"{tweet_text}\n\n{url}"[:280]
            api.update_status(full_tweet)
            log.info("  ✅ Posted to Twitter")
        except Exception as e:
            log.warning(f"  Twitter post failed: {e}")
    
    def _post_linkedin(self, post_text: str, url: str):
        if not os.getenv("LINKEDIN_ACCESS_TOKEN"):
            log.info("  LinkedIn: no credentials configured, skipping")
            return
        try:
            # LinkedIn Share API
            headers = {
                "Authorization": f"Bearer {os.getenv('LINKEDIN_ACCESS_TOKEN')}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0"
            }
            person_id = os.getenv("LINKEDIN_PERSON_ID")
            payload = {
                "author": f"urn:li:person:{person_id}",
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": f"{post_text}\n\n🎙️ Listen: {url}"},
                        "shareMediaCategory": "NONE"
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
            response = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload, timeout=15)
            if response.status_code == 201:
                log.info("  ✅ Posted to LinkedIn")
        except Exception as e:
            log.warning(f"  LinkedIn post failed: {e}")
    
    def _save_episode_record(self, metadata: dict, url: str, audio_path: str):
        import sqlite3
        from pathlib import Path
        Path("database").mkdir(exist_ok=True)
        conn = sqlite3.connect("database/episodes.db")
        conn.execute("""CREATE TABLE IF NOT EXISTS episodes 
                       (id INTEGER PRIMARY KEY, episode_num INTEGER, episode_date TEXT,
                        title TEXT, url TEXT, audio_path TEXT, created_at TEXT)""")
        conn.execute(
            "INSERT INTO episodes (episode_num, episode_date, title, url, audio_path, created_at) VALUES (?,?,?,?,?,?)",
            (metadata["episode_num"], metadata["episode_date"], metadata.get("TITLE"), 
             url, audio_path, datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
