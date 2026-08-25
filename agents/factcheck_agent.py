import crosscheck
import runlog
import sources as sourcing
from agents._llm_utils import call_llm_json
from providers.registry import get_provider

SYSTEM = (
    "You are a skeptical, meticulous fact-checker for documentary video production. "
    "You evaluate factual claims against source evidence, scoring confidence "
    "(high, medium, low) and isolating questionable, unverified, or outdated claims."
)


def _record_sources(input_data: dict, output: dict) -> str:
    """The sourcing record, or "" if it could not be written.

    A video whose sources failed to save is still a video; halting a finished
    run over a file write would be the wrong trade.
    """
    try:
        path = sourcing.write_document(
            input_data.get("topic", ""),
            {"sources": input_data.get("sources", [])},
            output,
        )
        runlog.report(f"Sources written to {path.rsplit('/', 1)[-1]}")
        return path
    except Exception as e:
        runlog.report(f"Could not write the sources document: {e}")
        return ""


def run(input_data: dict, config: dict) -> dict:
    """Input: {research_summary: str, sources: list[dict], ...}
    Output: {verified_claims: list[str], flagged_claims: list[str],
             confidence_scores: dict, claim_citations: list[dict]}
    """
    sources = input_data.get("sources", [])
    research_summary = input_data.get("research_summary", "")
    figures = input_data.get("numbers_and_data", [])

    # Claims keep the source that made them. Flattening them into one list
    # threw away the only thing a cross-check needs - who said what - so two
    # sources giving different figures for the same quantity arrived as two
    # claims in a heap, and the model was free to verify both.
    attributed = crosscheck.attributed_claims(sources)
    all_facts = [f"{claim['claim']} [{claim['source']}]" for claim in attributed]

    for num in figures:
        all_facts.append(f"{num.get('metric')}: {num.get('value')} ({num.get('context')})")
    for event in input_data.get("chronology", []):
        all_facts.append(f"{event.get('date')} - {event.get('event')}")

    # The disagreements that can be found without judgement: the same quantity
    # reported as two different numbers.
    conflicts = crosscheck.conflicting_figures(figures)
    for conflict in conflicts:
        runlog.report(
            f"SOURCES DIFFER on {conflict['subject']}: "
            f"{' vs '.join(conflict['values'])}"
        )

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
        f"Claims to verify, each followed by the source that made it: {all_facts}\n"
        f"{crosscheck.describe(conflicts)}"
        "Evaluate each claim:\n"
        "1. verified_claims: list of confirmed factual statements safe to state as fact.\n"
        "2. flagged_claims: list of unverified or sensationalized statements that must be qualified or omitted.\n"
        "3. disputed_claims: statements the sources do not agree on. A claim one source makes and "
        "another contradicts belongs here, not in verified_claims and not in flagged_claims - "
        "the disagreement is worth saying out loud rather than resolving silently. Each entry: "
        '{"claim": "...", "positions": ["source A says ...", "source B says ..."]}.\n'
        "4. confidence: mapping from claim summary to 'high' | 'medium' | 'low'.\n"
        'Respond with ONLY a JSON object: {"verified_claims": ["...", ...], "flagged_claims": ["...", ...], '
        '"disputed_claims": [{"claim": "...", "positions": ["..."]}], "confidence": {"...": "high"}}'
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
            f"{len(verified)} verified, {len(flagged)} flagged as unsafe to state, "
            f"{len(parsed.get('disputed_claims') or []) + len(conflicts)} disputed",
            progress=1.0,
        )
        disputed = parsed.get("disputed_claims")
        if not isinstance(disputed, list):
            disputed = []

        # The figures that disagree are added whether the model noticed them or
        # not: they were found by comparing numbers, which needs no judgement,
        # and a run should not depend on the model having spotted them.
        for conflict in conflicts:
            disputed.append({
                "claim": f"{conflict['subject']}: sources report {' and '.join(conflict['values'])}",
                "positions": [
                    f"{source} says {value}"
                    for source, value in zip(conflict["sources"], conflict["values"])
                ],
            })

        for entry in disputed:
            runlog.report(f"SOURCES DIFFER: {str(entry.get('claim', entry))[:110]}")

        output = {
            "verified_claims": verified,
            "flagged_claims": flagged,
            "disputed_claims": disputed,
            "confidence_scores": parsed.get("confidence") or {c: "high" for c in verified},
        }

        # Written here rather than at publish time because a run that never
        # publishes still owes its sources, and this is the first moment both
        # the sources and the verdicts on them exist.
        output["sources_document"] = _record_sources(input_data, output)
        return {"success": True, "output": output, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
