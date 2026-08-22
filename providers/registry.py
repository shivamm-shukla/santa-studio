"""Factory: resolves config.ACTIVE_PROVIDERS[kind] -> a concrete provider
instance. This is the only place that imports concrete provider classes -
agents and the manager only ever go through get_provider().
"""

from providers.caption.whisper_provider import WhisperProvider
from providers.llm.claude_provider import ClaudeProvider
from providers.llm.fallback_provider import FallbackLLMProvider
from providers.llm.gemini_provider import GeminiProvider
from providers.llm.groq_provider import GroqProvider
from providers.music.ambient_music_provider import AmbientMusicProvider
from providers.publish.youtube_provider import YouTubeProvider
from providers.visual.pexels_provider import PexelsProvider
from providers.visual.pixabay_provider import PixabayProvider
from providers.visual.wikimedia_provider import WikimediaProvider
from providers.voice.gtts_provider import GTTSProvider
from providers.voice.xtts_provider import XTTSProvider

_REGISTRY = {
    "llm": {
        "claude": ClaudeProvider,
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "fallback": FallbackLLMProvider,  # tries Gemini, then Groq
    },
    "voice": {
        "gtts": GTTSProvider,  # free, no setup, but does not clone
        "xtts": XTTSProvider,  # real cloning; needs `pip install coqui-tts`
    },
    "visual": {
        "pexels": PexelsProvider,
        "pixabay": PixabayProvider,
        "wikimedia": WikimediaProvider,
    },
    "caption": {
        "whisper": WhisperProvider,
    },
    "music": {
        "ambient": AmbientMusicProvider,
    },
    "publish": {
        "youtube": YouTubeProvider,
    },
}


def get_provider(kind: str, config: dict):
    name = config["ACTIVE_PROVIDERS"][kind]
    try:
        provider_cls = _REGISTRY[kind][name]
    except KeyError:
        raise ValueError(f"No provider registered for kind={kind!r}, name={name!r}")
    return provider_cls()
