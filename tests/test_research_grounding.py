"""What the research brief is actually grounded on.

The research agent searches Wikipedia and hands the extracts to the LLM as
"verified real-world source grounding". A topic is a video title or a human's
question, and handing one of those to a search index verbatim returned pages
about nothing to do with it - which the brief was then written from. These
cover the part that decides what gets fed in.
"""

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
