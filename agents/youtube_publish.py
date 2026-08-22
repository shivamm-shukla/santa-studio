"""Publishes the finished video to YouTube.

Metadata (title, description, tags) is drafted by draft_metadata() before
the AWAITING_PUBLISH gate rather than inside run(), so the human edits the
real thing at the gate instead of reviewing it after upload. run() then
uploads exactly what the gate left behind.
"""

from agents._llm_utils import call_llm_json, language_instruction
from providers.registry import get_provider

SYSTEM = (
    "You write YouTube metadata that earns clicks without misleading. "
    "Titles are specific and curiosity-driving, descriptions open with a "
    "one-line hook, and tags are the terms a viewer would actually search."
)

MAX_TITLE = 100  # YouTube's hard limit


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
        f"Write YouTube metadata for this video. The title must be under "
        f"{MAX_TITLE} characters. The description should be 3-5 sentences. "
        "Give 8-12 tags.\n"
        f"{language_instruction(config)} Tags should mix the video's own "
        "language and English, since viewers search in both.\n"
        'Respond with ONLY a JSON object: {"title": "...", "description": "...", '
        '"tags": ["...", "..."]}'
    )

    try:
        parsed = call_llm_json(get_provider("llm", config), prompt, SYSTEM)
        return {
            "title": str(parsed.get("title") or topic)[:MAX_TITLE],
            "description": str(parsed.get("description") or ""),
            "tags": [str(t) for t in parsed.get("tags", []) if str(t).strip()],
        }
    except Exception:
        return {"title": topic[:MAX_TITLE], "description": "", "tags": []}


def run(input_data: dict, config: dict) -> dict:
    """Input: {video_path, title, description, tags, thumbnail_path, ...}
    Output: {video_url: str, video_id: str}
    """
    try:
        provider = get_provider("publish", config)
        result = provider.upload(
            video_path=input_data["video_path"],
            title=input_data.get("title") or "Untitled",
            description=input_data.get("description") or "",
            tags=input_data.get("tags") or [],
            thumbnail_path=input_data.get("thumbnail_path") or "",
        )
        return {"success": True, "output": result, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
