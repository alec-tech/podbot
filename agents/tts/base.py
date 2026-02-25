"""
agents/tts/base.py — TTS Provider Abstract Base + VoiceConfig
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VoiceConfig:
    """Per-host, per-provider voice configuration."""
    host_name: str
    voice_id: str
    provider_settings: dict = field(default_factory=dict)


class TTSProvider(ABC):
    """Abstract base class for TTS providers."""

    @abstractmethod
    def synthesize(self, text: str, voice_config: VoiceConfig,
                   output_path: str, direction: str = "") -> str:
        """
        Synthesize text to audio file.

        Args:
            text: The dialogue text to synthesize.
            voice_config: Voice configuration for this host/provider.
            output_path: Where to write the audio file.
            direction: Acting direction (e.g., "excited", "measured").

        Returns:
            The output_path on success.

        Raises:
            Exception on failure.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider is configured and ready (API key present, etc.)."""
        ...
