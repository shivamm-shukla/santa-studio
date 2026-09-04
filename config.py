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
    # "router" tries every free tier that has a key configured - Gemini,
    # Groq, Cerebras, OpenRouter - skipping any already out of quota for the
    # day rather than burning a failed request on it. Set to "claude" instead
    # once/if a paid Anthropic key is added, for better quality on a budget
    # that allows it.
    "llm": "router",
    # "gtts" is the zero-setup default: free and instant, but one fixed
    # voice that ignores the uploaded sample entirely. "xtts" clones from a
    # sample, but its weights are CPML-licensed (non-commercial) - see
    # providers/voice/xtts_provider.py before switching.
    # Resolved per run by _voice_provider(): a cloning provider when one is
    # installed, gTTS when none is.
    "voice": "gtts",
    "visual": "pexels",
    "caption": "whisper",
    "music": "ambient",
    # None = don't upload anywhere; the run ends at DONE with the file.
    # Resolved per-run by _publish_target(): connecting a YouTube account is
    # what turns publishing on, so it is never a code edit.
    "publish": None,
}

REVIEW_MODE = os.getenv("REVIEW_MODE", "autonomous")

# Which look the editor cuts to when a run has no reference channel to learn
# one from. A run *with* a reference overrides this with what it measured, so
# this is the floor rather than the setting. Presets live in style_profile.py;
# a profile learned from a reference is saved into the library under the
# channel's name and can be named here to reuse it on later runs.
STYLE_PROFILE = os.getenv("STYLE_PROFILE", "documentary")

# How long a video is when nobody says. Every front end can override it per
# run; this is what a run started with nothing but a topic gets.
#
# Above six minutes the script is outlined and then written a chapter at a
# time - see agents/script_agent.py - which is what makes a long video
# actually arrive at its length, and which costs one LLM request per chapter
# on top of the outline. On a free tier counted in requests per day, that is
# the reason this is a setting rather than simply being raised.
VIDEO_LENGTH_MINUTES = int(os.getenv("VIDEO_LENGTH_MINUTES", "5"))

# Language of everything the viewer sees or hears - script, thumbnail text,
# title, description, tags. "en" | "hi" | "hinglish". Also picks the voice
# and caption language downstream. Research still happens in English, since
# the sources are, and only the viewer-facing output is translated.
OUTPUT_LANGUAGE = os.getenv("OUTPUT_LANGUAGE", "hinglish")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


# "youtube", or "none" to keep runs ending at the finished file even with an
# account connected. Unset means "publish if an account is connected".
PUBLISH_TARGET = os.getenv("PUBLISH_TARGET", "").strip().lower()

# "chatterbox" | "xtts" | "gtts". Unset picks the best installed one.
VOICE_PROVIDER = os.getenv("VOICE_PROVIDER", "").strip().lower()


def _voice_provider() -> str:
    """Which voice provider a run should use.

    gTTS cannot clone. It was the hardcoded default, so choosing a voice
    profile in the UI changed nothing audible - the profile was resolved,
    handed to the provider, and ignored, and every run came out in the same
    stock voice.

    Chatterbox is preferred because it clones and its weights are MIT, which
    XTTS-v2's are not (CPML forbids commercial use - see §4.1 of the
    roadmap). Falling back keeps a run working on a machine where neither is
    installed; the caller still drops to gTTS when there is no profile to
    clone from, because a cloning provider with no reference is worse than a
    stock voice.
    """
    if VOICE_PROVIDER:
        return VOICE_PROVIDER

    try:
        from providers.voice import chatterbox_provider

        # Chatterbox lives in an interpreter of its own, so "is it importable
        # here" is the wrong question - it never will be.
        if chatterbox_provider.is_available():
            return "chatterbox"
    except Exception:
        pass
    return "gtts"


def _publish_target() -> str | None:
    """Whether a run should upload, and where.

    Publishing used to be a hardcoded None that only a code edit could
    change, so the two publish states in the state machine were unreachable
    no matter what the user did in the UI. Connecting an account is the
    thing that enables it - which is also why this is checked per run
    rather than once at import: an account connected while the server is up
    takes effect on the next run, not the next restart.
    """
    if PUBLISH_TARGET in ("none", "off", "0"):
        return None
    if PUBLISH_TARGET:
        return PUBLISH_TARGET
    try:
        from providers.publish.youtube_provider import auth_status

        return "youtube" if auth_status()["connected"] else None
    except Exception:
        # A missing optional dependency must not stop a run that was never
        # going to publish anyway.
        return None


def build_config() -> dict:
    return {
        "ACTIVE_PROVIDERS": {
            **ACTIVE_PROVIDERS,
            "voice": _voice_provider(),
            "publish": _publish_target(),
        },
        "REVIEW_MODE": REVIEW_MODE,
        "STYLE_PROFILE": STYLE_PROFILE,
        "OUTPUT_LANGUAGE": OUTPUT_LANGUAGE,
        "ANTHROPIC_API_KEY": ANTHROPIC_API_KEY,
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "GROQ_API_KEY": GROQ_API_KEY,
        "CEREBRAS_API_KEY": CEREBRAS_API_KEY,
        "OPENROUTER_API_KEY": OPENROUTER_API_KEY,
        "PEXELS_API_KEY": PEXELS_API_KEY,
        "PIXABAY_API_KEY": PIXABAY_API_KEY,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
