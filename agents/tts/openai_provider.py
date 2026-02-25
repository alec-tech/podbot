"""
agents/tts/openai_provider.py — OpenAI TTS Provider (Fallback 1)
Uses OpenAI SDK with gpt-4o-mini-tts model.
"""

import os
import logging
from .base import TTSProvider, VoiceConfig

log = logging.getLogger("tts.openai")


# Direction → natural language instructions
DIRECTION_INSTRUCTIONS = {
    "faster":  "Speak with energy and excitement, at a slightly faster pace.",
    "excited": "Speak with energy and excitement, at a slightly faster pace.",
    "slower":  "Speak slowly and deliberately, with careful measured pacing.",
    "measured": "Speak slowly and deliberately, with careful measured pacing.",
    "wry":     "Speak with subtle dry humor, slightly sardonic tone.",
    "dry":     "Speak with subtle dry humor, slightly sardonic tone.",
    "warm":    "Speak warmly and conversationally, like talking to a friend.",
    "urgent":  "Speak with urgency and emphasis, conveying importance.",
    "reading sponsor": "Read this naturally and conversationally, like a trusted recommendation.",
}


class OpenAIProvider(TTSProvider):

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        return self._client

    def is_available(self) -> bool:
        return bool(os.getenv("OPENAI_API_KEY"))

    def synthesize(self, text: str, voice_config: VoiceConfig,
                   output_path: str, direction: str = "") -> str:
        client = self._get_client()
        model = voice_config.provider_settings.get("model", "gpt-4o-mini-tts")
        voice = voice_config.voice_id
        base_instructions = voice_config.provider_settings.get("instructions", "")

        # Build instructions from direction
        direction_instruction = ""
        if direction:
            for keyword, instruction in DIRECTION_INSTRUCTIONS.items():
                if keyword in direction.lower():
                    direction_instruction = instruction
                    break

        instructions = f"{base_instructions} {direction_instruction}".strip() or None

        kwargs = {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": "mp3",
        }
        if instructions:
            kwargs["instructions"] = instructions

        response = client.audio.speech.create(**kwargs)
        response.stream_to_file(output_path)

        return output_path
