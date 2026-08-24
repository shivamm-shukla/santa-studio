"""The sources that ship are the ones we fetched, not the ones a model wrote.

Two things are covered here. First, the indexes that were added past
Wikipedia - OpenAlex for the academic record, GDELT for contemporary
coverage - both of which must degrade to an empty list rather than take a run
down. Second, and more important: the published description carries these
URLs as citations a viewer is invited to click, so a URL the model invented is
worse than no citation at all. `_cite` is what enforces that.
"""

import requests

from agents.research_agent import _cite
from providers.research import grounding


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._payload


# ---- the academic record ---------------------------------------------------


def test_a_work_is_cited_by_its_doi_rather_than_by_openalex(monkeypatch):
    """The DOI resolves anywhere and does not depend on us staying up."""
    monkeypatch.setattr(grounding.requests, "get", lambda *a, **k: _Response({
        "results": [{
            "display_name": "Cyanide in mine tailings",
            "doi": "https://doi.org/10.1007/s10706-005-3372-3",
            "id": "https://openalex.org/W123",
            "publication_year": 2006,
            "cited_by_count": 41,
            "primary_location": {"source": {"display_name": "Geotechnical Journal"}},
        }]
    }))

    source = grounding.academic("kolar gold fields")[0]

    assert source["url"] == "https://doi.org/10.1007/s10706-005-3372-3"
    assert source["kind"] == "academic"
    assert "Geotechnical Journal" in source["summary"]
    assert "2006" in source["summary"]


def test_a_work_with_no_doi_falls_back_to_its_openalex_page(monkeypatch):
    monkeypatch.setattr(grounding.requests, "get", lambda *a, **k: _Response({
        "results": [{"display_name": "An unregistered preprint", "id": "https://openalex.org/W9"}]
    }))

    assert grounding.academic("anything")[0]["url"] == "https://openalex.org/W9"


def test_a_work_with_no_usable_url_is_not_offered_as_a_citation(monkeypatch):
    monkeypatch.setattr(grounding.requests, "get", lambda *a, **k: _Response({
        "results": [{"display_name": "Untitled record", "id": "W7"}]
    }))

    assert grounding.academic("anything") == []


def test_the_academic_index_being_down_narrows_the_brief_instead_of_ending_it(monkeypatch):
    def refuse(*args, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(grounding.requests, "get", refuse)

    assert grounding.academic("anything") == []


# ---- contemporary coverage -------------------------------------------------


def test_news_carries_the_domain_and_the_date_it_was_seen(monkeypatch):
    monkeypatch.setattr(grounding.requests, "get", lambda *a, **k: _Response({
        "articles": [{
            "title": "Mine closure leaves township without water",
            "url": "https://thehindu.com/mine-closure",
            "domain": "thehindu.com",
            "seendate": "20060714T120000Z",
        }]
    }))

    source = grounding.news("kolar")[0]

    assert source["kind"] == "news"
    assert source["summary"] == "thehindu.com, 20060714"


def test_being_rate_limited_is_read_as_no_news_not_as_json(monkeypatch):
    """GDELT answers a throttled caller with plain text under a 429."""
    def throttled(*args, **kwargs):
        return _Response({}, status_code=429)

    monkeypatch.setattr(grounding.requests, "get", throttled)

    assert grounding.news("anything") == []


# ---- merging ---------------------------------------------------------------


def test_one_entry_per_url_in_the_order_the_indexes_were_asked():
    merged = grounding.merge(
        [{"url": "https://a", "title": "wiki"}],
        [{"url": "https://b", "title": "doi"}, {"url": "https://a", "title": "wiki again"}],
    )

    assert [s["url"] for s in merged] == ["https://a", "https://b"]
    assert merged[0]["title"] == "wiki"


# ---- what actually gets published ------------------------------------------


def _grounded():
    return [
        {"title": "Kolar Gold Fields", "url": "https://en.wikipedia.org/wiki/KGF", "summary": "A mining region."},
        {"title": "Tailings study", "url": "https://doi.org/10.1/2", "summary": "Peer-reviewed work."},
    ]


def test_a_url_the_model_invented_never_reaches_the_description():
    cited = _cite(_grounded(), [
        {"title": "Ministry of Mines report", "url": "https://mines.gov.in/kgf-1998.pdf",
         "key_facts": ["The mine closed in 2001."]},
    ])

    assert [s["url"] for s in cited] == ["https://en.wikipedia.org/wiki/KGF", "https://doi.org/10.1/2"]


def test_the_facts_the_model_wrote_are_kept_on_the_url_we_fetched():
    cited = _cite(_grounded(), [
        {"url": "https://doi.org/10.1/2", "key_facts": ["Cyanide persisted in the tailings."]},
    ])

    assert cited[1]["key_facts"] == ["Cyanide persisted in the tailings."]


def test_a_trailing_slash_is_not_treated_as_a_different_source():
    cited = _cite(_grounded(), [
        {"url": "https://doi.org/10.1/2/", "key_facts": ["Matched anyway."]},
    ])

    assert cited[1]["key_facts"] == ["Matched anyway."]


def test_a_source_the_model_ignored_still_ships_with_its_own_summary():
    cited = _cite(_grounded(), [])

    assert cited[0]["key_facts"] == ["A mining region."]


def test_a_model_that_returned_nothing_usable_does_not_lose_the_sources():
    assert len(_cite(_grounded(), None)) == 2
    assert len(_cite(_grounded(), ["not a dict"])) == 2
