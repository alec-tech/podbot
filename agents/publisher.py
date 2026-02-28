"""
agents/publisher.py v5 — Multi-Show Publishing and Syndication
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


def _get_client():
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


class PublisherAgent:

    def __init__(self, show=None):
        if show is None:
            from agents.show_loader import load_show
            show = load_show("the-signal")
        self.show = show

    def generate_metadata(self, brief: dict, script_data: dict, episode_num: int,
                          episode_date: str, edition: str = "morning") -> dict:
        """Use Claude to generate SEO-optimized episode metadata"""

        story_titles = []
        for cat_key in self.show.story_quotas.keys():
            story_titles.extend(
                s["podcast_headline"] for s in brief.get(cat_key, [])
            )

        edition_label = edition.upper()
        pipeline = self.show.pipeline_config
        target_minutes = pipeline.get("target_duration_minutes", 12)

        # Load prompt template
        prompt_template = self.show.prompts.get("publisher", "")
        if prompt_template:
            prompt = prompt_template.format(
                show_name=self.show.name,
                episode_num=episode_num,
                edition_label=edition_label,
                episode_date=episode_date,
                show_theme=brief.get("show_theme", ""),
                story_titles=json.dumps(story_titles, indent=2),
                target_minutes=target_minutes,
            )
        else:
            prompt = f"""Generate metadata for today's podcast episode.

Show: {self.show.name}
Episode: {episode_num} ({edition_label} edition)
Date: {episode_date}
Theme: {brief.get("show_theme", "")}
Stories covered: {json.dumps(story_titles, indent=2)}

Generate a JSON object with these keys:
1. TITLE: A compelling, concise episode title (max 80 chars).
2. DESCRIPTION: 200-250 word show notes.
3. CHAPTERS: List with timestamps
4. TAGS: 8-10 relevant tags
5. TWEET: 240 char tweet
6. LINKEDIN_POST: 3-4 sentence LinkedIn announcement

Return as JSON."""

        response = _get_client().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]

        try:
            metadata = json.loads(text.strip())
        except Exception:
            metadata = {
                "DESCRIPTION": f"Today on {self.show.name}: {'. '.join(story_titles[:3])}",
                "TAGS": self.show.topic_domains[:4],
                "TWEET": f"New episode of {self.show.name} is live! Episode {episode_num}: {brief.get('show_theme', '')}",
                "LINKEDIN_POST": f"Today's episode of {self.show.name} covers: {'. '.join(story_titles[:3])}"
            }

        if not metadata.get("TITLE"):
            metadata["TITLE"] = brief.get("show_theme") or f"Ep {episode_num}: {self.show.name}"
        metadata["episode_num"] = episode_num
        metadata["episode_date"] = episode_date
        return metadata

    def upload(self, audio_path: str, metadata: dict) -> str:
        """Upload episode to Buzzsprout via API"""
        api_key = os.environ["BUZZSPROUT_API_KEY"]
        podcast_id = os.getenv("BUZZSPROUT_PODCAST_ID", "")
        base_url = f"https://www.buzzsprout.com/api/{podcast_id}/episodes"

        with open(audio_path, 'rb') as audio_file:
            response = requests.post(
                base_url,
                headers={
                    "Authorization": f"Token token={api_key}",
                    "User-Agent": f"{self.show.name.replace(' ', '')}/1.0",
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

    def post_social(self, metadata: dict, episode_url: str, edition: str = "morning"):
        """Post announcements to social media"""
        self._post_twitter(metadata.get("TWEET", ""), episode_url)
        self._post_linkedin(metadata.get("LINKEDIN_POST", ""), episode_url)

    def _post_twitter(self, tweet_text: str, url: str):
        api_key = os.getenv("TWITTER_API_KEY")
        if not api_key:
            log.info("  Twitter: no credentials configured, skipping")
            return
        try:
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
            log.info("  Posted to Twitter")
        except Exception as e:
            log.warning(f"  Twitter post failed: {e}")

    def _post_linkedin(self, post_text: str, url: str):
        if not os.getenv("LINKEDIN_ACCESS_TOKEN"):
            log.info("  LinkedIn: no credentials configured, skipping")
            return
        try:
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
                        "shareCommentary": {"text": f"{post_text}\n\nListen: {url}"},
                        "shareMediaCategory": "NONE"
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
            }
            response = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=payload, timeout=15)
            if response.status_code == 201:
                log.info("  Posted to LinkedIn")
        except Exception as e:
            log.warning(f"  LinkedIn post failed: {e}")

    def _save_episode_record(self, metadata: dict, url: str, audio_path: str):
        import sqlite3
        db_path = self.show.database_dir() / "episodes.db"
        conn = sqlite3.connect(db_path)
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
