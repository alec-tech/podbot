"""
agents/tts/cartesia_provider.py — Cartesia TTS Provider (Primary)
Uses Cartesia SDK with sonic-3 model.
"""

import os
import logging
from .base import TTSProvider, VoiceConfig

log = logging.getLogger("tts.cartesia")


# Direction → generation_config mapping
DIRECTION_MAP = {
    "faster":  {"speed": 1.3, "emotion": ["excited"]},
    "excited": {"speed": 1.3, "emotion": ["excited"]},
    "slower":  {"speed": 0.8, "emotion": ["calm"]},
    "measured": {"speed": 0.8, "emotion": ["calm"]},
    "wry":     {"speed": 0.95, "emotion": ["curious"]},
    "dry":     {"speed": 0.95, "emotion": ["curious"]},
    "warm":    {"speed": 0.95, "emotion": ["positivity"]},
    "urgent":  {"speed": 1.2, "emotion": ["surprise"]},
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

        # Build generation config from direction
        gen_config = {"speed": base_speed}
        if direction:
            for keyword, settings in DIRECTION_MAP.items():
                if keyword in direction.lower():
                    gen_config.update(settings)
                    break

        output = client.tts.generate(
            model_id=model_id,
            transcript=text,
            voice_id=voice_config.voice_id,
            output_format={"container": "mp3", "sample_rate": 44100, "bit_rate": 192000},
            _experimental_voice_controls=gen_config,
        )

        with open(output_path, "wb") as f:
            f.write(output["audio"])

        return output_path
