import runlog
import sources as sourcing
import spoken_register
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

# What "spoken, not an essay" actually means, said as instructions a draft
# can be checked against rather than as an adjective.
#
# The prompt this sits in is otherwise two hundred words of fact-checking
# constraint, and a model handed that much concrete instruction about
# accuracy and one vague clause about voice will satisfy the concrete one
# and write an encyclopedia entry. Which is what it was doing: correct,
# sourced, and narrated as though it were being read off a page.
CRAFT = """
How it has to be written, which matters as much as what it says:

Write it to be SPOKEN. Read every line back in your head; if you would not
say it out loud to one person sitting opposite you, rewrite it. Sentences
average about thirteen words - that is what fits in a breath. Vary them
hard: a nine-word sentence, then a four-word one, then a twenty-word one.
Uniform sentence length is what makes narration drone.

Talk to one viewer, not an audience. Second person. Ask them things. Let
them arrive at the conclusion a beat before you say it.

Never use a connective that only exists on the page - moreover, furthermore,
additionally, in conclusion, it is important to note, parantu, kintu,
uparokt. Speech uses "but", "so", "and here's the thing", "lekin", "aur".

Every scene ends owing the next one something. A question you have not
answered, a number that does not add up yet, a name you have not explained.
That debt is the only reason anyone watches scene four.

Facts are the payoff, not the delivery. Set up the tension first - what
should have happened, what everyone assumed - and let the verified fact land
as the turn. A figure stated flat is a fact; the same figure after a
question is a moment.

Be concrete. A person, a place, a time of day, an object. Abstractions are
what a reader can re-read and a listener cannot.
"""

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
        f"{CRAFT}\n"
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
            # The other half of what makes a draft unusable. A script can be
            # perfectly sourced and still be unwatchable, and the difference
            # is countable - see spoken_register for what is counted and why.
            reads_as_prose = spoken_register.problems(script_text)

            if not loose and not reads_as_prose:
                break

            correction = "\n\nRewrite it. What is wrong with the draft you just sent:"

            if loose:
                runlog.report(
                    f"Draft {draft} states {len(loose)} figure(s) no verified claim "
                    f"carries: {', '.join(loose[:8])}"
                )
                correction += (
                    "\n\nYou stated these figures, and no verified claim supports "
                    f"any of them: {loose}. They were invented. Write it again "
                    "without them - cut the sentence, or replace the figure with "
                    "one from the verified claims. Say less rather than guessing."
                )

            if reads_as_prose:
                runlog.report(f"Draft {draft} reads as prose: {reads_as_prose[0]}")
                correction += (
                    "\n\nIt reads as something written to be read, not said. "
                    + " ".join(reads_as_prose)
                    + " Keep the facts and the structure exactly as they are; "
                    "change how it is said."
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

        # Same reasoning, lower stakes. A script that still reads as prose
        # after three attempts is a watchable video with a flat narrator, not
        # a wrong one, so it ships - but the desk says so, because "the voice
        # sounds like someone reading" is the kind of thing that is obvious in
        # the finished file and invisible in the logs.
        if reads_as_prose:
            runlog.report(f"Shipping a draft that still reads as prose: {reads_as_prose[0]}")
            output["register_notes"] = reads_as_prose

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
