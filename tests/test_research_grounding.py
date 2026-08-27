"""What the research brief is actually grounded on.

The research agent searches Wikipedia and hands the extracts to the LLM as
"verified real-world source grounding". A topic is a video title or a human's
question, and handing one of those to a search index verbatim returned pages
about nothing to do with it - which the brief was then written from. These
cover the part that decides what gets fed in.
"""

from agents import research_agent
from agents.research_agent import _relevant_to, _search_queries


def _sources(*titles):
    return [{"title": t, "url": "", "summary": ""} for t in titles]


# ---- building the query ----------------------------------------------------


def test_the_subject_is_tried_before_the_whole_question():
    """"Why the Kolar Gold Fields shut down" returned Novak Djokovic.

    The question words matched far more pages than the subject did, so the
    run of capitalised words - which is what an encyclopedia indexes under -
    is tried first.
    """
    queries = _search_queries("Why the Kolar Gold Fields shut down")
    assert queries[0] == "Kolar Gold Fields"
    # The original is still tried, last, rather than thrown away.
    assert queries[-1] == "Why the Kolar Gold Fields shut down"


def test_a_leading_capital_is_not_mistaken_for_a_subject():
    """"Why" is capitalised only because it starts the sentence."""
    assert "Why" not in _search_queries("Why the Bhopal disaster happened")[0]


def test_a_lowercase_topic_falls_back_to_stripping_question_words():
    queries = _search_queries("why indian railways run late")
    assert queries[0] == "indian railways run late"


def test_a_topic_with_nothing_to_strip_is_searched_as_written():
    assert _search_queries("Bhopal disaster") == ["Bhopal disaster"]


def test_queries_are_not_repeated():
    assert len(_search_queries("Kolar Gold Fields")) == len(set(_search_queries("Kolar Gold Fields")))


# ---- filtering the results -------------------------------------------------


def test_results_about_something_else_are_dropped():
    """Wikipedia's search never fails - it guesses, and the guess looks the same.

    One good page and four unrelated ones is the common shape, so the set is
    filtered rather than accepted or rejected whole.
    """
    kept = _relevant_to(
        _sources("History of rockets", "Yao Ming", "Kenny Beats"),
        "The Rockets That Beat an Empire",
    )
    assert [s["title"] for s in kept] == ["History of rockets"]


def test_everything_relevant_is_kept():
    kept = _relevant_to(
        _sources("Kolar Gold Fields", "Kolar district", "Novak Djokovic"),
        "Why the Kolar Gold Fields shut down",
    )
    assert [s["title"] for s in kept] == ["Kolar Gold Fields", "Kolar district"]


def test_nothing_relevant_means_no_grounding_at_all():
    """A brief written with no sources beats one written from the wrong ones."""
    assert _relevant_to(_sources("Novak Djokovic", "Austin, Texas"), "Kolar Gold Fields") == []


def test_a_shared_stopword_is_not_a_match():
    assert _relevant_to(_sources("The History of the World"), "The Kolar Gold Fields") == []


# ---- screening the indexes the word filter never covered -------------------


class _Provider:
    """Stands in for an LLM provider the screen never actually calls."""


def test_a_paper_that_only_shares_a_word_is_not_a_source(monkeypatch):
    """OpenAlex answered "how a metal box rewired world trade" with four papers
    on photosynthesis, plant stress and a tomato fungus - every one of them
    carrying the word "rewiring" - and all four shipped in sources.md as "the
    sources this video is built on". Word overlap cannot tell them apart.
    """
    monkeypatch.setattr(research_agent, "call_llm_json", lambda *a, **k: {"keep": [1]})

    kept = research_agent._screened(
        _sources("Containerization", "Rewiring photosynthetic electron transport chains"),
        "how a metal box rewired world trade",
        _Provider(),
    )

    assert [s["title"] for s in kept] == ["Containerization"]


def test_the_screen_failing_falls_back_to_the_word_filter_not_to_accepting_everything(monkeypatch):
    """Failing open is the behaviour that wrote the wrong document."""
    def refuse(*args, **kwargs):
        raise RuntimeError("no allowance left today")

    monkeypatch.setattr(research_agent, "call_llm_json", refuse)

    kept = research_agent._screened(
        _sources("Kolar Gold Fields", "Novak Djokovic"),
        "Why the Kolar Gold Fields shut down",
        _Provider(),
    )
    assert [s["title"] for s in kept] == ["Kolar Gold Fields"]


def test_keeping_nothing_is_an_answer_the_screen_is_allowed_to_give(monkeypatch):
    monkeypatch.setattr(research_agent, "call_llm_json", lambda *a, **k: {"keep": []})

    assert research_agent._screened(_sources("Something else"), "A topic", _Provider()) == []


def test_no_brief_is_written_when_nothing_fetched_is_about_the_topic(monkeypatch):
    """A brief with nothing behind it gets written from the model's memory and
    then cited to sources that do not support it, which is the failure this
    whole stage exists to prevent.
    """
    monkeypatch.setattr(research_agent, "_search_wikipedia", lambda query: [])
    monkeypatch.setattr(research_agent.websearch, "search", lambda query, **k: [])
    monkeypatch.setattr(
        research_agent.grounding, "academic",
        lambda query, **k: [{"title": "Rewiring photosynthesis", "url": "https://doi.org/1", "summary": ""}],
    )
    monkeypatch.setattr(research_agent.grounding, "news", lambda query, **k: [])
    monkeypatch.setattr(research_agent, "get_provider", lambda kind, config: _Provider())
    monkeypatch.setattr(
        research_agent, "call_llm_json",
        lambda *a, **k: {"queries": ["metal box trade"], "keep": []},
    )

    result = research_agent.run({"topic": "how a metal box rewired world trade"}, {})

    assert result["success"] is False
    assert "metal box" in result["error"]


# ---- the window the provider that answered happens to have ------------------


def test_a_prompt_too_large_for_the_provider_is_asked_again_with_less():
    """Which provider answers is decided by whose free allowance is left, and
    their windows are nothing alike - Groq takes 8000 tokens a minute, Gemini
    a million. A brief that took three rounds of searching to assemble should
    not be lost because a smaller one picked up.
    """
    assert research_agent._too_large("Error code: 413 - Request too large for model")
    assert research_agent._too_large("rate_limit_exceeded on tokens per minute (TPM)")
    assert research_agent._too_large("maximum context length exceeded")


def test_an_ordinary_failure_is_not_mistaken_for_a_window_problem():
    """Retrying a smaller prompt against an invalid key just fails slower."""
    assert not research_agent._too_large("401 invalid api key")
    assert not research_agent._too_large("connection reset by peer")
    assert not research_agent._too_large(None)


def test_the_sources_are_cut_to_the_budget_they_are_given():
    sources = [
        {"title": f"Source {i}", "url": f"https://example.org/{i}", "content": "x" * 5000}
        for i in range(10)
    ]

    assert len(research_agent._grounding_text(sources, budget=4000)) < 4500
    assert len(research_agent._grounding_text(sources, budget=20000)) > 15000


def test_every_query_gets_a_look_in_when_the_sweep_is_capped(monkeypatch):
    """Screening judges a bounded number of candidates per round. Concatenated,
    that bound is spent on whatever the first query returned - so a query that
    found the good source fourth never gets looked at."""
    def per_query(query, **kwargs):
        return [{"title": f"{query}-{i}", "url": f"https://example.org/{query}/{i}",
                 "summary": ""} for i in range(5)]

    monkeypatch.setattr(research_agent, "_search_wikipedia", lambda query: [])
    monkeypatch.setattr(research_agent.websearch, "search", per_query)
    monkeypatch.setattr(research_agent.grounding, "academic", lambda query, **k: [])
    monkeypatch.setattr(research_agent.grounding, "news", lambda query, **k: [])

    swept = research_agent._sweep(["alpha", "beta"])

    # Both queries are represented before either is exhausted.
    assert {s["title"] for s in swept[:2]} == {"alpha-0", "beta-0"}
