"""
agents/scriptwriter.py v4 — Unified Three-Edition Script Generation

All editions: 10-15 min target (12 min ideal), 2 static hosts + 1 rotating crossover guest.
Unified episode structure with 3 optional sponsor slots.
"""

import os
import json
import logging
from anthropic import Anthropic

log = logging.getLogger("scriptwriter")
client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# ─── Host Personas ────────────────────────────────────────────────────────────

PERSONAS = {
    # Static hosts (every episode)
    "chuck": {
        "name": "Chuck Leblanc",
        "role": "Business anchor",
        "type": "static",
        "personality": "Analytical, measured, slightly skeptical of hype. Ex-finance background energy. Asks sharp clarifying questions. Connects stories to market implications. Occasionally dry wit.",
        "speech_patterns": [
            "Demands analytical precision — frequently challenges vague claims, questions specific numbers, and insists on distinguishing correlation from causation. Varies his phrasing naturally each time rather than repeating a catchphrase.",
            "The real question here is...",
            "That number deserves scrutiny.",
            "Hold on—",
        ],
        "avoid": ["Excessive enthusiasm", "Tech jargon without explanation", "Vague optimism"],
    },
    "jessica": {
        "name": "Jessica Waverly",
        "role": "Tech correspondent",
        "type": "static",
        "personality": "Enthusiastic but substantive. Loves emerging tech, connects it to human impact. Pushes back on Alex's skepticism with evidence. Uses vivid analogies. Faster pace when excited.",
        "speech_patterns": ["Okay but think about what this actually means—", "This is the part people are sleeping on:", "So here's the thing about that—", "Wait, actually—"],
        "avoid": ["Empty hype", "Dismissing business concerns", "Being condescending"],
    },
    # Rotating crossover hosts (one per episode)
    "drew": {
        "name": "Drew Vasquez",
        "role": "Geopolitics & trade analyst",
        "type": "rotating",
        "personality": "Big picture thinker. Historical context, contrarian takes, pattern recognition. Deliberate pacing. Specializes in trade wars, sanctions, macro, and international dynamics.",
        "speech_patterns": ["Here's a historical parallel—", "I want to push back on the framing.", "The conventional wisdom is X, but look at the data.", "This is the third time we've seen this pattern."],
        "avoid": ["Excessive hedging", "Agreeing with both without adding value"],
        "topic_keywords": ["trade", "tariff", "sanctions", "geopolitics", "macro", "international", "export", "import", "treaty", "diplomacy"],
    },
    "priya": {
        "name": "Priya Nair",
        "role": "AI & emerging tech specialist",
        "type": "rotating",
        "personality": "Patient explainer who challenges hype with implementation reality. Deep knowledge of AI infrastructure, semiconductors, and deep tech. Bridges research to real-world deployment.",
        "speech_patterns": ["Let me break down what's actually happening under the hood.", "The benchmark says one thing, but in production—", "People keep confusing capability with deployment.", "Here's what the researchers actually found—"],
        "avoid": ["Dismissing genuine breakthroughs", "Over-simplifying technical concepts", "Academic jargon without translation"],
        "topic_keywords": ["ai", "artificial intelligence", "machine learning", "semiconductor", "chip", "deep tech", "neural", "model", "compute", "gpu"],
    },
    "marcus": {
        "name": "Marcus Cole",
        "role": "Policy & regulation correspondent",
        "type": "rotating",
        "personality": "Former Hill staffer energy. Wry sense of humor, cause-and-effect reasoning. Connects regulation to market impact. Understands legislative process and how DC actually works.",
        "speech_patterns": ["Here's how this actually plays out in practice—", "The bill says one thing, but the enforcement mechanism—", "I've seen this movie before on the Hill.", "Follow the committee jurisdiction—that tells you everything."],
        "avoid": ["Partisan framing", "Assuming regulation is inherently bad or good", "Ignoring implementation details"],
        "topic_keywords": ["regulation", "antitrust", "privacy", "legislation", "congress", "executive order", "policy", "ftc", "sec", "doj", "compliance"],
    },
    "sam": {
        "name": "Sam Torres",
        "role": "Startup & venture correspondent",
        "type": "rotating",
        "personality": "Founder-fluent and energetic. Deep venture network. Pushes back when Chuck or Jessica are too quick to dismiss startups. Knows valuations and the founder mindset.",
        "speech_patterns": ["Talk to any founder in this space and they'll tell you—", "That valuation actually makes sense when you look at—", "The round tells you one thing, the cap table tells you another.", "Don't sleep on this one."],
        "avoid": ["Uncritical startup boosterism", "Ignoring burn rate reality", "Dismissing incumbents"],
        "topic_keywords": ["startup", "venture", "funding", "ipo", "unicorn", "series", "seed", "vc", "founder", "valuation", "acquisition"],
    },
    "jordan": {
        "name": "Jordan Blake",
        "role": "Consumer & culture analyst",
        "type": "rotating",
        "personality": "Bridges tech to ordinary people. Slightly irreverent, consumer-first perspective. Understands product adoption, creator economy, and cultural trends that drive markets.",
        "speech_patterns": ["Here's what normal people actually think about this—", "My group chat lit up when this dropped.", "The product is fine, but the timing is—", "This is a vibes thing more than a metrics thing."],
        "avoid": ["Being dismissive of enterprise/B2B", "Over-indexing on Twitter discourse", "Confusing online sentiment with market reality"],
        "topic_keywords": ["consumer", "product launch", "social media", "adoption", "creator", "culture", "retail", "brand", "user", "app"],
    },
}

ROTATING_HOSTS = [k for k, v in PERSONAS.items() if v.get("type") == "rotating"]

# ─── Unified system prompt ───────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the head writer for "The Signal," a three-daily business, tech, and policy podcast.

{edition_label} EDITION ({publish_time} EST) — 12 minutes target (~1,680 words spoken at 140 wpm)

EDITION IDENTITY — CRITICAL:
This is the {edition_word} edition. Hosts MUST say "{edition_word} edition" in the intro.
NEVER call this the "morning edition" or "morning episode" unless this IS the morning edition.
References to events that happened "this morning" or "earlier today" are fine —
but the SHOW ITSELF is always the {edition_word} edition.

HOSTS: Chuck Leblanc (business anchor) and Jessica Waverly (tech correspondent) are in every episode.
The crossover host for this episode is {guest_name} ({guest_role}).

STRUCTURE:

[PRE-INTRO SPONSOR — 0:00–0:30 — ~70 words]  (if sponsor provided for this slot)
The designated host reads the provided sponsor script verbatim. Format: [HOST_NAME - reading sponsor]: "script text"

[INTRO — 0:30–1:00 — ~70 words]
Quick, energetic open. "Welcome to The Signal {edition_word} edition." Date and episode number, fast.
Introduce today's crossover guest briefly.

[POST-INTRO SPONSOR — 1:00–1:30 — ~70 words]  (if sponsor provided for this slot)
The designated host reads the provided sponsor script verbatim. Format: [HOST_NAME - reading sponsor]: "script text"

[BUSINESS BLOCK — 1:30–4:30 — ~420 words]
2 business stories, ~2 min each. Chuck leads each one.
Format per story: headline → key fact or number → debate with Jessica → so-what.
One sharp exchange per story.

[CROSSOVER SEGMENT — 4:30–7:30 — ~420 words]
1 crossover story, ~3 min. {guest_name} joins.
This is the segment where the guest brings their specialty. At least ONE real disagreement.
Chuck or Jessica can push back. Real tension, not politeness.

[TECH BLOCK — 7:30–10:30 — ~420 words]
2 tech stories, ~2 min each. Jessica leads each one.
Format per story: headline → key detail → Chuck reacts → Jessica wraps.

[PRE-OUTRO SPONSOR — 10:30–11:00 — ~70 words]  (if sponsor provided for this slot)
The designated host reads the provided sponsor script verbatim. Format: [HOST_NAME - reading sponsor]: "script text"

[WRAP + SIGNOFF — 11:00–12:00 — ~140 words]
What to watch next. Quick callback to the sharpest exchange.
Warm but quick signoff. "Stay sharp." or similar.

NATURALNESS — THIS IS CRITICAL:
The listener should NOT feel like the hosts are reading from a script. Write dialogue that
sounds like smart people talking to each other over coffee.
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
- DO: interruptions, half-sentences, "Hold on—", "Actually—", real tension
- 2+ data points per story. At least 2 genuine disagreements total.

SPOKEN TEXT ONLY — CRITICAL:
Everything inside quotation marks MUST be spoken dialogue only. NEVER put inside quotes:
- Parenthetical directions: NO "(laughs)", "(turning to Jessica)", "(pause)"
- Bracketed directions: NO "[laughs]", "[transition]", "[beat]"
- Asterisk actions: NO "*laughs*", "*pauses*", "*sighs*"
- Explicit transition phrases: NO "moving on to tech news" or "turning to our next story"
All acting directions belong in the bracket BEFORE the colon: [HOST - direction]: "dialogue"
The quotes contain ONLY words the host says out loud.

SPONSOR RULES:
- Sponsors specify a "voice" and a "script" field. Use the designated host and read the script verbatim.
- Only include sponsor spots for slots that have sponsors provided. Skip empty slots.

FORMAT: [HOST_NAME - acting direction]: "dialogue"
Return complete script only. No headers or commentary outside the script."""


def select_crossover_host(crossover_story: dict, episode_num: int) -> str:
    """
    Select the best rotating crossover host for the given story.
    Topic-weighted with round-robin fallback.
    """
    if not crossover_story:
        return ROTATING_HOSTS[episode_num % len(ROTATING_HOSTS)]

    # Build text to match against
    story_text = (
        crossover_story.get("podcast_headline", "") + " " +
        crossover_story.get("context", "") + " " +
        crossover_story.get("summary", "")
    ).lower()

    # Score each rotating host
    scores = {}
    for host_key in ROTATING_HOSTS:
        persona = PERSONAS[host_key]
        keywords = persona.get("topic_keywords", [])
        score = sum(1 for kw in keywords if kw in story_text)
        scores[host_key] = score

    # If there's a clear winner, use them
    max_score = max(scores.values())
    if max_score > 0:
        winners = [h for h, s in scores.items() if s == max_score]
        if len(winners) == 1:
            return winners[0]
        # Tiebreak with episode number
        return winners[episode_num % len(winners)]

    # No strong match — round-robin fallback
    return ROTATING_HOSTS[episode_num % len(ROTATING_HOSTS)]


class ScriptwriterAgent:

    DURATION_TARGETS = {
        "morning": {"target": 12, "min": 10, "max": 15, "wpm": 140},
        "midday":  {"target": 12, "min": 10, "max": 15, "wpm": 140},
        "evening": {"target": 12, "min": 10, "max": 15, "wpm": 140},
    }

    def run(self, brief: dict, episode_num: int, episode_date: str, edition: str) -> dict:
        edition = edition.lower()
        targets = self.DURATION_TARGETS[edition]
        sponsors = brief.get("sponsors", self._placeholder_sponsors())

        # Select crossover host
        overlap_stories = brief.get("overlap_stories", [])
        crossover_story = overlap_stories[0] if overlap_stories else None
        crossover_host = select_crossover_host(crossover_story, episode_num)

        script_text = self._write_script(brief, episode_num, episode_date, edition, sponsors, crossover_host)
        est = self._estimate_duration(script_text, targets["wpm"])
        log.info(f"  First draft: ~{est:.1f} min ({edition.capitalize()})")

        if est < targets["min"]:
            gap = targets["target"] - est
            log.info(f"  Expanding ({gap:.1f} min short)...")
            script_text = self._expand_script(script_text, brief, gap, edition)
        elif est > targets["max"]:
            overage = est - targets["target"]
            log.info(f"  Trimming ({overage:.1f} min over)...")
            script_text = self._trim_script(script_text, overage, edition)

        final_est = self._estimate_duration(script_text, targets["wpm"])
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
                "cta": "Get started free at thesignalpod.com/sponsor",
            },
        ]

    def _write_script(self, brief: dict, episode_num: int, episode_date: str,
                      edition: str, sponsors: list, crossover_host: str) -> str:
        guest = PERSONAS[crossover_host]
        edition_labels = {"morning": "MORNING", "midday": "MIDDAY", "evening": "EVENING"}
        edition_words = {"morning": "morning", "midday": "midday", "evening": "evening"}
        publish_times = {"morning": "7:00 AM", "midday": "1:00 PM", "evening": "5:30 PM"}
        targets = self.DURATION_TARGETS[edition]

        system_prompt = SYSTEM_PROMPT.format(
            edition_label=edition_labels[edition],
            publish_time=publish_times[edition],
            edition_word=edition_words[edition],
            guest_name=guest["name"],
            guest_role=guest["role"],
        )

        # Build personas for prompt — static hosts + selected guest
        active_personas = {
            "chuck": PERSONAS["chuck"],
            "jessica": PERSONAS["jessica"],
            crossover_host: guest,
        }

        word_target = int(targets["target"] * targets["wpm"])

        # Sponsor slot instructions
        sponsor_slots = {"pre-intro": None, "post-intro": None, "pre-outro": None}
        for s in sponsors:
            slot = s.get("slot", "")
            if slot in sponsor_slots:
                sponsor_slots[slot] = s

        sponsor_instruction = "Include sponsor spots ONLY for slots that have sponsors provided below. Skip empty slots."

        prompt = f"""Write the complete {edition_labels[edition]} EDITION script for The Signal.

Episode: {episode_num} | Date: {episode_date} | Edition: {edition.capitalize()}
Theme: {brief.get("show_theme", "")}
Hook: {brief.get("episode_hook", "")}
Stories: {len(brief.get("business_stories",[]))} business, {len(brief.get("tech_stories",[]))} tech, {len(brief.get("overlap_stories",[]))} overlap
Crossover guest: {guest["name"]} ({guest["role"]})

HOST PERSONAS:
{json.dumps(active_personas, indent=2)}

SPONSORS:
{json.dumps(sponsors, indent=2)}

EDITORIAL BRIEF:
{json.dumps(brief, indent=2)}

Write the COMPLETE {targets["target"]}-minute script (~{word_target} words of spoken dialogue).
{sponsor_instruction}
Begin immediately with the intro dialogue (or pre-intro sponsor if one is provided). No preamble."""

        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=12000,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def _estimate_duration(self, script: str, wpm: int = 140) -> float:
        import re
        lines = re.findall(r'\]: "([^"]+)"', script)
        words = sum(len(l.split()) for l in lines)
        return words / wpm

    def _expand_script(self, script: str, brief: dict, min_short: float, edition: str) -> str:
        targets = self.DURATION_TARGETS[edition]
        words_needed = int(min_short * targets["wpm"])

        prompt = f"""This podcast script is {min_short:.1f} minutes short. Add ~{words_needed} words by:

1. Adding a quick reaction or back-and-forth to the thinnest story
2. Slightly expanding the crossover segment with one more exchange
3. Adding one more specific detail or number to the biggest story

Keep all sponsor spots intact. Keep it conversational and fast-paced.
Return the COMPLETE expanded script.

SCRIPT:
{script}"""
        r = client.messages.create(model="claude-sonnet-4-6", max_tokens=12000,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text

    def _trim_script(self, script: str, min_over: float, edition: str = "morning") -> str:
        targets = self.DURATION_TARGETS[edition]
        words_cut = int(min_over * targets["wpm"])

        prompt = f"""This podcast script is {min_over:.1f} minutes too long. Remove ~{words_cut} words by:

1. Cutting any exchange that goes beyond one quick back-and-forth per story
2. Removing redundant reactions or repeated points
3. Tightening the intro and signoff

DO NOT cut: any sponsor spots.
Every line should earn its place.
Return the COMPLETE trimmed script.

SCRIPT:
{script}"""
        r = client.messages.create(model="claude-sonnet-4-6", max_tokens=12000,
                                   messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
