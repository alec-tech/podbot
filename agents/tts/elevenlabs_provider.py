"""
agents/tts/elevenlabs_provider.py — ElevenLabs TTS Provider (Fallback 2)
Extracted from the original voice_producer.py.
"""

import os
import logging
from .base import TTSProvider, VoiceConfig

log = logging.getLogger("tts.elevenlabs")


class ElevenLabsProvider(TTSProvider):

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from elevenlabs import ElevenLabs
            self._client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
        return self._client

    def is_available(self) -> bool:
        return bool(os.getenv("ELEVENLABS_API_KEY"))

    def _apply_direction(self, text: str, direction: str) -> str:
        """Modify text with SSML prosody based on acting direction."""
        direction = direction.lower()
        if "faster" in direction or "excited" in direction:
            return f"<speak><prosody rate='fast'>{text}</prosody></speak>"
        elif "slower" in direction or "measured" in direction:
            return f"<speak><prosody rate='slow'>{text}</prosody></speak>"
        return text

    def synthesize(self, text: str, voice_config: VoiceConfig,
                   output_path: str, direction: str = "") -> str:
        from elevenlabs import VoiceSettings

        client = self._get_client()
        settings = voice_config.provider_settings

        voice_settings = VoiceSettings(
            stability=settings.get("stability", 0.50),
            similarity_boost=settings.get("similarity_boost", 0.75),
            style=settings.get("style", 0.40),
            use_speaker_boost=True,
        )

        # Apply SSML direction
        processed_text = self._apply_direction(text, direction) if direction else text

        audio = client.text_to_speech.convert(
            voice_id=voice_config.voice_id,
            text=processed_text,
            model_id="eleven_multilingual_v2",
            voice_settings=voice_settings,
        )

        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        return output_path
