"""Publishes the finished video to YouTube.

Metadata (title, description, tags) is drafted by draft_metadata() before
the AWAITING_PUBLISH gate rather than inside run(), so the human edits the
real thing at the gate instead of reviewing it after upload. run() then
uploads exactly what the gate left behind.
"""

import json
import os

import sources as sourcing
from agents._llm_utils import call_llm_json, language_instruction
from providers.registry import get_provider

SYSTEM = (
    "You write YouTube metadata that earns clicks without misleading. "
    "Titles are specific and curiosity-driving, descriptions open with a "
    "one-line hook, and tags are the terms a viewer would actually search."
)

MAX_TITLE = 100  # YouTube's hard limit


def _chapters(state) -> list[dict]:
    """The video's sections and where they start, if it has any.

    Measured against the finished audio by the timeline builder rather than
    estimated from the script, which is why they are read back off the
    timeline instead of recomputed here.
    """
    path = (state.video_output or {}).get("timeline_path") or ""
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path) as handle:
            marks = (json.load(handle).get("meta") or {}).get("chapters") or []
    except (OSError, ValueError):
        return []
    return [m for m in marks if isinstance(m, dict) and m.get("title")]


def _stamp(seconds: float) -> str:
    """A timestamp YouTube will parse, hours included.

    Past an hour "62:30" is not a longer video's minute count, it is a
    malformed timestamp - and one bad line makes YouTube drop the whole
    chapter block rather than the line.
    """
    whole = int(seconds)
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _chapter_list(state) -> str:
    """The sections as YouTube renders them into a chapter strip.

    YouTube needs a timestamp per line, the first one at 0:00, and at least
    three of them - so a video that has fewer sections than that simply gets
    none, rather than a list that shows up as plain text nobody can click.
    """
    marks = _chapters(state)
    if len(marks) < 3:
        return ""

    try:
        times = [float(mark["at"]) for mark in marks]
    except (KeyError, TypeError, ValueError):
        return ""

    # YouTube wants the first entry at 0:00. Relabelling the first section as
    # 0:00 when it really starts later would put the wrong name on the video's
    # opening, so the opening gets an entry of its own instead.
    titles = [str(mark["title"]).strip() for mark in marks]
    if times[0] > 1.0:
        times.insert(0, 0.0)
        titles.insert(0, "Intro")

    # Strictly increasing, or YouTube ignores the whole block rather than the
    # line - so a set of marks that is not gets dropped here instead.
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        return ""

    return "\n".join(f"{_stamp(at)} {title}" for at, title in zip(times, titles))


def draft_metadata(state, config: dict) -> dict:
    """Drafts {title, description, tags} from the script and research.

    Never raises: a failed draft still lets the human write their own at
    the gate, which is a far better outcome than halting a finished video
    before it can be published.
    """
    topic = state.topic or "Untitled"
    summary = (state.research or {}).get("research_summary", "")
    script_text = (state.script or {}).get("script_text", "")[:3000]

    prompt = (
        f"Video topic: {topic!r}\n"
        f"Research summary: {summary!r}\n"
        f"Script: {script_text!r}\n"
        "Write YouTube metadata for this video.\n"
        f"title: under {MAX_TITLE} characters, and it has to earn the click "
        "honestly. Name the specific thing - the place, the number, the year - "
        "and leave one question open that only the video answers. No "
        "all-caps, no 'you won't believe', and nothing the video does not "
        "actually deliver: a title that oversells is the fastest way to lose "
        "the audience it wins.\n"
        "description: 3-5 sentences. The first one has to stand on its own, "
        "because it is all that shows above the fold.\n"
        "tags: 8-12.\n"
        f"{language_instruction(config)} Tags should mix the video's own "
        "language and English, since viewers search in both.\n"
        'Respond with ONLY a JSON object: {"title": "...", "description": "...", '
        '"tags": ["...", "..."]}'
    )

    # The sources ship whether or not the draft succeeds. On a research
    # channel a description without them is a broken promise, and it is the
    # half of the description we can write without an LLM.
    try:
        parsed = call_llm_json(get_provider("llm", config), prompt, SYSTEM)
        drafted = str(parsed.get("description") or "")
        return {
            "title": str(parsed.get("title") or topic)[:MAX_TITLE],
            "description": _describe(drafted, state),
            "tags": [str(t) for t in parsed.get("tags", []) if str(t).strip()],
        }
    except Exception:
        return {
            "title": topic[:MAX_TITLE],
            "description": _describe("", state),
            "tags": [],
        }


def _describe(drafted: str, state) -> str:
    """The description as it ships: the draft, the chapters, the sources."""
    chapters = _chapter_list(state)
    body = f"{drafted}\n\n{chapters}".strip() if chapters else drafted
    return sourcing.with_sources(body, state.research)


def run(input_data: dict, config: dict) -> dict:
    """Input: {video_path, title, description, tags, thumbnail_path, ...}
    Output: {video_url: str, video_id: str, thumbnail_status: str, published: bool, platform: str}
    """
    from agents import publish_agent
    return publish_agent.run(input_data, config)
