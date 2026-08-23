import runlog
from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are a skeptical, meticulous fact-checker for documentary video production. "
    "You evaluate factual claims against source evidence, scoring confidence "
    "(high, medium, low) and isolating questionable, unverified, or outdated claims."
)


def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, sources: list[dict], ...}
    Output: {verified_claims: list[str], flagged_claims: list[str],
             confidence_scores: dict, claim_citations: list[dict]}
    """
    sources = input_data.get("sources", [])
    all_facts = [fact for source in sources for fact in source.get("key_facts", [])]
    research_summary = input_data.get("research_summary", "")

    # Also pull from metrics and chronology if provided
    for num in input_data.get("numbers_and_data", []):
        all_facts.append(f"{num.get('metric')}: {num.get('value')} ({num.get('context')})")
    for event in input_data.get("chronology", []):
        all_facts.append(f"{event.get('date')} - {event.get('event')}")

    runlog.report(
        f"{len(all_facts)} claim(s) to check across {len(sources)} source(s)", progress=0.15
    )
    if not all_facts:
        runlog.report("Nothing to verify", progress=1.0)
        return {
            "success": True,
            "output": {"verified_claims": [], "flagged_claims": [], "confidence_scores": {}},
            "error": None,
        }

    prompt = (
        f"Research summary: {research_summary!r}\n"
        f"Sources: {[s.get('title', '') for s in sources]}\n"
        f"Claims to verify: {all_facts}\n"
        "Evaluate each claim:\n"
        "1. verified_claims: list of confirmed factual statements safe to state as fact.\n"
        "2. flagged_claims: list of unverified, disputed, or sensationalized statements that must be qualified or omitted.\n"
        "3. confidence: mapping from claim summary to 'high' | 'medium' | 'low'.\n"
        'Respond with ONLY a JSON object: {"verified_claims": ["...", ...], "flagged_claims": ["...", ...], "confidence": {"...": "high"}}'
    )

    try:
        provider = get_provider("llm", config)
        parsed = call_llm_json(provider, prompt, SYSTEM)
        verified = parsed.get("verified_claims")
        flagged = parsed.get("flagged_claims")
        if not isinstance(verified, list) or not isinstance(flagged, list):
            raise ValueError(f"Expected list fields in LLM response: {parsed}")

        for claim in flagged:
            runlog.report(f"DISPUTED: {str(claim)[:110]}")
        runlog.report(
            f"{len(verified)} verified, {len(flagged)} flagged as unsafe to state",
            progress=1.0,
        )
        output = {
            "verified_claims": verified,
            "flagged_claims": flagged,
            "confidence_scores": parsed.get("confidence") or {c: "high" for c in verified},
        }
        return {"success": True, "output": output, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
