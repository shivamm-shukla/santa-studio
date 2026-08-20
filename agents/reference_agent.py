from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are an expert video editor and content analyst. You study reference "
    "videos to extract STRUCTURAL and STYLISTIC patterns only - pacing, tone, "
    "how hooks are built, how sections are ordered, framing/angle choices. "
    "You NEVER quote, summarize the specific content of, or reproduce any "
    "text, facts, or claims from the reference material. If you cannot access "
    "a URL's content, describe general patterns typical of that platform/genre "
    "instead of guessing at the specific video's content."
)


def run(input_data: dict, config: dict) -> dict:
    """Input: {urls: list[str]}
    Output: {style_notes: str, structure_notes: str, angle_notes: str}

    IMPORTANT: this agent must never copy content from the reference URLs -
    only extract structural/stylistic patterns. Enforced above at the prompt
    level, not just documented here.
    """
    # TODO: wire the web_fetch server tool so Claude can actually read the
    # reference pages/transcripts instead of reasoning about the URLs blind.
    urls = input_data.get("urls", [])
    if not urls:
        return {
            "success": True,
            "output": {
                "style_notes": "No reference material provided - using a neutral, fast-paced conversational default.",
                "structure_notes": "Hook -> main points -> recap -> CTA.",
                "angle_notes": "No specific angle bias.",
            },
            "error": None,
        }

    prompt = (
        f"Reference URLs (analyze structure/style patterns only, never content): {urls}\n"
        "Describe: (1) style_notes - tone, pacing, delivery style; "
        "(2) structure_notes - how the video is typically organized/sectioned; "
        "(3) angle_notes - the typical framing/angle/contrarian-or-not stance.\n"
        'Respond with ONLY a JSON object: {"style_notes": "...", "structure_notes": "...", "angle_notes": "..."}'
    )

    try:
        provider = get_provider("llm", config)
        parsed = call_llm_json(provider, prompt, SYSTEM)
        for key in ("style_notes", "structure_notes", "angle_notes"):
            if not parsed.get(key):
                raise ValueError(f"Missing or empty '{key}' in LLM response: {parsed}")
        return {"success": True, "output": parsed, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
