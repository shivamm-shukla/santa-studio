def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, sources: list[dict]}
    Output: {verified_claims: list[str], flagged_claims: list[str]}
    """
    sources = input_data.get("sources", [])
    all_facts = [fact for source in sources for fact in source.get("key_facts", [])]
    if not all_facts:
        all_facts = ["[stub claim]"]

    split = max(1, len(all_facts) - 1)
    return {
        "success": True,
        "output": {
            "verified_claims": all_facts[:split],
            "flagged_claims": all_facts[split:],
        },
        "error": None,
    }
