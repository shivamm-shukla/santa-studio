from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are a veteran YouTube scriptwriter known for scripts that hook "
    "viewers in the first 15 seconds and hold retention throughout. You "
    "write in a natural, spoken voice - not an essay."
)


def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, verified_claims: list[str]}
    Output: {script_text: str, scenes: list[dict]}
    Each scene: {timestamp_estimate, text, visual_hint}
    """
    research_summary = input_data.get("research_summary", "")
    claims = input_data.get("verified_claims", [])

    prompt = (
        f"Research summary: {research_summary!r}\n"
        f"Verified claims to build the script around: {claims}\n"
        "Write a YouTube video script as a list of scenes: a hook scene, one "
        "scene per major claim, and a recap/CTA scene. Each scene needs a "
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
