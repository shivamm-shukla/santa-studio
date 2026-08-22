"""API keys, provider selection, and review-gate behavior.

REVIEW_MODE:
  "autonomous"  (default) - the pipeline runs topic -> assembly without
                 stopping, pausing only once at the end for final approval
                 before DONE.
  "checkpoints" - additionally pauses after research, script, and the
                 final assembled video (mirrors a more hands-on workflow).
"""

import os

from dotenv import load_dotenv

load_dotenv()

ACTIVE_PROVIDERS = {
    # "fallback" tries Gemini (free) then Groq (free) in order - no cost.
    # Set to "claude" instead once/if a paid Anthropic key is added, for
    # better quality on a budget that allows it.
    "llm": "fallback",
    # "gtts" is the zero-setup default: free and instant, but one fixed
    # voice that ignores the uploaded sample entirely. "xtts" clones from a
    # sample, but its weights are CPML-licensed (non-commercial) - see
    # providers/voice/xtts_provider.py before switching.
    "voice": "gtts",
    "visual": "pexels",
    "caption": "whisper",
    # None = don't upload anywhere; the run ends at DONE with the file.
    # Set to "youtube" once OAuth credentials are in place.
    "publish": None,
}

REVIEW_MODE = os.getenv("REVIEW_MODE", "autonomous")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


def build_config() -> dict:
    return {
        "ACTIVE_PROVIDERS": dict(ACTIVE_PROVIDERS),
        "REVIEW_MODE": REVIEW_MODE,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "GROQ_API_KEY": GROQ_API_KEY,
        "PEXELS_API_KEY": PEXELS_API_KEY,
        "PIXABAY_API_KEY": PIXABAY_API_KEY,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
