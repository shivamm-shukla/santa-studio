from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are a skeptical, meticulous fact-checker. You separate claims you "
    "are confident are accurate from claims that are uncertain, outdated, or "
    "need a citation before they should appear in a published video."
)


def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, sources: list[dict]}
    Output: {verified_claims: list[str], flagged_claims: list[str]}
    """
    sources = input_data.get("sources", [])
    all_facts = [fact for source in sources for fact in source.get("key_facts", [])]
    research_summary = input_data.get("research_summary", "")

    if not all_facts:
        return {"success": True, "output": {"verified_claims": [], "flagged_claims": []}, "error": None}

    prompt = (
        f"Research summary: {research_summary!r}\n"
        f"Claims to fact-check: {all_facts}\n"
        "Sort each claim into verified_claims (you're confident it's accurate) "
        "or flagged_claims (uncertain, needs a citation, or possibly outdated).\n"
        'Respond with ONLY a JSON object: {"verified_claims": ["...", ...], "flagged_claims": ["...", ...]}'
    )

    try:
        provider = get_provider("llm", config)
        parsed = call_llm_json(provider, prompt, SYSTEM)
        if not isinstance(parsed.get("verified_claims"), list) or not isinstance(parsed.get("flagged_claims"), list):
            raise ValueError(f"Expected list fields in LLM response: {parsed}")
        return {"success": True, "output": parsed, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
