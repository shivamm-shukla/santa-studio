"""Abstract interfaces for every external AI capability the pipeline uses.

Agents never import a concrete provider class directly - they receive one
through providers.registry.get_provider(), driven by config.ACTIVE_PROVIDERS.
Swapping XTTS -> ElevenLabs or Pexels -> Storyblocks is a config change only.
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, prompt: str, system: str | None = None) -> dict:
        """Returns {"text": str, "raw": dict}"""
        ...


class VoiceProvider(ABC):
    @abstractmethod
    def clone_and_generate(self, script_text: str, voice_sample_path: str) -> dict:
        """Returns {"audio_path": str, "word_timestamps": list[dict]}"""
        ...


class VisualProvider(ABC):
    @abstractmethod
    def search(self, query: str, asset_type: str = "video") -> dict:
        """Returns {"asset_type": str, "asset_path": str}"""
        ...


class CaptionProvider(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str) -> dict:
        """Returns {"word_timestamps": list[dict]}"""
        ...


class MusicProvider(ABC):
    @abstractmethod
    def search(self, mood: str) -> dict:
        """Returns {"track_path": str}"""
        ...
