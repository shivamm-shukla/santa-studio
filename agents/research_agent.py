from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are a veteran researcher who prepares accurate, well-sourced "
    "briefings for YouTube scriptwriters. You are careful to flag anything "
    "you are not confident about rather than stating it as fact."
)


def run(input_data: dict, config: dict) -> dict:
    """Input: {topic: str, reference_notes: dict}
    Output: {research_summary: str, sources: list[dict]}
    Each source: {title, url, key_facts: list[str]}
    """
    # TODO: wire the web_search server tool so this is grounded in real,
    # current sources instead of the model's own training knowledge.
    topic = input_data.get("topic", "the topic")
    prompt = (
        f"Research the topic: {topic!r} for a YouTube video.\n"
        "Produce a research_summary (2-4 sentences) and a list of 2-4 sources, "
        "each with a title, a plausible url, and 1-3 key_facts. If you are not "
        "confident in a specific fact, phrase it cautiously rather than as certain.\n"
        'Respond with ONLY a JSON object: {"research_summary": "...", '
        '"sources": [{"title": "...", "url": "...", "key_facts": ["...", "..."]}]}'
    )

    try:
        provider = get_provider("llm", config)
        parsed = call_llm_json(provider, prompt, SYSTEM)
        if not parsed.get("research_summary") or not parsed.get("sources"):
            raise ValueError(f"Missing 'research_summary' or 'sources' in LLM response: {parsed}")
        return {"success": True, "output": parsed, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
