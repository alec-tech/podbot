"""
agents/scriptwriter.py v3 — Edition-Aware Script Generation

AM edition: Yesterday's Recap segment (2:30–7:30) + overnight stories
PM edition: Standard 7-story structure, no recap
Both: 43-minute target, two sponsor spots
"""

import os
import json
import logging
from anthropic import Anthropic

log = logging.getLogger("scriptwriter")
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

PERSONAS = {
    "alex": {
        "name": "Alex Chen",
        "role": "Business anchor",
        "personality": "Analytical, measured, slightly skeptical of hype. Ex-finance background energy. Asks sharp clarifying questions. Connects stories to market implications. Occasionally dry wit.",
        "speech_patterns": ["Let's be precise about this...", "The real question here is...", "That number deserves scrutiny.", "Hold on—"],
        "avoid": ["Excessive enthusiasm", "Tech jargon without explanation", "Vague optimism"],
    },
    "morgan": {
        "name": "Morgan Lee",
        "role": "Tech correspondent",
        "personality": "Enthusiastic but substantive. Loves emerging tech, connects it to human impact. Pushes back on Alex's skepticism with evidence. Uses vivid analogies. Faster pace when excited.",
        "speech_patterns": ["Okay but think about what this actually means—", "This is the part people are sleeping on:", "So here's the thing about that—", "Wait, actually—"],
        "avoid": ["Empty hype", "Dismissing business concerns", "Being condescending"],
    },
    "drew": {
        "name": "Drew Vasquez",
        "role": "Markets and strategy analyst (overlap segment only)",
        "personality": "Big picture thinker. Historical context, contrarian takes, pattern recognition. Deliberate pacing. Bridges Alex and Morgan.",
        "speech_patterns": ["Here's a historical parallel—", "I want to push back on the framing.", "The conventional wisdom is X, but look at the data.", "This is the third time we've seen this pattern."],
        "avoid": ["Excessive hedging", "Agreeing with both without adding value"],
    },
}

SYSTEM_PROMPT_AM = """You are the head writer for "The Signal," a twice-daily business and tech podcast.

MORNING EDITION (4:00 AM EST) — 43 minutes target (~5,590 words spoken at 130 wpm)

This episode has two jobs: (1) recap yesterday PM's biggest stories, (2) cover overnight news.

STRUCTURE:

[COLD OPEN — 0:00–1:30 — ~195 words]
Tease the most important overnight story. Start in the middle of the action. No pleasantries.

[INTRO — 1:30–2:30 — ~130 words]
"Good morning, welcome to The Signal morning edition." Date, episode number, hosts.

[YESTERDAY'S RECAP — 2:30–7:30 — ~650 words]
Alex: "Here's where things stood when we signed off yesterday afternoon..."
Briskly cover 2-3 PM stories. Each gets ~90 seconds MAX. Fast-paced.
Format per story: headline → one-sentence context → one-sentence new angle / update.
This is orientation, not re-investigation. Keep it moving.

[SPONSOR SPOT 1 — 7:30–8:30 — ~130 words]
Alex reads, 60 seconds. [ALEX - reading sponsor]: "Quick break..."

[OVERNIGHT BUSINESS BLOCK — 8:30–20:00 — ~1,495 words]
2 overnight business stories.
Story 1: Alex leads (5–6 min deep), Morgan reacts with evidence
Story 2: Morgan challenges Alex's frame (3–4 min)
Each: setup → data → debate → so-what

[OVERNIGHT CROSSOVER — 20:00–27:00 — ~910 words]
Drew joins. Overnight story bridging business and tech. At least ONE real disagreement.

[OVERNIGHT TECH BLOCK — 27:00–40:00 — ~1,690 words]
2 overnight tech stories.
Story 1: Morgan leads (5–6 min), Alex grounds with business context
Story 2: Alex leads skeptically (4 min), Morgan defends with data

[SPONSOR SPOT 2 — 40:00–41:00 — ~130 words]
Morgan reads, 60 seconds. Different energy from Spot 1.

[WRAP — 41:00–43:00 — ~260 words]
What to watch today (2 specific things). Callback to sharpest exchange.
Tease PM: "We'll be back at 1 this afternoon with the morning's full story."
Warm, not corporate.

DIALOGUE RULES:
- NEVER: "Great point," "Absolutely," "Exactly," "That's fascinating," "Good question"
- DO: interruptions, half-sentences, "Hold on—", "Actually—", real tension
- 3+ data points per overnight story. At least 2 genuine disagreements total.

SPONSOR RULES: Spot 1 at 7:30 (Alex), Spot 2 at 40:00 (Morgan). 60 sec each. Never break character.

FORMAT: [HOST_NAME - acting direction]: "dialogue"
Return complete script only. No headers or commentary outside the script."""

SYSTEM_PROMPT_PM = """You are the head writer for "The Signal," a twice-daily business and tech podcast.

AFTERNOON EDITION (1:00 PM EST) — 43 minutes target (~5,590 words spoken at 130 wpm)

Covers news from 4:00 AM–1:00 PM EST. 7 fresh stories. No recap (AM handled it).

STRUCTURE:

[COLD OPEN — 0:00–1:30 — ~195 words]
Morgan teases the biggest morning story with a sharp hook.
Alex sets the business stakes and tension. Start in the action.

[INTRO — 1:30–2:30 — ~130 words]
"Good afternoon, welcome to The Signal." Reference that AM covered overnight.
This is the morning's full story. Date, episode number, hosts.

[BUSINESS BLOCK — 2:30–15:00 — ~1,625 words]
Story 1: Alex leads (4–5 min), Morgan reacts
Story 2: Morgan challenges Alex's frame (3–4 min)
Story 3: Quick take, both hosts, 60 seconds each
Each: setup → data → debate → so-what

[SPONSOR SPOT 1 — 15:00–16:00 — ~130 words]
Alex reads, 60 seconds. Natural, not jarring.

[CROSSOVER SEGMENT — 16:00–23:00 — ~910 words]
Drew joins. One story that requires all three perspectives. At least ONE real disagreement.

[TECH BLOCK — 23:00–40:00 — ~2,210 words]
Story 1: Morgan leads (5–6 min), Alex provides business grounding
Story 2: Alex leads skeptically (3–4 min), Morgan defends with data
Story 3: Quick takes, both hosts, 90 seconds each

[SPONSOR SPOT 2 — 40:00–41:00 — ~130 words]
Morgan reads, 60 seconds. Different energy from Spot 1.

[WRAP — 41:00–43:00 — ~260 words]
What to watch tomorrow (2 specific things). Callback to sharpest exchange.
Tease AM: "We'll be back tomorrow morning at 4 with the overnight."
Warm sign-off.

DIALOGUE RULES:
- NEVER: "Great point," "Absolutely," "Exactly," "That's fascinating," "Good question"
- DO: interruptions, half-sentences, "Hold on—", real disagreements, evidence-based pushback
- 3+ data points per story. At least 2 genuine disagreements per episode.

SPONSOR RULES: Spot 1 at 15:00 (Alex), Spot 2 at 40:00 (Morgan). 60 sec each. Never break character.

FORMAT: [HOST_NAME - acting direction]: "dialogue"
Return complete script only."""


class ScriptwriterAgent:

    def run(self, brief: dict, episode_num: int, episode_date: str, edition: str) -> dict:
        edition = edition.lower()
        sponsors = brief.get("sponsors", self._placeholder_sponsors())
        script_text = self._write_script(brief, episode_num, episode_date, edition, sponsors)
        est = self._estimate_duration(script_text)
        log.info(f"  First draft: ~{est:.1f} min ({edition.upper()})")

        if est < 41:
            log.info(f"  Expanding ({43 - est:.1f} min short)...")
            script_text = self._expand_script(script_text, brief, 43 - est, edition)
        elif est > 46:
            log.info(f"  Trimming ({est - 43:.1f} min over)...")
            script_text = self._trim_script(script_text, est - 43)

        final_est = self._estimate_duration(script_text)
        log.info(f"  Final: ~{final_est:.1f} min ({edition.upper()})")

        return {
            "full_script":       script_text,
            "estimated_minutes": final_est,
            "episode_num":       episode_num,
            "episode_date":      episode_date,
            "edition":           edition,
            "show_theme":        brief.get("show_theme", ""),
            "episode_hook":      brief.get("episode_hook", ""),
            "sponsors":          sponsors,
        }

    def _placeholder_sponsors(self) -> list:
        return [
            {
                "slot": "mid",
                "name": "SPONSOR_PLACEHOLDER",
                "tagline": "Visit our website to learn more.",
                "product_description": "A leading B2B SaaS platform for business professionals",
                "cta": "Visit thesignalpod.com/sponsor for a listener offer",
            },
            {
                "slot": "outro",
                "name": "SPONSOR_PLACEHOLDER",
                "tagline": "Built for the way you work.",
                "product_description": "A productivity and workflow tool used by top companies",
                "cta": "Get started free at thesignalpod.com/sponsor2",
            },
        ]

    def _write_script(self, brief: dict, episode_num: int, episode_date: str,
                      edition: str, sponsors: list) -> str:
        system_prompt = SYSTEM_PROMPT_AM if edition == "am" else SYSTEM_PROMPT_PM
        edition_label = "MORNING" if edition == "am" else "AFTERNOON"

        recap = brief.get("yesterday_recap", [])
        recap_note = ""
        if edition == "am" and recap:
            recap_note = f"\nYESTERDAY'S PM RECAP STORIES ({len(recap)} — use in the recap segment):\n"
            for r in recap:
                recap_note += (
                    f"  • [{r['category'].upper()}] {r['headline']}"
                    + (f" — {r['one_line_summary']}" if r.get("one_line_summary") else "")
                    + "\n"
                )

        prompt = f"""Write the complete {edition_label} EDITION script for The Signal.

Episode: {episode_num} | Date: {episode_date} | Edition: {edition.upper()}
Theme: {brief.get("show_theme", "")}
Hook: {brief.get("episode_hook", "")}
Stories: {len(brief.get("business_stories",[]))} business, {len(brief.get("tech_stories",[]))} tech, {len(brief.get("overlap_stories",[]))} overlap
{recap_note}
HOST PERSONAS:
{json.dumps(PERSONAS, indent=2)}

SPONSORS:
{json.dumps(sponsors, indent=2)}

EDITORIAL BRIEF:
{json.dumps(brief, indent=2)}

Write the COMPLETE 43-minute script (~5,590 words of spoken dialogue).
Include BOTH sponsor spots. Do not skip any structural section.
Begin immediately with the cold open dialogue. No preamble."""

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=12000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _estimate_duration(self, script: str) -> float:
        import re
        lines = re.findall(r'\]: "([^"]+)"', script)
        words = sum(len(l.split()) for l in lines)
        return words / 130

    def _expand_script(self, script: str, brief: dict, min_short: float, edition: str) -> str:
        words_needed = int(min_short * 130)
        edition_word = "morning" if edition == "am" else "afternoon"
        prompt = f"""This {edition_word} podcast script is {min_short:.1f} minutes short. Add ~{words_needed} words by:

1. Expanding the most interesting debate — 2-3 more rounds of back-and-forth
2. Deepening the crossover segment — Drew introduces a historical parallel
3. Adding more specific data and debate to the main tech story
4. Slightly more substantial Wrap with a forward-looking prediction

Keep both sponsor spots intact. Same voice and character consistency.
Return the COMPLETE expanded script.

SCRIPT:
{script}"""
        r = client.messages.create(model="claude-sonnet-4-6", max_tokens=12000,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text

    def _trim_script(self, script: str, min_over: float) -> str:
        words_cut = int(min_over * 130)
        prompt = f"""This script is {min_over:.1f} minutes too long. Remove ~{words_cut} words by:

1. Tightening exchanges that repeat the same point
2. Cutting tangential remarks that don't advance the story
3. Shortening quick takes that run long
4. Trimming padded lines in the intro or wrap

DO NOT cut: either sponsor spot, the cold open, crossover segment, or wrap.
Cut agreement and repetition, not genuine disagreements.
Return the COMPLETE trimmed script.

SCRIPT:
{script}"""
        r = client.messages.create(model="claude-sonnet-4-6", max_tokens=12000,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
