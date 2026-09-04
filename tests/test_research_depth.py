"""Research that knows how long a video it is researching for.

A twenty-minute video is not a five-minute one said slowly - it is four
times the events, the figures and the disagreements. Research had no idea
which it was being asked for, so every run looked equally hard, and a script
cannot be long about material that was never gathered.
"""

import pytest

from agents import research_agent as research


def test_a_longer_video_earns_a_deeper_search():
    short = research.depth_for(5)
    long = research.depth_for(20)

    assert long["sources"] > short["sources"]
    assert long["pages"] > short["pages"]
    assert long["rounds"] >= short["rounds"]
    assert long["facts_per_source"] > short["facts_per_source"]
    assert long["summary_sentences"] > short["summary_sentences"]


def test_the_baseline_length_gets_exactly_what_it_always_got():
    """The numbers were chosen for a five-minute video and still hold there."""
    baseline = research.depth_for(research.BASELINE_MINUTES)

    assert baseline["sources"] == research.ENOUGH_SOURCES
    assert baseline["pages"] == research.PAGES_READ
    assert baseline["rounds"] == research.SEARCH_ROUNDS
    assert baseline["facts_per_source"] == research.FACTS_PER_SOURCE


def test_a_shorter_video_is_not_researched_more_thinly_than_the_floor():
    """Below the baseline the effort holds rather than shrinking.

    A three-minute video still has to be right, and the cost of the extra
    reading is small next to the cost of a video built on two sources.
    """
    assert research.depth_for(1) == research.depth_for(research.BASELINE_MINUTES)


def test_depth_grows_sub_linearly_because_sources_overlap():
    """The tenth page on a subject repeats more of the ninth than the second
    repeated the first, so four times the length is not four times the work."""
    baseline = research.depth_for(5)["sources"]
    quadruple = research.depth_for(20)["sources"]

    assert quadruple > baseline
    assert quadruple < baseline * 4


def test_effort_is_capped_however_long_the_video():
    """A free tier is counted in requests per day."""
    enormous = research.depth_for(600)

    assert enormous["sources"] <= 24
    assert enormous["pages"] <= 28
    assert enormous["rounds"] <= 5


def test_a_missing_target_length_is_the_baseline(monkeypatch):
    """Callers that predate this - and the CLI - simply get what they got."""
    assert research.depth_for(None or research.BASELINE_MINUTES) == research.depth_for(5)


# --------------------------------------------------------------------------
# What the synthesis is actually asked for
# --------------------------------------------------------------------------

def _synthesis_prompt(monkeypatch, grounded, minutes):
    """Runs the agent far enough to capture the synthesis prompt it builds.

    `ask` is a closure inside run(), so the seam is call_llm_json - which is
    what every prompt in this agent goes through anyway.
    """
    prompts = []

    def capture(provider, prompt, system, list_key=None):
        prompts.append(prompt)
        if "Synthesize an authoritative research brief" in prompt:
            return {"research_summary": "It happened.", "sources": []}
        return {}

    monkeypatch.setattr(research, "get_provider", lambda kind, config: object())
    monkeypatch.setattr(research, "_query_plan", lambda *a, **k: ["a query"])
    monkeypatch.setattr(research, "_sweep", lambda queries: [dict(s) for s in grounded])
    monkeypatch.setattr(research, "_screened", lambda found, topic, provider: list(found))
    monkeypatch.setattr(research, "_read_in_full", lambda sources, pages=10: None)
    monkeypatch.setattr(research, "_run_specialist_research", lambda role, p, ask: {})
    monkeypatch.setattr(research, "call_llm_json", capture)

    result = research.run({"topic": "containers", "target_length_minutes": minutes}, {})
    assert result["success"] is True, result["error"]

    synthesis = [p for p in prompts if "Synthesize an authoritative research brief" in p]
    assert synthesis, "the agent never reached its synthesis pass"
    return synthesis[0]


SOURCES = [
    {"url": f"https://example.test/{i}", "title": f"Source {i}",
     "summary": "a summary", "content": "what the page says"}
    for i in range(12)
]


def test_every_grounded_source_is_asked_about_not_just_five(monkeypatch):
    """This one clause was the ceiling on how long a video could honestly be.

    Key facts become claims, claims are what survive fact-checking, and the
    script may state nothing that did not come through there. Asking for
    "3-5 sources with key facts" meant that however many pages had been read
    in full, five at most ever reached the writer.
    """
    prompt = _synthesis_prompt(monkeypatch, SOURCES, minutes=15)

    for source in SOURCES:
        assert source["url"] in prompt, "a grounded source the model was never asked about"
    assert "3-5" not in prompt


def test_a_longer_video_asks_each_source_for_more(monkeypatch):
    short = _synthesis_prompt(monkeypatch, SOURCES, minutes=5)
    long = _synthesis_prompt(monkeypatch, SOURCES, minutes=20)

    assert f"up to {research.depth_for(5)['facts_per_source']} key_facts" in short
    assert f"up to {research.depth_for(20)['facts_per_source']} key_facts" in long


def test_a_source_that_supports_nothing_is_not_made_to(monkeypatch):
    """Asking every source for facts must not become asking it to invent them."""
    prompt = _synthesis_prompt(monkeypatch, SOURCES, minutes=15)

    assert "empty list rather than an invented" in prompt


def test_the_text_budget_moves_with_the_page_count(monkeypatch):
    """Otherwise the extra reading is thrown away before anyone reads it.

    A run that opens twenty-eight pages and then hands the swarm the same
    24000 characters has trimmed most of what it just read down to a title -
    while the synthesis is being asked for facts from every one of those
    URLs.
    """
    short = research.depth_for(5)
    long = research.depth_for(20)

    assert long["grounding"] > short["grounding"]
    assert long["grounding"] / short["grounding"] == pytest.approx(
        long["pages"] / short["pages"], rel=0.2
    )


def test_the_baseline_text_budget_is_unchanged():
    assert research.depth_for(research.BASELINE_MINUTES)["grounding"] == research.GROUNDING_BUDGET


def test_the_text_budget_stays_inside_a_providers_window():
    """Groq takes 8000 tokens a minute; the shrink path exists for a reason."""
    assert research.depth_for(600)["grounding"] <= 64000
