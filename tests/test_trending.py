"""Choosing a topic from what people read, rather than from what a model guesses.

`topic_agent` used to ask an LLM to invent three topics for a niche. That is a
guess dressed as research: the model has no idea what anyone is searching for,
and its three suggestions are the three a language model finds plausible.
Wikipedia publishes readership for nothing, which is the closest public record
of what people are curious about this week.
"""

import requests

from providers.research import trending


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


# ---- what counts as a subject ----------------------------------------------


def test_an_article_about_something_is_a_subject():
    assert trending.is_a_subject("Bharat Gold Mines Limited")
    assert trending.is_a_subject("Proto-industrialization")


def test_scaffolding_is_not():
    """These are read constantly and are not stories."""
    for title in ("Main Page", "Special:Search", "Wikipedia:Featured pictures",
                  "Deaths in 2026", "List of gold mines", "Mercury (disambiguation)"):
        assert not trending.is_a_subject(title), title


def test_nothing_is_not_a_subject():
    assert not trending.is_a_subject("")
    assert not trending.is_a_subject("   ")


# ---- measuring one article -------------------------------------------------


def test_an_article_read_more_than_usual_has_momentum():
    daily = [100] * 23 + [200] * 7

    readership, momentum = trending._measure(daily)

    assert readership == 200
    assert momentum > 1.9


def test_an_article_going_quiet_has_momentum_below_one():
    daily = [200] * 23 + [100] * 7

    _, momentum = trending._measure(daily)
    assert momentum < 0.6


def test_a_tiny_article_doubling_is_not_a_story():
    """One reader becoming two is up a hundred per cent and means nothing."""
    assert trending._measure([1] * 23 + [2] * 7) is None


def test_too_few_days_to_compare_is_no_measurement():
    assert trending._measure([500, 500, 500]) is None
    assert trending._measure([]) is None


# ---- ranking ---------------------------------------------------------------


def _fixed(monkeypatch, articles: dict):
    monkeypatch.setattr(trending, "search", lambda *a, **k: list(articles))
    monkeypatch.setattr(
        trending, "views", lambda title, project="en.wikipedia", session=None: articles[title]
    )


def test_a_rising_subject_outranks_a_flat_one_of_similar_size(monkeypatch):
    _fixed(monkeypatch, {
        "Rising": [100] * 23 + [180] * 7,
        "Flat": [120] * 30,
    })

    ranked = trending.candidates("mining", limit=2)
    assert [item["title"] for item in ranked] == ["Rising", "Flat"]


def test_a_famous_subject_does_not_win_on_size_alone(monkeypatch):
    """Past a point it is simply famous, which is not the same as timely."""
    _fixed(monkeypatch, {
        "Famous": [500_000] * 30,
        "Rising": [200] * 23 + [800] * 7,
    })

    assert trending.candidates("mining", limit=1)[0]["title"] == "Rising"


def test_an_article_with_no_readership_is_dropped(monkeypatch):
    _fixed(monkeypatch, {"Quiet": [2] * 30, "Read": [300] * 30})

    assert [item["title"] for item in trending.candidates("mining", limit=5)] == ["Read"]


def test_what_comes_back_says_why_it_was_picked(monkeypatch):
    _fixed(monkeypatch, {"Rising": [100] * 23 + [200] * 7})

    picked = trending.candidates("mining", limit=1)[0]
    assert picked["daily_views"] == 200
    assert picked["momentum"] > 1.5
    assert picked["score"] > 0


# ---- failing quietly -------------------------------------------------------


def test_search_being_down_narrows_the_choice_rather_than_ending_the_run(monkeypatch):
    def refuse(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(trending.requests.Session, "get", refuse)

    assert trending.search("mining") == []
    assert trending.views("Anything") == []
    assert trending.candidates("mining") == []


def test_an_article_with_no_pageview_data_is_skipped(monkeypatch):
    monkeypatch.setattr(
        trending.requests.Session, "get", lambda self, *a, **k: _Response({}, status_code=404)
    )

    assert trending.views("Never heard of it") == []
