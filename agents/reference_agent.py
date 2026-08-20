def run(input_data: dict, config: dict) -> dict:
    """Input: {urls: list[str]}
    Output: {style_notes: str, structure_notes: str, angle_notes: str}

    IMPORTANT: this agent must never copy content from the reference URLs -
    only extract structural/stylistic patterns (pacing, tone, how a hook is
    built, how sections are ordered). Real implementation must enforce this
    at the prompt level once the LLM call is wired in.
    """
    urls = input_data.get("urls", [])
    return {
        "success": True,
        "output": {
            "style_notes": f"[stub] Fast-paced, conversational tone observed across {len(urls)} reference(s).",
            "structure_notes": "[stub] Hook (0-15s) -> 3 main points -> recap -> CTA.",
            "angle_notes": "[stub] Reference material leans contrarian/myth-busting in framing.",
        },
        "error": None,
    }
