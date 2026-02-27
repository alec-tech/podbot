"""
agents/tts/ — TTS Provider Abstraction with Fallback Chain

Primary: Cartesia (sonic-3)
Fallback 1: OpenAI (gpt-4o-mini-tts)
Fallback 2: ElevenLabs (eleven_multilingual_v2)
"""

import json
import time
import logging
from pathlib import Path
from typing import Optional

from .base import TTSProvider, VoiceConfig
from .cartesia_provider import CartesiaProvider
from .openai_provider import OpenAIProvider
from .elevenlabs_provider import ElevenLabsProvider

log = logging.getLogger("tts")

PROVIDER_CLASSES = {
    "cartesia": CartesiaProvider,
    "openai": OpenAIProvider,
    "elevenlabs": ElevenLabsProvider,
}


def load_voice_config(host_name: str, provider_name: str, config: dict) -> Optional[VoiceConfig]:
    """
    Build a VoiceConfig for a given host and provider from show_config.json voices section.

    Args:
        host_name: e.g. "chuck"
        provider_name: e.g. "cartesia"
        config: The full show_config dict.
    """
    voices = config.get("voices", {})
    host_config = voices.get(host_name)
    if not host_config:
        return None
    providers = host_config.get("providers", {})
    provider_config = providers.get(provider_name)
    if not provider_config:
        return None
    voice_id = provider_config.get("voice_id", "")
    if not voice_id or voice_id == "PLACEHOLDER":
        return None
    settings = {k: v for k, v in provider_config.items() if k != "voice_id"}
    return VoiceConfig(
        host_name=host_name,
        voice_id=voice_id,
        provider_settings=settings,
    )


class FallbackTTSChain:
    """
    Tries providers in order with per-provider retries and exponential backoff.
    Per-line: tries Cartesia 3x -> OpenAI 2x -> ElevenLabs 2x (configurable).
    """

    def __init__(self, config: dict):
        tts_config = config.get("tts", {})
        provider_order = tts_config.get("provider_order", ["cartesia", "openai", "elevenlabs"])
        retries = tts_config.get("retries_per_provider", [3, 2, 2])

        self._providers: list[tuple[str, TTSProvider, int]] = []
        for i, name in enumerate(provider_order):
            cls = PROVIDER_CLASSES.get(name)
            if not cls:
                log.warning(f"Unknown TTS provider: {name}")
                continue
            provider = cls()
            if provider.is_available():
                max_retries = retries[i] if i < len(retries) else 2
                self._providers.append((name, provider, max_retries))
                log.debug(f"TTS provider available: {name} (max {max_retries} retries)")
            else:
                log.info(f"TTS provider skipped (no API key): {name}")

        if not self._providers:
            raise RuntimeError("No TTS providers available. Set at least one API key.")

        self._config = config

    def synthesize_line(self, text: str, host_name: str, output_path: str,
                        direction: str = "") -> Optional[str]:
        """
        Synthesize a single line, falling back through providers on failure.

        Returns:
            The output_path on success, None if all providers fail.
        """
        for provider_name, provider, max_retries in self._providers:
            voice_config = load_voice_config(host_name, provider_name, self._config)
            if not voice_config:
                log.debug(f"No voice config for {host_name}/{provider_name}, skipping")
                continue

            for attempt in range(max_retries):
                try:
                    result = provider.synthesize(text, voice_config, output_path, direction)
                    log.debug(f"TTS success: {host_name} via {provider_name}")
                    return result
                except Exception as e:
                    log.warning(
                        f"TTS {provider_name} attempt {attempt + 1}/{max_retries} "
                        f"failed for {host_name}: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)

            log.warning(f"TTS provider {provider_name} exhausted for {host_name}, falling back")

        log.error(f"All TTS providers failed for {host_name}: {text[:50]}...")
        return None
