"""Shared helpers for agents that call the LLM provider and expect JSON back."""

import json
import re

# What the finished video should sound like. Agents that produce
# viewer-facing text append the matching instruction to their prompt, so
# the language is set once in config rather than baked into eight prompts.
#
# Everything the viewer READS stays in Latin script - captions, thumbnail
# text, titles - so no Devanagari font is needed anywhere in the render
# path. Only the text the voice READS ALOUD is Devanagari, because TTS
# pronounces romanised Hindi as if it were English and it comes out
# unintelligible. See script_agent for the two-field split that carries
# both.
LANGUAGE_INSTRUCTIONS = {
    "en": "Write all viewer-facing text in English.",
    "hi": (
        "Write all viewer-facing text in Hindi, in Latin script "
        "(transliterated), using natural spoken Hindi rather than literary "
        "or Sanskritised Hindi. Do not use Devanagari script."
    ),
    "hinglish": (
        "Write all viewer-facing text in Hinglish, in Latin script - the way "
        "Hindi speakers actually type on YouTube. Keep English words as "
        "English where a Hindi speaker would naturally say the English word "
        "(technology, mission, budget, update). Example of the register: "
        "'Aaj hum ek aisi technology ki baat karenge jo sab kuch badal degi.' "
        "Do not use Devanagari script."
    ),
}


# Hinglish is Hindi as far as speech and transcription are concerned - the
# English loanwords inside it are pronounced the way a Hindi speaker says
# them, not the way an English voice would.
SPEECH_LANGUAGE = {"en": "en", "hi": "hi", "hinglish": "hi"}


def speech_language(config: dict) -> str:
    """The TTS/ASR language code for the configured output language."""
    lang = (config.get("OUTPUT_LANGUAGE") or "en").lower()
    return SPEECH_LANGUAGE.get(lang, "en")


def needs_spoken_field(config: dict) -> bool:
    """True when the visible text and the spoken text differ."""
    return speech_language(config) != "en"


def spoken_field_instruction(config: dict) -> str:
    """Asks for the Devanagari twin of each scene's on-screen text."""
    if not needs_spoken_field(config):
        return ""
    return (
        "Additionally, give each scene a 'spoken' field: the exact same "
        "sentence written in Devanagari script, for text-to-speech to read "
        "aloud. English loanwords should be spelled phonetically in "
        "Devanagari there so they are pronounced correctly. The 'text' "
        "field stays in Latin script.\n"
    )


def language_instruction(config: dict) -> str:
    """The prompt fragment for the configured output language."""
    lang = (config.get("OUTPUT_LANGUAGE") or "en").lower()
    return LANGUAGE_INSTRUCTIONS.get(lang, LANGUAGE_INSTRUCTIONS["en"])


def call_llm_json(provider, prompt: str, system: str) -> dict:
    """Calls provider.complete(), extracts and parses a JSON object from the
    response text (tolerating markdown code fences), and returns it.
    Raises ValueError on any failure - callers should catch this and return
    the standard {"success": False, "error": ...} agent contract.
    """
    result = provider.complete(prompt, system=system)
    text = result["text"].strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response was not valid JSON: {e}. Text: {text[:200]}") from e
