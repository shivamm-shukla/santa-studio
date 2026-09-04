"""Writing the script.

Two things about this stage are worth knowing before reading it.

The first is that a script is checked, not just generated. Three things about
a draft are measured rather than hoped for - whether every figure in it comes
from a verified claim, whether it reads as speech or as prose, and whether it
is anywhere near the length that was asked for - and a draft that fails one
is shown exactly what and asked again. All three are failures that shipped
silently before they were checked.

The second is that a long video is not written in one call. Asked for twenty
minutes in a single reply, every model here writes two or three - it hits
its output ceiling, or it simply stops, and the salvage path in call_llm_json
keeps whatever arrived. So above a few minutes the script is outlined first
and then written a chapter at a time against that outline, which is both how
the length is actually reached and how the video gets a spine instead of a
list.
"""

import checkpoints
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

OUTLINE_SYSTEM = (
    "You are a documentary story editor. You do not write prose; you decide "
    "what happens in what order, and why a viewer would still be watching at "
    "each point. You think in tension and payoff, not in topics."
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

# Above this, the script is outlined and written chapter by chapter. Below it
# a single call comfortably covers the whole thing, and outlining would spend
# an extra request from a daily allowance to arrange six scenes.
LONG_FORM_MINUTES = 6

# A draft this far under what was asked for is short enough to send back. Not
# tighter, because the writer is also told to say less rather than pad, and
# those two instructions have to be able to coexist.
MIN_LENGTH_RATIO = 0.75

# How many times a draft is shown its own faults and asked again. Three for a
# whole short script; two per chapter, because a long video has six or seven
# of them and a free tier is counted in requests per day.
DRAFTS = 3
CHAPTER_DRAFTS = 2

# How long a chapter should be. Short enough that a model reliably writes the
# whole thing, long enough that a video is not forty chapters of nothing.
CHAPTER_MINUTES = 2.5


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


def _too_short(script_text: str, target_words: int) -> int:
    """How many words a draft is short by, or 0 if it is long enough.

    This is the check that was missing, and its absence is why runs came out
    at one to three minutes against a five to twenty minute target. Nothing
    compared the draft against what had been asked for, so a model that
    stopped early - because it ran out of output tokens, or because it simply
    stopped - produced a short video and no error.
    """
    written = len(script_text.split())
    floor = int(target_words * MIN_LENGTH_RATIO)
    return max(0, floor - written)


def _faults(script_text: str, claims: list, target_words: int) -> dict:
    """Everything measurably wrong with a draft, in one place."""
    return {
        "loose": _unsupported(script_text, claims),
        "prose": spoken_register.problems(script_text),
        "short_by": _too_short(script_text, target_words),
    }


def _correction(faults: dict, target_words: int, written: int) -> str:
    """The faults, written as something a writer can act on.

    One string covering every fault rather than one redraft per fault: three
    round trips to fix three things is three times the allowance, and a
    writer given all of it at once fixes all of it at once.
    """
    if not any(faults.values()):
        return ""

    text = "\n\nRewrite it. What is wrong with the draft you just sent:"

    if faults["loose"]:
        text += (
            "\n\nYou stated these figures, and no verified claim supports "
            f"any of them: {faults['loose']}. They were invented. Write it "
            "again without them - cut the sentence, or replace the figure "
            "with one from the verified claims. Say less rather than guessing."
        )

    if faults["prose"]:
        text += (
            "\n\nIt reads as something written to be read, not said. "
            + " ".join(faults["prose"])
            + " Keep the facts and the structure exactly as they are; change "
            "how it is said."
        )

    if faults["short_by"]:
        text += (
            f"\n\nIt is far too short. You wrote {written} words and this "
            f"needs about {target_words}. Do not pad it and do not invent "
            "anything to fill it - go deeper on what is already there. Every "
            "claim has a story around it: who was involved, what they "
            "expected, what it cost, what changed afterwards, why anyone "
            "should care now. Write that."
        )

    return text


def _report_faults(faults: dict, draft: str) -> None:
    if faults["loose"]:
        runlog.report(
            f"{draft} states {len(faults['loose'])} figure(s) no verified claim "
            f"carries: {', '.join(faults['loose'][:8])}"
        )
    if faults["prose"]:
        runlog.report(f"{draft} reads as prose: {faults['prose'][0]}")
    if faults["short_by"]:
        runlog.report(f"{draft} is {faults['short_by']} words short")


def _scenes_from(parsed) -> list[dict]:
    scenes = parsed.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError(f"Expected non-empty 'scenes' list, got: {parsed}")
    return [scene for scene in scenes if isinstance(scene, dict)]


def _text_of(scenes: list[dict]) -> str:
    return "\n".join(scene.get("text", "") for scene in scenes)


def _write(provider, prompt: str, claims: list, target_words: int, attempts: int,
           label: str) -> tuple[list[dict], dict]:
    """One piece of script, redrafted until it measures up or runs out of tries.

    Returns the scenes and whatever was still wrong with them, so the caller
    can decide whether that is worth failing over - it usually is not, and
    saying so is more use than losing the run.
    """
    correction = ""
    scenes: list[dict] = []
    faults = {"loose": [], "prose": [], "short_by": 0}

    for attempt in range(1, attempts + 1):
        # The prompt asks for {"scenes": [...]} and the model regularly sends
        # the bare array instead. Naming the key means that arrives as the
        # script it is rather than as a parse failure.
        parsed = call_llm_json(provider, prompt + correction, SYSTEM, list_key="scenes")
        scenes = _scenes_from(parsed)
        text = _text_of(scenes)

        faults = _faults(text, claims, target_words)
        if not any(faults.values()):
            break

        _report_faults(faults, f"{label} draft {attempt}")
        correction = _correction(faults, target_words, len(text.split()))

    return scenes, faults


# --------------------------------------------------------------------------
# The shared half of every prompt
# --------------------------------------------------------------------------

def _material(input_data: dict, claims: list) -> str:
    """What the script is allowed to be built out of."""
    context_extras = ""
    if input_data.get("disputed_claims"):
        context_extras = (
            "\nThe sources disagree on the following. Say that they disagree "
            "rather than picking one side: "
            f"{input_data['disputed_claims'][:3]}"
        )

    return (
        "Background, for shape and tone only. It has not been fact-checked "
        f"and nothing may be stated on its authority: "
        f"{input_data.get('research_summary', '')!r}\n"
        "The verified claims. Every factual statement in the script - every "
        "date, figure, name and causal link - has to come from this list, and "
        f"nothing outside it may be asserted: {claims}\n"
        f"{context_extras}\n"
        "Do not introduce a date, a number or a name that is not in the list "
        "above, even if you are confident it is correct. If a claim will not "
        "carry the length asked of it, go deeper into what it implies rather "
        "than inventing more of them.\n"
    )


def _reference(input_data: dict) -> str:
    """What the reference channels teach.

    Structure and pacing only - never their content, which is enforced
    upstream in reference_agent's own prompt and repeated here because this
    is where the writing happens.
    """
    notes = ""
    for field, framing in (
        ("structure_notes", "How videos like this are built"),
        ("style_notes", "The tone and pacing to write in"),
        ("angle_notes", "The framing they take"),
    ):
        if input_data.get(field):
            notes += f"\n{framing}: {input_data[field]}"
    if not notes:
        return ""
    return (
        "\n\nWrite to the shape of the reference channel, in its register and "
        "at its pace. Take nothing else from it - no facts, no phrases, no "
        "examples. The substance is the verified claims and only those."
        + notes
    )


def _scene_contract(config: dict) -> str:
    """What one scene has to contain, and in what language."""
    return (
        "Each scene needs a timestamp_estimate (e.g. '0:00-0:15'), the spoken "
        "text, and a visual_hint describing what footage should play.\n"
        f"{CRAFT}\n"
        f"{language_instruction(config)} The visual_hint is a search query for "
        "a stock footage site, so keep that one in English.\n"
        + spoken_field_instruction(config)
        + 'Respond with ONLY a JSON object: {"scenes": [{"timestamp_estimate": '
        '"...", "text": "...", "spoken": "...", "visual_hint": "..."}]}'
    )


# --------------------------------------------------------------------------
# Long form: outline, then chapters
# --------------------------------------------------------------------------

def _outline(provider, material: str, reference: str, topic: str,
             target_minutes: int, target_words: int, claims: list) -> list[dict]:
    """The spine of the video, before a word of it is written.

    A list of claims narrated in order is not a documentary, and asking for
    one in a single call is how you get one. Deciding the shape first - what
    the question is, where it turns, what the viewer is still waiting to find
    out - is the difference between a video with a story and a video with
    contents.
    """
    chapters = max(2, round(target_minutes / CHAPTER_MINUTES))

    prompt = (
        material
        + reference
        + f"\nThe subject: {topic!r}\n"
        f"Target length: about {target_minutes} minutes, roughly "
        f"{target_words} spoken words.\n\n"
        f"Plan it as {chapters} chapters before anything is written. For each "
        "one give:\n"
        "- title: what this chapter is about, in a few words\n"
        "- purpose: what it does to the viewer - the question it opens, the "
        "assumption it breaks, the thing it makes them need to know next\n"
        "- beats: 2-4 specific moments that happen in it, in order\n"
        "- claims: which of the verified claims above belong here, quoted\n"
        f"- target_words: how many spoken words it gets, summing to about "
        f"{target_words} across all chapters\n\n"
        "The first chapter opens cold on something concrete and asks the "
        "question the whole video answers. The last one lands the answer and "
        "says why it matters now. The chapters between them escalate - each "
        "one has to raise the stakes on the one before, not sit beside it.\n"
        'Respond with ONLY a JSON object: {"chapters": [{"title": "...", '
        '"purpose": "...", "beats": ["..."], "claims": ["..."], '
        '"target_words": 0}]}'
    )

    parsed = call_llm_json(provider, prompt, OUTLINE_SYSTEM, list_key="chapters")
    planned = [c for c in (parsed.get("chapters") or []) if isinstance(c, dict)]
    if not planned:
        raise ValueError(f"The outline came back with no chapters: {parsed}")

    return _budget(planned, target_words)


def _budget(chapters: list[dict], target_words: int) -> list[dict]:
    """Word budgets that actually sum to the target.

    The outline is asked for these and gets them roughly right, which is not
    the same as right: a plan whose chapters add up to nine hundred words is
    a plan for a six-minute video however long it says it is at the top.
    """
    weights = []
    for chapter in chapters:
        try:
            weights.append(max(1.0, float(chapter.get("target_words") or 0)))
        except (TypeError, ValueError):
            weights.append(1.0)

    scale = target_words / sum(weights)
    for chapter, weight in zip(chapters, weights):
        chapter["target_words"] = max(120, int(round(weight * scale)))
    return chapters


def _chapter_prompt(material: str, reference: str, chapter: dict, index: int,
                    total: int, written_so_far: str, config: dict) -> str:
    beats = chapter.get("beats") or []
    where = (
        "This is the opening. Start cold, in the middle of something concrete "
        "- no throat-clearing, no 'in this video'. Earn the next fifteen "
        "seconds."
        if index == 0
        else "This is the last chapter. Land the answer, and say why it matters "
        "now. Then a short sign-off."
        if index == total - 1
        else "This is a middle chapter. Open by paying off what the last one "
        "left hanging, and end owing the next one something."
    )

    tail = written_so_far.strip().split("\n")[-3:]
    continuity = (
        "\n\nThe last few lines already written, so this picks up rather than "
        f"restates: {' '.join(tail)!r}\n"
        if tail and any(tail) else "\n"
    )

    return (
        material
        + reference
        + f"\n\nYou are writing chapter {index + 1} of {total}, and only that "
        "chapter.\n"
        f"Title: {chapter.get('title', '')!r}\n"
        f"What it has to do to the viewer: {chapter.get('purpose', '')!r}\n"
        f"The moments in it, in order: {beats}\n"
        f"The claims it is built on: {chapter.get('claims') or 'any of the above'}\n"
        f"Length: about {chapter['target_words']} spoken words. This is a "
        "chapter of a longer video, so write it to that length - not shorter."
        + where
        + continuity
        + "Write it as scenes.\n"
        + _scene_contract(config)
    )


def _renumber(scenes: list[dict]) -> list[dict]:
    """Timestamps that run continuously through the whole video.

    Each chapter is written on its own and numbers itself from zero, so the
    assembled script carried six scenes all starting at 0:00. The timeline
    builder reads these to decide how long each scene holds the screen and
    refuses a sequence that does not increase, so it was silently falling
    back to word counts on every long video. Counting words at the narration
    pace gives it something true to read instead.
    """
    at = 0.0
    for scene in scenes:
        words = len((scene.get("text") or "").split())
        span = max(1.5, words / WORDS_PER_MINUTE * 60.0)
        scene["timestamp_estimate"] = f"{_clock(at)}-{_clock(at + span)}"
        at += span
    return scenes


def _clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _write_chapters(provider, input_data: dict, claims: list, config: dict,
                    topic: str, target_minutes: int, target_words: int) -> tuple[list[dict], dict]:
    material = _material(input_data, claims)
    reference = _reference(input_data)

    outline = checkpoints.load("script:outline")
    if outline is None:
        runlog.report("Planning the shape of it before writing any of it", progress=0.2)
        outline = _outline(
            provider, material, reference, topic, target_minutes, target_words, claims
        )
        checkpoints.save("script:outline", outline)

    for index, chapter in enumerate(outline, start=1):
        runlog.report(
            f"{index}. {chapter.get('title', 'untitled')} "
            f"(~{chapter['target_words']} words) - {chapter.get('purpose', '')[:70]}"
        )

    scenes: list[dict] = []
    worst = {"loose": [], "prose": [], "short_by": 0}

    for index, chapter in enumerate(outline):
        key = f"script:chapter:{index}:{chapter.get('title', '')}"
        done = checkpoints.load(key)
        if done is not None:
            runlog.report(f"Chapter {index + 1} already written; reusing it")
            scenes.extend(done)
            continue

        runlog.report(
            f"Writing chapter {index + 1} of {len(outline)}: "
            f"{chapter.get('title', 'untitled')}",
            progress=0.2 + 0.7 * (index / len(outline)),
        )
        written, faults = _write(
            provider,
            _chapter_prompt(
                material, reference, chapter, index, len(outline), _text_of(scenes), config
            ),
            claims,
            chapter["target_words"],
            CHAPTER_DRAFTS,
            f"Chapter {index + 1}",
        )

        checkpoints.save(key, written)
        scenes.extend(written)
        worst["loose"] = sorted(set(worst["loose"]) | set(faults["loose"]))
        worst["prose"] = worst["prose"] or faults["prose"]
        worst["short_by"] += faults["short_by"]

    return _renumber(scenes), worst


# --------------------------------------------------------------------------
# Short form: one call
# --------------------------------------------------------------------------

def _write_whole(provider, input_data: dict, claims: list, config: dict,
                 target_minutes: int, target_words: int) -> tuple[list[dict], dict]:
    prompt = (
        _material(input_data, claims)
        + _reference(input_data)
        + f"\nTarget video length: ~{target_minutes} minutes "
        f"(~{target_words} spoken words total).\n"
        "Write a YouTube video script as a list of scenes: a hook scene, then "
        "enough scenes to actually hit the target length - roughly one scene "
        "per claim, going deeper on each rather than padding - then a "
        "recap/CTA scene.\n"
        + _scene_contract(config)
    )
    return _write(provider, prompt, claims, target_words, DRAFTS, "Draft")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, verified_claims: list[str],
               disputed_claims: list, target_length_minutes: int,
               style_notes: str, structure_notes: str, angle_notes: str}
    Output: {script_text: str, scenes: list[dict]}
    Each scene: {timestamp_estimate, text, visual_hint}
    """
    claims = input_data.get("verified_claims", [])
    target_minutes = int(input_data.get("target_length_minutes") or 5)
    target_words = target_minutes * WORDS_PER_MINUTE
    topic = input_data.get("topic") or input_data.get("user_topic") or ""

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
        f"Writing ~{target_words} words ({target_minutes} min) from "
        f"{len(claims)} verified claim(s)",
        progress=0.15,
    )

    try:
        provider = get_provider("llm", config)

        if target_minutes >= LONG_FORM_MINUTES:
            scenes, faults = _write_chapters(
                provider, input_data, claims, config, topic, target_minutes, target_words
            )
        else:
            scenes, faults = _write_whole(
                provider, input_data, claims, config, target_minutes, target_words
            )

        script_text = _text_of(scenes)
        for scene in scenes[:8]:
            runlog.report(
                f"{scene.get('timestamp_estimate', '?')}  "
                f"{str(scene.get('text', ''))[:90]}"
            )
        runlog.report(
            f"{len(scenes)} scenes, {len(script_text.split())} words "
            f"(~{len(script_text.split()) / WORDS_PER_MINUTE:.1f} min)",
            progress=1.0,
        )

        output = {"script_text": script_text, "scenes": scenes}

        # Every attempt used and still failing a check. The video is worth
        # more than any of these cost, so it ships - and the desk says which,
        # because all three are obvious in the finished file and were
        # invisible in the log.
        if faults["loose"]:
            runlog.report(
                f"Shipping with {len(faults['loose'])} unsupported figure(s); "
                "sources.md will say so"
            )
            output["unsupported_figures"] = faults["loose"]

        if faults["prose"]:
            runlog.report(f"Shipping a draft that still reads as prose: {faults['prose'][0]}")
            output["register_notes"] = faults["prose"]

        written = len(script_text.split())
        if _too_short(script_text, target_words):
            runlog.report(
                f"Shipping short: {written} words against a target of "
                f"{target_words}. The verified material would not carry more."
            )
            output["short_by_words"] = target_words - written

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
