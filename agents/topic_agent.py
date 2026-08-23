import runlog
from agents._llm_utils import call_llm_json, language_instruction
from providers.registry import get_provider

SYSTEM = (
    "You are an expert YouTube content strategist with a track record of "
    "picking topics that perform well for long-form videos. You think in "
    "terms of hooks, audience curiosity gaps, and search intent."
)


def run(input_data: dict, config: dict) -> dict:
    """Input: {niche: str, preferences: dict, user_topic: str | None}
    Output: {topics: list[str]}
    """
    user_topic = input_data.get("user_topic")
    if user_topic:
        runlog.report(f"Topic was given by the human: {user_topic!r}", progress=1.0)
        return {"success": True, "output": {"topics": [user_topic]}, "error": None}

    niche = input_data.get("niche", "general")
    runlog.report(f"No topic given - proposing three for {niche!r}", progress=0.2)
    prompt = (
        f"Suggest exactly 3 YouTube long-form video topics for the niche: {niche!r}.\n"
        "Each topic should be a specific, curiosity-driving title (not generic).\n"
        f"{language_instruction(config)}\n"
        'Respond with ONLY a JSON object: {"topics": ["...", "...", "..."]}'
    )

    try:
        provider = get_provider("llm", config)
        parsed = call_llm_json(provider, prompt, SYSTEM)
        topics = parsed.get("topics")
        if not isinstance(topics, list) or not topics:
            raise ValueError(f"Expected non-empty 'topics' list, got: {parsed}")
        for candidate in topics:
            runlog.report(f"Candidate: {candidate}")
        runlog.report(f"Going with {topics[0]!r}", progress=1.0)
        return {"success": True, "output": {"topics": topics}, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
