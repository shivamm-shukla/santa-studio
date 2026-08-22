"""Factory: resolves config.ACTIVE_PROVIDERS[kind] -> a concrete provider
instance. This is the only place that imports concrete provider classes -
agents and the manager only ever go through get_provider().
"""

from providers.caption.whisper_provider import WhisperProvider
from providers.llm.cerebras_provider import CerebrasProvider
from providers.llm.claude_provider import ClaudeProvider
from providers.llm.fallback_provider import FallbackLLMProvider
from providers.llm.gemini_provider import GeminiProvider
from providers.llm.groq_provider import GroqProvider
from providers.llm.openrouter_provider import OpenRouterProvider
from providers.llm.router import RouterLLMProvider
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
        "cerebras": CerebrasProvider,
        "openrouter": OpenRouterProvider,
        # Tries every free tier that has a key, skipping ones already out of
        # quota for the day. This is the one to use.
        "router": RouterLLMProvider,
        # The original two-step chain, kept so existing configs keep working.
        "fallback": FallbackLLMProvider,
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
