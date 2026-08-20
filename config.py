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
    "llm": "claude",
    "voice": "xtts",
    "visual": "pexels",
    "caption": "whisper",
}

REVIEW_MODE = os.getenv("REVIEW_MODE", "autonomous")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")


def build_config() -> dict:
    return {
        "ACTIVE_PROVIDERS": dict(ACTIVE_PROVIDERS),
        "REVIEW_MODE": REVIEW_MODE,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "PEXELS_API_KEY": PEXELS_API_KEY,
        "PIXABAY_API_KEY": PIXABAY_API_KEY,
    }
