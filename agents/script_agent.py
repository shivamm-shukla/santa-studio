import runlog
from agents._llm_utils import (
    call_llm_json,
    language_instruction,
    needs_spoken_field,
    spoken_field_instruction,
)
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
    runlog.report(
        f"Writing ~{target_word_count} words ({target_length_minutes} min) "
        f"from {len(claims)} verified claim(s)",
        progress=0.15,
    )

    context_extras = ""
    if input_data.get("chronology"):
        context_extras += f"\nKey Chronological Milestones: {input_data['chronology'][:5]}"
    if input_data.get("numbers_and_data"):
        context_extras += f"\nKey Concrete Figures & Metrics: {input_data['numbers_and_data'][:6]}"
    if input_data.get("disputed_claims"):
        context_extras += f"\nDisputed / Alternative Perspectives: {input_data['disputed_claims'][:3]}"

    prompt = (
        f"Research summary: {research_summary!r}\n"
        f"Verified claims to build the script around: {claims}\n"
        f"{context_extras}\n"
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
        f"{language_instruction(config)} The visual_hint is a search query "
        "for a stock footage site, so keep that one in English.\n"
        + spoken_field_instruction(config)
        + 'Respond with ONLY a JSON object: {"scenes": [{"timestamp_estimate": "...", '
        '"text": "...", "spoken": "...", "visual_hint": "..."}]}'
    )

    try:
        provider = get_provider("llm", config)
        # The prompt asks for {"scenes": [...]} and the model regularly sends
        # the bare array instead. Naming the key means that arrives as the
        # script it is rather than as a parse failure.
        parsed = call_llm_json(provider, prompt, SYSTEM, list_key="scenes")
        scenes = parsed.get("scenes")
        if not isinstance(scenes, list) or not scenes:
            raise ValueError(f"Expected non-empty 'scenes' list, got: {parsed}")
        script_text = "\n".join(scene.get("text", "") for scene in scenes)
        for scene in scenes[:8]:
            runlog.report(f"{scene.get('timestamp_estimate', '?')}  {str(scene.get('text', ''))[:90]}")
        runlog.report(
            f"{len(scenes)} scenes, {len(script_text.split())} words", progress=1.0
        )
        output = {"script_text": script_text, "scenes": scenes}

        # For a non-English video the voice needs Devanagari to pronounce
        # the script correctly, while everything on screen stays in Latin
        # script. Fall back to the visible text if the model skipped the
        # field - a mispronounced video still beats no video.
        if needs_spoken_field(config):
            output["script_spoken"] = "\n".join(
                scene.get("spoken") or scene.get("text", "") for scene in scenes
            )
        return {"success": True, "output": output, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
