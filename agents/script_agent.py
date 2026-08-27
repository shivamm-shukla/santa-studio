import runlog
import sources as sourcing
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

# How many times the writer is shown its own invented figures and asked to
# write the scene again. Three, because a model that has not taken the
# point by the third draft is not going to take it on the fourth, and a
# run should not spend a day's allowance learning that.
DRAFTS = 3


def _unsupported(script_text: str, claims: list) -> list[str]:
    """Figures the narration states that no verified claim carries.

    The prompt is where the rule lives; this is how we find out whether it
    held. A number is the part of a claim that survives being rewritten into
    Hinglish, so it is the part that can be checked afterwards.
    """
    supported = set()
    for claim in claims:
        supported |= sourcing.figures(str(claim))
    return sorted(sourcing.figures(script_text) - supported)


def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, verified_claims: list[str],
               disputed_claims: list, target_length_minutes: int,
               style_notes: str, structure_notes: str, angle_notes: str}
    Output: {script_text: str, scenes: list[dict]}
    Each scene: {timestamp_estimate, text, visual_hint}
    """
    research_summary = input_data.get("research_summary", "")
    claims = input_data.get("verified_claims", [])
    target_length_minutes = input_data.get("target_length_minutes", 5)
    target_word_count = target_length_minutes * WORDS_PER_MINUTE

    # A script has to be written from something, and the only material this
    # channel may assert is what survived fact-checking. Handed an empty list
    # the model writes from the research summary instead - fluently, and
    # entirely out of claims the checker had just refused. One run narrated
    # all six of its flagged claims that way and shipped a sourcing document
    # saying they had been kept out. Refusing here is the difference between
    # a run that fails and a video that is wrong.
    if not claims:
        return {
            "success": False,
            "output": None,
            "error": (
                "Nothing survived fact-checking, so there is nothing this "
                "script is allowed to state. The research stage grounded on "
                "sources that do not support the topic - check those first."
            ),
        }

    runlog.report(
        f"Writing ~{target_word_count} words ({target_length_minutes} min) "
        f"from {len(claims)} verified claim(s)",
        progress=0.15,
    )

    # What the reference channels teach. Structure and pacing only - never
    # their content, which is enforced upstream in reference_agent's own
    # prompt and repeated here because this is where the writing happens.
    reference = ""
    for field, framing in (
        ("structure_notes", "How videos like this are built"),
        ("style_notes", "The tone and pacing to write in"),
        ("angle_notes", "The framing they take"),
    ):
        if input_data.get(field):
            reference += f"\n{framing}: {input_data[field]}"
    if reference:
        reference = (
            "\n\nWrite to the shape of the reference channel, in its register "
            "and at its pace. Take nothing else from it - no facts, no phrases, "
            "no examples. The substance is the verified claims and only those."
            + reference
        )

    context_extras = ""
    if input_data.get("disputed_claims"):
        context_extras += (
            "\nThe sources disagree on the following. Say that they disagree "
            "rather than picking one side: "
            f"{input_data['disputed_claims'][:3]}"
        )

    prompt = (
        "Background, for shape and tone only. It has not been fact-checked "
        f"and nothing may be stated on its authority: {research_summary!r}\n"
        f"The verified claims. Every factual statement in the script - every "
        f"date, figure, name and causal link - has to come from this list, "
        f"and nothing outside it may be asserted: {claims}\n"
        f"{context_extras}\n"
        "Do not introduce a date, a number or a name that is not in the list "
        "above, even if you are confident it is correct. If the verified "
        "material will not fill the target length, write a shorter video.\n"
        f"{reference}\n"
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

        # Telling a model not to invent figures gets most of the way there and
        # not all of it: one draft of this script narrated a ship stacking
        # "1000 containers" against "10,000 pallets", numbers that appear in no
        # source and were simply written. So the draft is checked, and where it
        # invented something it is shown exactly what and asked again. Rejecting
        # the run instead would fail a video over a sentence the writer can fix.
        correction = ""
        for draft in range(1, DRAFTS + 1):
            # The prompt asks for {"scenes": [...]} and the model regularly
            # sends the bare array instead. Naming the key means that arrives
            # as the script it is rather than as a parse failure.
            parsed = call_llm_json(provider, prompt + correction, SYSTEM, list_key="scenes")
            scenes = parsed.get("scenes")
            if not isinstance(scenes, list) or not scenes:
                raise ValueError(f"Expected non-empty 'scenes' list, got: {parsed}")
            script_text = "\n".join(scene.get("text", "") for scene in scenes)

            loose = _unsupported(script_text, claims)
            if not loose:
                break

            runlog.report(
                f"Draft {draft} states {len(loose)} figure(s) no verified claim "
                f"carries: {', '.join(loose[:8])}"
            )
            correction = (
                "\n\nYour previous draft stated these figures, and no verified "
                f"claim supports any of them: {loose}. They were invented. Write "
                "it again without them - cut the sentence, or replace the figure "
                "with one from the verified claims. Say less rather than "
                "guessing."
            )

        for scene in scenes[:8]:
            runlog.report(f"{scene.get('timestamp_estimate', '?')}  {str(scene.get('text', ''))[:90]}")
        runlog.report(
            f"{len(scenes)} scenes, {len(script_text.split())} words", progress=1.0
        )
        output = {"script_text": script_text, "scenes": scenes}

        # Three drafts in and still inventing. The video is worth more than the
        # figures are worth losing, so it ships - and the sourcing document
        # names them, because the alternative is a video quietly stating
        # numbers that nothing behind it supports.
        if loose:
            runlog.report(
                f"Shipping with {len(loose)} unsupported figure(s); sources.md will say so"
            )
            output["unsupported_figures"] = loose

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
