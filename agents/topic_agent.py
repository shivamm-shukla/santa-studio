import runlog
from agents._llm_utils import call_llm_json, language_instruction
from providers.registry import get_provider
from providers.research import trending

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
    runlog.report(f"No topic given - finding what people read about {niche!r}", progress=0.1)

    # Grounded in readership rather than invented. Asked to suggest topics on
    # its own the model returns the three a language model finds plausible,
    # which is a different thing from the three a viewer wants - and it has no
    # way of knowing what anyone is currently curious about.
    trending_articles = trending.candidates(niche, limit=6)
    for article in trending_articles:
        runlog.report(
            f"Being read: {article['title']} - {article['daily_views']:,}/day, "
            f"{article['momentum']}x its usual"
        )
    runlog.report(f"{len(trending_articles)} subject(s) with real readership", progress=0.35)

    evidence = ""
    if trending_articles:
        evidence = (
            "\nWhat people are actually reading about this niche on Wikipedia "
            "right now, with daily readers and how that compares with the "
            "month before:\n"
            + "\n".join(
                f"- {a['title']}: {a['daily_views']:,} readers a day, {a['momentum']}x its usual"
                for a in trending_articles
            )
            + "\nBuild the topics out of these subjects. A subject being read "
            "more than usual is the strongest signal here. Do not propose a "
            "topic that has nothing to do with any of them.\n"
        )

    prompt = (
        f"Suggest exactly 3 YouTube long-form video topics for the niche: {niche!r}.\n"
        f"{evidence}"
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
