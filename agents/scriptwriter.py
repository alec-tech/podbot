"""
agents/scriptwriter.py v5 — Multi-Show Script Generation

Reads personas, prompts, and duration targets from ShowConfig.
"""

import os
import json
import logging
from anthropic import Anthropic

from agents.show_loader import safe_format

log = logging.getLogger("scriptwriter")


def _get_client():
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def select_crossover_host(show, crossover_story: dict, episode_num: int) -> str:
    """
    Select the best rotating crossover host for the given story.
    Topic-weighted with round-robin fallback.
    """
    rotating = show.rotating_hosts
    if not rotating:
        return show.static_hosts[0] if show.static_hosts else "host"

    if not crossover_story:
        return rotating[episode_num % len(rotating)]

    # Build text to match against
    story_text = (
        crossover_story.get("podcast_headline", "") + " " +
        crossover_story.get("context", "") + " " +
        crossover_story.get("summary", "")
    ).lower()

    # Score each rotating host
    scores = {}
    for host_key in rotating:
        persona = show.personas[host_key]
        keywords = persona.get("topic_keywords", [])
        score = sum(1 for kw in keywords if kw in story_text)
        scores[host_key] = score

    max_score = max(scores.values())
    if max_score > 0:
        winners = [h for h, s in scores.items() if s == max_score]
        if len(winners) == 1:
            return winners[0]
        return winners[episode_num % len(winners)]

    return rotating[episode_num % len(rotating)]


class ScriptwriterAgent:

    def __init__(self, show=None):
        if show is None:
            from agents.show_loader import load_show
            show = load_show()
        self.show = show

    def run(self, brief: dict, episode_num: int, episode_date: str, edition: str) -> dict:
        edition = edition.lower()
        edition_config = self.show.editions.get(edition, {})
        pipeline = self.show.pipeline_config
        wpm = pipeline.get("wpm", 140)
        target = edition_config.get("target_duration_minutes", pipeline.get("target_duration_minutes", 12))
        min_dur = edition_config.get("min_duration_minutes", pipeline.get("min_duration_minutes", 10))
        max_dur = edition_config.get("max_duration_minutes", pipeline.get("max_duration_minutes", 15))

        sponsors = brief.get("sponsors", self._placeholder_sponsors())

        # Select crossover host
        overlap_stories = brief.get("overlap_stories", [])
        crossover_story = overlap_stories[0] if overlap_stories else None
        crossover_host = select_crossover_host(self.show, crossover_story, episode_num)

        script_text = self._write_script(brief, episode_num, episode_date, edition, sponsors, crossover_host)
        est = self._estimate_duration(script_text, wpm)
        log.info(f"  First draft: ~{est:.1f} min ({edition.capitalize()})")

        if est < min_dur:
            gap = target - est
            log.info(f"  Expanding ({gap:.1f} min short)...")
            script_text = self._expand_script(script_text, brief, gap, edition)
        elif est > max_dur:
            overage = est - target
            log.info(f"  Trimming ({overage:.1f} min over)...")
            script_text = self._trim_script(script_text, overage, edition)

        final_est = self._estimate_duration(script_text, wpm)
        log.info(f"  Final: ~{final_est:.1f} min ({edition.capitalize()})")

        return {
            "full_script":       script_text,
            "estimated_minutes": final_est,
            "episode_num":       episode_num,
            "episode_date":      episode_date,
            "edition":           edition,
            "show_theme":        brief.get("show_theme", ""),
            "episode_hook":      brief.get("episode_hook", ""),
            "sponsors":          sponsors,
            "crossover_host":    crossover_host,
        }

    def _placeholder_sponsors(self) -> list:
        return [
            {
                "slot": "pre-outro",
                "name": "SPONSOR_PLACEHOLDER",
                "tagline": "Built for the way you work.",
                "product_description": "A productivity and workflow tool used by top companies",
                "cta": "Get started free at sponsor.example.com/podcast",
            },
        ]

    def _write_script(self, brief: dict, episode_num: int, episode_date: str,
                      edition: str, sponsors: list, crossover_host: str) -> str:
        personas = self.show.personas
        guest = personas[crossover_host]
        static = self.show.static_hosts
        edition_config = self.show.editions.get(edition, {})
        pipeline = self.show.pipeline_config
        wpm = pipeline.get("wpm", 140)
        target = edition_config.get("target_duration_minutes", pipeline.get("target_duration_minutes", 12))

        # Determine static host roles
        static_1_key = static[0] if static else "host1"
        static_2_key = static[1] if len(static) > 1 else static_1_key
        static_1 = personas.get(static_1_key, {})
        static_2 = personas.get(static_2_key, {})

        edition_label = edition.upper()
        edition_word = edition.lower()
        publish_time_est = edition_config.get("publish_time_est", "07:00")
        h, m = publish_time_est.split(":")
        h_int = int(h)
        ampm = "AM" if h_int < 12 else "PM"
        h_12 = h_int if h_int <= 12 else h_int - 12
        publish_time = f"{h_12}:{m} {ampm}"

        word_target = int(target * wpm)

        # Build dynamic content blocks for generic templates
        content_blocks, pre_outro_ts, signoff_ts = self._build_content_blocks(
            static_1, static_2, guest, crossover_host, target,
        )

        # Load prompt template
        system_template = self.show.prompts.get("scriptwriter", "")
        if system_template:
            system_prompt = safe_format(
                system_template,
                show_name=self.show.name,
                show_tagline=self.show.tagline,
                edition_label=edition_label,
                publish_time=publish_time,
                edition_word=edition_word,
                target_minutes=target,
                word_target=word_target,
                wpm=wpm,
                guest_name=guest["name"],
                guest_role=guest["role"],
                static_host_1=static_1.get("name", "Host 1"),
                static_role_1=static_1.get("role", "Anchor"),
                static_host_2=static_2.get("name", "Host 2"),
                static_role_2=static_2.get("role", "Correspondent"),
                lead_host_business=static_1.get("name", "Host 1"),
                other_host_business=static_2.get("name", "Host 2"),
                lead_host_tech=static_2.get("name", "Host 2"),
                other_host_tech=static_1.get("name", "Host 1"),
                content_blocks=content_blocks,
                pre_outro_timestamp=pre_outro_ts,
                signoff_start=signoff_ts,
            )
        else:
            system_prompt = f"You are the head writer for {self.show.name}. Write a {target}-minute podcast script."

        # Build personas for prompt — static hosts + selected guest
        active_personas = {}
        for key in static:
            active_personas[key] = personas[key]
        active_personas[crossover_host] = guest

        # Sponsor slot instructions
        sponsor_slots = {"pre-intro": None, "post-intro": None, "pre-outro": None}
        for s in sponsors:
            slot = s.get("slot", "")
            if slot in sponsor_slots:
                sponsor_slots[slot] = s

        sponsor_instruction = "Include sponsor spots ONLY for slots that have sponsors provided below. Skip empty slots."

        prompt = f"""Write the complete {edition_label} EDITION script for {self.show.name}.

Episode: {episode_num} | Date: {episode_date} | Edition: {edition.capitalize()}
Theme: {brief.get("show_theme", "")}
Hook: {brief.get("episode_hook", "")}
Stories: {json.dumps({k: len(brief.get(k, [])) for k in self.show.story_quotas.keys()})}
Crossover guest: {guest["name"]} ({guest["role"]})

HOST PERSONAS:
{json.dumps(active_personas, indent=2)}

SPONSORS:
{json.dumps(sponsors, indent=2)}

EDITORIAL BRIEF:
{json.dumps(brief, indent=2)}

Write the COMPLETE {target}-minute script (~{word_target} words of spoken dialogue).
{sponsor_instruction}
Begin immediately with the intro dialogue (or pre-intro sponsor if one is provided). No preamble."""

        response = _get_client().messages.create(
            model="claude-opus-4-6",
            max_tokens=12000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _build_content_blocks(self, static_1: dict, static_2: dict,
                               guest: dict, guest_key: str, target: int) -> tuple[str, str, str]:
        """Build dynamic content block instructions from story_quotas.

        Returns (content_blocks_text, pre_outro_timestamp, signoff_start).
        """
        quotas = self.show.story_quotas
        items = list(quotas.items())
        if not items:
            return ("", f"{target-1.5:.0f}:00", f"{target-1:.0f}:00")

        # Allocate ~2 min per story, starting at 1:30 (after intro)
        current_min = 1.5
        blocks = []
        mid_idx = len(items) // 2  # Middle block gets the guest crossover

        for i, (cat_key, count) in enumerate(items):
            label = cat_key.replace("_", " ").upper()
            block_minutes = count * 2
            start_ts = f"{int(current_min)}:{int((current_min % 1) * 60):02d}"
            end_min = current_min + block_minutes
            end_ts = f"{int(end_min)}:{int((end_min % 1) * 60):02d}"
            words = int(block_minutes * self.show.pipeline_config.get("wpm", 140))

            if i == mid_idx and len(items) > 1:
                # Crossover block — guest joins
                block_text = (
                    f"[{label} (CROSSOVER) — {start_ts}–{end_ts} — ~{words} words]\n"
                    f"{count} stories, ~2 min each. {guest['name']} joins for this segment.\n"
                    f"This is the segment where the guest brings their specialty. At least ONE real disagreement.\n"
                    f"{static_1.get('name', 'Host 1')} or {static_2.get('name', 'Host 2')} can push back."
                )
            elif i == 0:
                # First block — static host 1 leads
                block_text = (
                    f"[{label} — {start_ts}–{end_ts} — ~{words} words]\n"
                    f"{count} stories, ~2 min each. {static_1.get('name', 'Host 1')} leads each one.\n"
                    f"Format per story: headline -> key fact or number -> debate with {static_2.get('name', 'Host 2')} -> so-what."
                )
            else:
                # Later blocks — static host 2 leads
                block_text = (
                    f"[{label} — {start_ts}–{end_ts} — ~{words} words]\n"
                    f"{count} stories, ~2 min each. {static_2.get('name', 'Host 2')} leads each one.\n"
                    f"Format per story: headline -> key detail -> {static_1.get('name', 'Host 1')} reacts -> wrap."
                )
            blocks.append(block_text)
            current_min = end_min

        pre_outro_ts = f"{int(current_min)}:{int((current_min % 1) * 60):02d}"
        signoff_min = current_min + 0.5
        signoff_ts = f"{int(signoff_min)}:{int((signoff_min % 1) * 60):02d}"

        return ("\n\n".join(blocks), pre_outro_ts, signoff_ts)

    def _estimate_duration(self, script: str, wpm: int = 140) -> float:
        import re
        lines = re.findall(r'\]: "([^"]+)"', script)
        words = sum(len(l.split()) for l in lines)
        return words / wpm

    def _expand_script(self, script: str, brief: dict, min_short: float, edition: str) -> str:
        pipeline = self.show.pipeline_config
        wpm = pipeline.get("wpm", 140)
        words_needed = int(min_short * wpm)

        prompt = f"""This podcast script is {min_short:.1f} minutes short. Add ~{words_needed} words by:

1. Adding a quick reaction or back-and-forth to the thinnest story
2. Slightly expanding the crossover segment with one more exchange
3. Adding one more specific detail or number to the biggest story

Keep all sponsor spots intact. Keep it conversational and fast-paced.
Return the COMPLETE expanded script.

SCRIPT:
{script}"""
        r = _get_client().messages.create(model="claude-sonnet-4-6", max_tokens=12000,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text

    def _trim_script(self, script: str, min_over: float, edition: str = "morning") -> str:
        pipeline = self.show.pipeline_config
        wpm = pipeline.get("wpm", 140)
        words_cut = int(min_over * wpm)

        prompt = f"""This podcast script is {min_over:.1f} minutes too long. Remove ~{words_cut} words by:

1. Cutting any exchange that goes beyond one quick back-and-forth per story
2. Removing redundant reactions or repeated points
3. Tightening the intro and signoff

DO NOT cut: any sponsor spots.
Every line should earn its place.
Return the COMPLETE trimmed script.

SCRIPT:
{script}"""
        r = _get_client().messages.create(model="claude-sonnet-4-6", max_tokens=12000,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
