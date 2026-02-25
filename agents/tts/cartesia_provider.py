"""
agents/tts/cartesia_provider.py — Cartesia TTS Provider (Primary)
Uses Cartesia SDK with sonic-3 model.
"""

import os
import logging
from .base import TTSProvider, VoiceConfig

log = logging.getLogger("tts.cartesia")


# Direction → speed multiplier mapping
DIRECTION_MAP = {
    "faster":   1.3,
    "excited":  1.3,
    "slower":   0.8,
    "measured": 0.8,
    "wry":      0.95,
    "dry":      0.95,
    "warm":     0.95,
    "urgent":   1.2,
}


class CartesiaProvider(TTSProvider):

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            from cartesia import Cartesia
            self._client = Cartesia(api_key=os.environ["CARTESIA_API_KEY"])
        return self._client

    def is_available(self) -> bool:
        return bool(os.getenv("CARTESIA_API_KEY"))

    def synthesize(self, text: str, voice_config: VoiceConfig,
                   output_path: str, direction: str = "") -> str:
        client = self._get_client()
        model_id = voice_config.provider_settings.get("model_id", "sonic-3")
        base_speed = voice_config.provider_settings.get("speed", 1.0)

        # Apply direction as speed modifier
        speed = base_speed
        if direction:
            for keyword, multiplier in DIRECTION_MAP.items():
                if keyword in direction.lower():
                    speed = multiplier
                    break
        gen_config = {"speed": speed}

        response = client.tts.generate(
            model_id=model_id,
            transcript=text,
            voice={"mode": "id", "id": voice_config.voice_id},
            output_format={"container": "mp3", "sample_rate": 44100, "bit_rate": 192000},
            speed=gen_config.get("speed", base_speed),
        )

        response.write_to_file(output_path)

        return output_path
