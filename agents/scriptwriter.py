"""
agents/scriptwriter.py v3 — Edition-Aware Script Generation

AM edition: Yesterday's Recap segment (2:00–6:00) + overnight stories — 33-minute target, two sponsor spots
PM edition: Quick highlights reel — ~11-minute target, single post-roll sponsor, just Alex + Morgan
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

MORNING EDITION (4:00 AM EST) — 33 minutes target (~4,290 words spoken at 130 wpm)

This episode has two jobs: (1) recap yesterday PM's biggest stories, (2) cover overnight news.

STRUCTURE:

[COLD OPEN — 0:00–1:30 — ~195 words]
Tease the most important overnight story. Start in the middle of the action. No pleasantries.

[INTRO — 1:30–2:00 — ~65 words]
"Good morning, welcome to The Signal morning edition." Date, episode number, hosts. Keep it tight.

[YESTERDAY'S RECAP — 2:00–6:00 — ~520 words]
Alex: "Here's where things stood when we signed off yesterday afternoon..."
Briskly cover 2-3 PM stories. Each gets ~60-90 seconds MAX. Fast-paced.
Format per story: headline → one-sentence context → one-sentence new angle / update.
This is orientation, not re-investigation. Keep it moving.

[SPONSOR SPOT 1 — 6:00–7:00 — ~130 words]
The designated host reads the provided sponsor script verbatim. Use the exact script from the sponsor data. Format: [HOST_NAME - reading sponsor]: "script text"

[OVERNIGHT BUSINESS BLOCK — 7:00–15:00 — ~1,040 words]
2 overnight business stories.
Story 1: Alex leads (4–5 min deep), Morgan reacts with evidence
Story 2: Morgan challenges Alex's frame (3 min)
Each: setup → data → debate → so-what

[OVERNIGHT CROSSOVER — 15:00–21:00 — ~780 words]
Drew joins. Overnight story bridging business and tech. At least ONE real disagreement.

[OVERNIGHT TECH BLOCK — 21:00–30:00 — ~1,170 words]
2 overnight tech stories.
Story 1: Morgan leads (4–5 min), Alex grounds with business context
Story 2: Alex leads skeptically (3 min), Morgan defends with data

[SPONSOR SPOT 2 — 30:00–31:00 — ~130 words]
The designated host reads the provided sponsor script verbatim. Use the exact script from the sponsor data. Different energy from Spot 1. Format: [HOST_NAME - reading sponsor]: "script text"

[WRAP — 31:00–33:00 — ~260 words]
What to watch today (2 specific things). Callback to sharpest exchange.
Tease PM: "We'll be back at 1 this afternoon with the morning's full story."
Warm, not corporate.

DIALOGUE RULES:
- NEVER: "Great point," "Absolutely," "Exactly," "That's fascinating," "Good question"
- DO: interruptions, half-sentences, "Hold on—", "Actually—", real tension
- 3+ data points per overnight story. At least 2 genuine disagreements total.

SPONSOR RULES: Each sponsor specifies a "voice" (alex/morgan/drew) and a "script" field. Use the designated host and read the provided script verbatim. 60 sec each. Never break character.

FORMAT: [HOST_NAME - acting direction]: "dialogue"
Return complete script only. No headers or commentary outside the script."""

SYSTEM_PROMPT_PM = """You are the head writer for "The Signal," a twice-daily business and tech podcast.

AFTERNOON EDITION (1:00 PM EST) — ~11 minutes target (~1,400 words at 140 wpm conversational pace)

This is the PM HIGHLIGHTS REEL — a quick, breezy rundown of the morning's biggest stories.
Just Alex and Morgan. No Drew. No deep dives. The listener is grabbing a coffee, checking in
on what happened. Give them the signal, not the noise.

HOSTS: Alex Chen (business anchor) and Morgan Lee (tech correspondent) ONLY.

STRUCTURE:

[INTRO — 0:00–0:30 — ~70 words]
Quick, energetic open. "Good afternoon, you're listening to The Signal — here's what
happened this morning." No cold open — jump straight in. Date and episode number, fast.

[BUSINESS HEADLINES — 0:30–4:30 — ~560 words]
2 business stories, ~2 min each. Alex leads each one.
Format per story: headline → one key fact or number → Morgan reacts → Alex wraps with so-what.
Keep it punchy. No extended debates. One sharp exchange per story max.

[CROSSOVER MOMENT — 4:30–5:30 — ~140 words]
1 story that bridges business and tech. Either host can lead. Quick back-and-forth.
This is a ~60-second moment, not a full segment.

[TECH HEADLINES — 5:30–9:30 — ~560 words]
2 tech stories, ~2 min each. Morgan leads each one.
Same format: headline → key detail → Alex reacts → Morgan wraps.

[LOOKING FORWARD + SIGNOFF — 9:30–10:00 — ~70 words]
One sentence on what to watch tonight/tomorrow. Warm but quick signoff.
"We'll be back tomorrow morning at 4. Until then — stay sharp." or similar.

[SPONSOR SPOT — 10:00–11:00 — ~130 words — POST-ROLL]
The designated host reads the provided sponsor script verbatim. Use the exact script from the sponsor data. This comes AFTER the signoff. Format: [HOST_NAME - reading sponsor]: "script text"

NATURALNESS — THIS IS CRITICAL:
The listener should NOT feel like the hosts are reading from a script. Write dialogue that
sounds like two smart people who just read the news talking to each other over coffee.
- Use contractions always (it's, don't, we're, that's)
- Incomplete thoughts are fine: "So the thing about this deal is—" "Right, the valuation."
- Reactions mid-sentence: "Wait, hold on—" "Yeah so—" "Okay but—"
- Let hosts interrupt each other naturally
- Short sentences. Fragments are fine. "Big number." "Not great." "Classic move."
- Avoid formal transitions. No "Moving on to our next story" — just pivot naturally.
- Sprinkle in casual filler: "I mean," "look," "honestly," "here's the thing"

DIALOGUE RULES:
- NEVER: "Great point," "Absolutely," "Exactly," "That's fascinating," "Good question"
- NEVER: formal transitions, segment announcements, reading-from-a-script energy
- DO: quick reactions, half-sentences, natural pivots, one genuine disagreement per episode
- 1-2 data points per story (this is highlights, not deep dive)

SPONSOR RULES: Single post-roll spot after signoff (~10:00). The sponsor specifies a "voice" (alex/morgan) and a "script" field. Use the designated host and read the provided script verbatim. Never break character.

FORMAT: [HOST_NAME - acting direction]: "dialogue"
Return complete script only. No preamble or commentary."""


class ScriptwriterAgent:

    # Edition-specific duration targets
    DURATION_TARGETS = {
        "am": {"target": 33, "min": 31, "max": 36, "wpm": 130},
        "pm": {"target": 11, "min": 8,  "max": 15, "wpm": 140},
    }

    def run(self, brief: dict, episode_num: int, episode_date: str, edition: str) -> dict:
        edition = edition.lower()
        targets = self.DURATION_TARGETS[edition]
        sponsors = brief.get("sponsors", self._placeholder_sponsors(edition))
        script_text = self._write_script(brief, episode_num, episode_date, edition, sponsors)
        est = self._estimate_duration(script_text, targets["wpm"])
        log.info(f"  First draft: ~{est:.1f} min ({edition.upper()})")

        if est < targets["min"]:
            gap = targets["target"] - est
            log.info(f"  Expanding ({gap:.1f} min short)...")
            script_text = self._expand_script(script_text, brief, gap, edition)
        elif est > targets["max"]:
            overage = est - targets["target"]
            log.info(f"  Trimming ({overage:.1f} min over)...")
            script_text = self._trim_script(script_text, overage, edition)

        final_est = self._estimate_duration(script_text, targets["wpm"])
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

    def _placeholder_sponsors(self, edition: str = "am") -> list:
        if edition == "pm":
            return [
                {
                    "slot": "post-roll",
                    "name": "SPONSOR_PLACEHOLDER",
                    "tagline": "Built for the way you work.",
                    "product_description": "A productivity and workflow tool used by top companies",
                    "cta": "Get started free at thesignalpod.com/sponsor",
                },
            ]
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
        targets = self.DURATION_TARGETS[edition]

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

        # Edition-aware personas: PM uses only Alex and Morgan
        if edition == "pm":
            personas = {k: v for k, v in PERSONAS.items() if k in ("alex", "morgan")}
        else:
            personas = PERSONAS

        word_target = int(targets["target"] * targets["wpm"])
        sponsor_instruction = (
            "Include BOTH sponsor spots. Do not skip any structural section."
            if edition == "am" else
            "Include the single post-roll sponsor spot AFTER the signoff."
        )

        prompt = f"""Write the complete {edition_label} EDITION script for The Signal.

Episode: {episode_num} | Date: {episode_date} | Edition: {edition.upper()}
Theme: {brief.get("show_theme", "")}
Hook: {brief.get("episode_hook", "")}
Stories: {len(brief.get("business_stories",[]))} business, {len(brief.get("tech_stories",[]))} tech, {len(brief.get("overlap_stories",[]))} overlap
{recap_note}
HOST PERSONAS:
{json.dumps(personas, indent=2)}

SPONSORS:
{json.dumps(sponsors, indent=2)}

EDITORIAL BRIEF:
{json.dumps(brief, indent=2)}

Write the COMPLETE {targets["target"]}-minute script (~{word_target} words of spoken dialogue).
{sponsor_instruction}
Begin immediately with the {"cold open" if edition == "am" else "intro"} dialogue. No preamble."""

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=12000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _estimate_duration(self, script: str, wpm: int = 130) -> float:
        import re
        lines = re.findall(r'\]: "([^"]+)"', script)
        words = sum(len(l.split()) for l in lines)
        return words / wpm

    def _expand_script(self, script: str, brief: dict, min_short: float, edition: str) -> str:
        targets = self.DURATION_TARGETS[edition]
        words_needed = int(min_short * targets["wpm"])
        edition_word = "morning" if edition == "am" else "afternoon"

        if edition == "pm":
            prompt = f"""This {edition_word} highlights podcast script is {min_short:.1f} minutes short. Add ~{words_needed} words by:

1. Adding a quick reaction or back-and-forth to the thinnest story
2. Slightly expanding the crossover moment with one more exchange
3. Adding one more specific detail or number to the biggest story

Keep the single post-roll sponsor spot intact. Keep it conversational and fast-paced.
Do NOT add deep dives or extended debates — this is a highlights reel.
Return the COMPLETE expanded script.

SCRIPT:
{script}"""
        else:
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

    def _trim_script(self, script: str, min_over: float, edition: str = "am") -> str:
        targets = self.DURATION_TARGETS[edition]
        words_cut = int(min_over * targets["wpm"])

        if edition == "pm":
            prompt = f"""This highlights podcast script is {min_over:.1f} minutes too long. Remove ~{words_cut} words by:

1. Cutting any exchange that goes beyond one quick back-and-forth per story
2. Removing redundant reactions or repeated points
3. Tightening the intro and signoff

DO NOT cut: the post-roll sponsor spot.
This is a highlights reel — every line should earn its place.
Return the COMPLETE trimmed script.

SCRIPT:
{script}"""
        else:
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
