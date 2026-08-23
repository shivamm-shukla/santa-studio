import runlog
from agents._llm_utils import call_llm_json
from providers.reference.analyzer import analyze_and_synthesize
from providers.reference.ingest import ingest_reference
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
    Output: {style_notes: str, structure_notes: str, angle_notes: str,
             style_profile: str, suggested_mood: str}

    IMPORTANT: this agent must never copy content from the reference URLs -
    only extract structural/stylistic patterns. Enforced above at the prompt
    level, not just documented here.
    """
    urls = input_data.get("urls", [])
    runlog.report(f"{len(urls)} reference URL(s) to analyse", progress=0.1)
    if not urls:
        runlog.report("Nothing to compare against - using the neutral default", progress=1.0)
        return {
            "success": True,
            "output": {
                "style_notes": "No reference material provided - using a neutral, fast-paced conversational default.",
                "structure_notes": "Hook -> main points -> recap -> CTA.",
                "angle_notes": "No specific angle bias.",
                "style_profile": "documentary",
                "suggested_mood": "curious",
            },
            "error": None,
        }

    # Ingest metadata from the primary reference URL
    primary_url = urls[0]
    runlog.report(f"Opening {primary_url}", progress=0.3)
    ingest_data = ingest_reference(primary_url)
    if ingest_data.get("title"):
        runlog.report(
            f"{ingest_data.get('title')} - {ingest_data.get('duration', 0):.0f}s, "
            f"~{ingest_data.get('word_count', 0)} words",
            progress=0.5,
        )

    metadata_context = ""
    if ingest_data.get("title"):
        metadata_context = (
            f"Reference Channel: {ingest_data.get('channel')}\n"
            f"Measured duration: {ingest_data.get('duration', 0):.0f}s\n"
            f"Word count estimate: {ingest_data.get('word_count', 0)}\n"
        )

    prompt = (
        f"Reference URLs: {urls}\n"
        f"{metadata_context}"
        "Analyze structure and stylistic patterns only (never copy actual content):\n"
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

        # Synthesize and save the learned StyleProfile
        runlog.report("Synthesising a style profile from the analysis", progress=0.8)
        profile = analyze_and_synthesize(ingest_data, llm_analysis=parsed, save_to_library=True)
        runlog.report(f"Saved style profile {profile.name!r}", progress=1.0)

        parsed["style_profile"] = profile.name
        parsed["suggested_mood"] = profile.music.mood_arc[0] if profile.music.mood_arc else "curious"

        return {"success": True, "output": parsed, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
