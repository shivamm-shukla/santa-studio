"""Sourcing is a deliverable on this channel, not an internal note.

The videos take positions on contested things, so a claim a viewer cannot
check is a claim we should not have made. These pin the two artefacts that
promise makes: the links in the description, and the record next to the
master file.
"""

import pytest

import sources


RESEARCH = {
    "sources": [
        {
            "title": "Kolar Gold Fields",
            "url": "https://en.wikipedia.org/wiki/Kolar_Gold_Fields",
            "key_facts": ["Closed in 2001", "Reached 3.2 km deep"],
        },
        {
            "title": "Bharat Gold Mines Limited",
            "url": "https://example.org/bgml",
            "key_facts": ["Nationalised in 1972"],
        },
    ]
}

FACTCHECK = {
    "verified_claims": ["The mine closed in 2001"],
    "flagged_claims": ["It was the deepest mine on earth"],
    "confidence_scores": {"The mine closed in 2001": "high"},
}


# ---------------------------------------------------------------------------
# What counts as a source
# ---------------------------------------------------------------------------

def test_a_source_without_a_url_is_not_citable():
    collected = sources.collect({"sources": [{"title": "A book someone read", "key_facts": ["x"]}]})
    assert collected == []


def test_the_same_url_twice_is_one_source_with_both_its_facts():
    collected = sources.collect({"sources": [
        {"title": "KGF", "url": "https://example.org/a", "key_facts": ["one"]},
        {"title": "KGF again", "url": "https://example.org/a", "key_facts": ["one", "two"]},
    ]})

    assert len(collected) == 1
    assert collected[0]["key_facts"] == ["one", "two"]


def test_no_research_at_all_is_not_a_crash():
    assert sources.collect(None) == []
    assert sources.collect({}) == []


# ---------------------------------------------------------------------------
# The description
# ---------------------------------------------------------------------------

def test_every_source_reaches_the_description_as_a_clickable_link():
    block = sources.description_block(sources.collect(RESEARCH))

    assert "https://en.wikipedia.org/wiki/Kolar_Gold_Fields" in block
    assert "https://example.org/bgml" in block
    assert block.startswith("Sources")


def test_the_drafted_copy_keeps_its_place_above_the_links():
    text = sources.with_sources("Why the mine closed.", RESEARCH)

    assert text.startswith("Why the mine closed.")
    assert text.index("Why the mine closed.") < text.index("Sources")


def test_the_sources_ship_even_when_the_draft_did_not():
    text = sources.with_sources("", RESEARCH)

    assert text.startswith("Sources")
    assert "https://example.org/bgml" in text


def test_a_description_stays_inside_youtubes_limit():
    many = {"sources": [
        {"title": f"Source number {i}", "url": f"https://example.org/{i}", "key_facts": []}
        for i in range(400)
    ]}

    text = sources.with_sources("x" * 4000, many)
    assert len(text) <= sources.DESCRIPTION_LIMIT


def test_the_budget_never_cuts_a_link_in_half():
    many = {"sources": [
        {"title": f"Source {i}", "url": f"https://example.org/a-fairly-long-path/{i}", "key_facts": []}
        for i in range(200)
    ]}

    block = sources.description_block(sources.collect(many), budget=300)
    for line in block.splitlines():
        if line.startswith("http"):
            assert line in {f"https://example.org/a-fairly-long-path/{i}" for i in range(200)}


def test_nothing_to_cite_leaves_the_description_alone():
    assert sources.with_sources("Just the copy.", {"sources": []}) == "Just the copy."


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------

def test_the_document_carries_sources_claims_and_what_was_dropped():
    doc = sources.document("Why the Kolar Gold Fields shut down", RESEARCH, FACTCHECK)

    assert "Why the Kolar Gold Fields shut down" in doc
    assert "https://example.org/bgml" in doc
    assert "Reached 3.2 km deep" in doc
    assert "The mine closed in 2001" in doc
    assert "high confidence" in doc
    # The claims we refused to make are recorded, not quietly discarded.
    assert "It was the deepest mine on earth" in doc


def test_a_video_with_no_sources_says_so_rather_than_pretending():
    doc = sources.document("Something", {"sources": []}, {})
    assert "No citable sources" in doc


def test_the_document_is_written_next_to_the_master(tmp_path, monkeypatch):
    monkeypatch.setattr(sources.paths, "scoped_dir", lambda kind: tmp_path)

    path = sources.write_document("A topic", RESEARCH, FACTCHECK)

    assert path.endswith("sources.md")
    written = open(path, encoding="utf-8").read()
    assert "https://example.org/bgml" in written


def test_a_bare_url_string_is_still_a_source():
    """Some research providers return links with nothing said about them."""
    collected = sources.collect({"sources": ["https://example.org/a", "not-a-url", 7]})

    assert [s["url"] for s in collected] == ["https://example.org/a"]
    assert collected[0]["title"] == "https://example.org/a"
