from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are a veteran YouTube scriptwriter known for scripts that hook "
    "viewers in the first 15 seconds and hold retention throughout, "
    "whether that's a 3-minute short-form video or a 20-minute deep dive. "
    "You write in a natural, spoken voice - not an essay."
)

WORDS_PER_MINUTE = 150  # rough average spoken pace, for pacing guidance


def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, verified_claims: list[str],
               target_length_minutes: int}
    Output: {script_text: str, scenes: list[dict]}
    Each scene: {timestamp_estimate, text, visual_hint}
    """
    research_summary = input_data.get("research_summary", "")
    claims = input_data.get("verified_claims", [])
    target_length_minutes = input_data.get("target_length_minutes", 5)
    target_word_count = target_length_minutes * WORDS_PER_MINUTE

    prompt = (
        f"Research summary: {research_summary!r}\n"
        f"Verified claims to build the script around: {claims}\n"
        f"Target video length: ~{target_length_minutes} minutes "
        f"(~{target_word_count} spoken words total).\n"
        "Write a YouTube video script as a list of scenes: a hook scene, "
        "then enough scenes to actually hit the target length - for a short "
        "video that's roughly one scene per claim, but for a longer target "
        "you should go deeper on each claim (examples, context, implications, "
        "a short story or analogy) rather than padding with filler, and add "
        "more scenes as needed - then a recap/CTA scene. Each scene needs a "
        "timestamp_estimate (e.g. '0:00-0:15'), the spoken text, and a "
        "visual_hint describing what footage should play.\n"
        'Respond with ONLY a JSON object: {"scenes": [{"timestamp_estimate": "...", '
        '"text": "...", "visual_hint": "..."}]}'
    )

    try:
        provider = get_provider("llm", config)
        parsed = call_llm_json(provider, prompt, SYSTEM)
        scenes = parsed.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError(f"Expected non-empty 'scenes' list, got: {parsed}")
        script_text = "\n".join(scene.get("text", "") for scene in scenes)
        return {"success": True, "output": {"script_text": script_text, "scenes": scenes}, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
