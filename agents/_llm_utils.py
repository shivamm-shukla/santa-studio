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


def _complete_objects(text: str) -> list[dict]:
    """Every top-level JSON object in `text`, skipping anything unparseable.

    Used to rescue a reply that was cut off mid-array. Decoding starts at each
    `{` and jumps past whatever it consumed, so nested objects are not
    collected twice and a truncated wrapper is simply stepped over.
    """
    decoder = json.JSONDecoder()
    found: list[dict] = []
    index = text.find("{")

    while index != -1:
        try:
            obj, end = decoder.raw_decode(text[index:])
        except Exception:
            index = text.find("{", index + 1)
            continue
        if isinstance(obj, dict):
            found.append(obj)
            index = text.find("{", index + end)
        else:
            index = text.find("{", index + 1)

    return found


def call_llm_json(provider, prompt: str, system: str, list_key: str | None = None) -> dict:
    """Calls provider.complete(), extracts and parses a JSON object from the
    response text (tolerating markdown code fences and conversational commentary),
    and returns it. Raises ValueError on any failure - callers should catch this
    and return the standard {"success": False, "error": ...} agent contract.

    `list_key` is for the agents that ask for an object wrapping a list and are
    sometimes handed the bare list instead. Given one, a top-level array comes
    back as {list_key: [...]}.

    A top-level array with no `list_key` is an error rather than a best guess.
    It used to fall through to the brace scan below, which found the array's
    *first object* and returned that - so a script of nine scenes arrived as
    one scene and everything after it was silently dropped. A visible failure
    is better than four fifths of a video.
    """
    result = provider.complete(prompt, system=system)
    text = result["text"].strip()

    def wrap(data):
        """A parsed value as the dict the caller expects, or None if it is not one."""
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and list_key:
            return {list_key: data}
        if isinstance(data, list):
            raise ValueError(
                f"LLM returned a top-level array of {len(data)} item(s) and this "
                f"caller expects an object: {str(data)[:200]}"
            )
        return None

    # 1. Direct parse attempt
    try:
        parsed = json.loads(text)
    except Exception:
        parsed = None
    if parsed is not None:
        wrapped = wrap(parsed)
        if wrapped is not None:
            return wrapped

    # 2. Markdown code fences ```json { ... } ``` or ``` [ ... ] ```
    fence_match = re.search(r"```(?:json)?\s*([\{\[][\s\S]*?[\}\]])\s*```", text)
    if fence_match:
        try:
            wrapped = wrap(json.loads(fence_match.group(1)))
            if wrapped is not None:
                return wrapped
        except json.JSONDecodeError:
            pass

    # 3. A bare array anywhere in the text, before any brace scan. Order
    # matters: the brace scan below would find this array's first element and
    # return it as if it were the whole answer.
    start = text.find("[")
    while start != -1:
        try:
            array, _ = json.JSONDecoder().raw_decode(text[start:])
        except Exception:
            array = None
        if isinstance(array, list) and array:
            wrapped = wrap(array)
            if wrapped is not None:
                return wrapped
        start = text.find("[", start + 1)

    # 4. Salvage: as many complete objects as the reply contains.
    #
    # A model that runs out of output tokens mid-answer leaves a truncated
    # array - {"scenes": [ {...}, {...}, {... - which parses nowhere. The
    # brace scan below then finds the *first scene* and returns it as the
    # whole script, so a nine scene video arrived as one and nothing said so.
    # Collecting every complete object keeps the eight that did arrive.
    if list_key:
        salvaged = _complete_objects(text)
        if len(salvaged) > 1:
            try:
                import runlog

                runlog.report(
                    f"LLM reply was incomplete; kept {len(salvaged)} {list_key} "
                    f"from it rather than failing"
                )
            except Exception:
                pass
            return {list_key: salvaged}

    # 5. Progressive JSONDecoder.raw_decode from opening braces
    start = text.find("{")
    while start != -1:
        try:
            obj, _ = json.JSONDecoder().raw_decode(text[start:])
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        start = text.find("{", start + 1)

    # 6. Fallback greedy regex
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass

    raise ValueError(f"No valid JSON object found in LLM response: {text[:200]}")
