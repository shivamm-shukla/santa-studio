"""No clip is used twice for two different scenes.

A stock library answers every query with the same top result, and a long
script asks for the same subject over and over - "shipping container",
"shipping container", "a port at night". So two scenes that meant different
moments were handed identical footage, and a twenty-minute video that shows
one piece of footage six times looks like exactly what it is.

Two halves to this: the providers had no second-best to offer, and nothing
told them what had already been used.
"""

import pytest

from agents import visual_agent
from providers.visual import pexels_provider, pixabay_provider


# --------------------------------------------------------------------------
# The provider side: a second-best answer exists
# --------------------------------------------------------------------------

def _pexels_video(slug, link):
    return {"url": f"https://www.pexels.com/video/{slug}-12345/",
            "video_files": [{"width": 1280, "fps": 24, "link": link}]}


def test_a_library_ranks_every_relevant_result_not_only_the_best():
    results = [
        _pexels_video("cargo-ship-at-sea", "a.mp4"),
        _pexels_video("cargo-ship-in-port", "b.mp4"),
        _pexels_video("a-cat-on-a-sofa", "c.mp4"),
    ]
    ranked = pexels_provider._ranked("cargo ship", results)

    assert len(ranked) == 2, "the cat is not of the subject and does not rank"
    assert ranked[0]["video_files"][0]["link"] in ("a.mp4", "b.mp4")


def test_an_irrelevant_result_still_ranks_nowhere():
    """Offering a second-best must not mean offering something off-subject."""
    assert pexels_provider._ranked("cargo ship", [_pexels_video("a-cat-on-a-sofa", "c.mp4")]) == []


def test_pixabay_ranks_the_same_way():
    hits = [
        {"tags": "cargo ship, sea", "pageURL": "https://pixabay.com/v/ship-1/",
         "videos": {"medium": {"url": "a.mp4"}}},
        {"tags": "cargo ship, port", "pageURL": "https://pixabay.com/v/ship-2/",
         "videos": {"medium": {"url": "b.mp4"}}},
    ]
    assert len(pixabay_provider._ranked("cargo ship", hits)) == 2


def test_a_library_skips_what_the_run_has_already_used(monkeypatch):
    """The whole point: the same query twice gives two different clips."""
    results = [
        _pexels_video("cargo-ship-at-sea", "a.mp4"),
        _pexels_video("cargo-ship-in-port", "b.mp4"),
    ]

    class _Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"videos": results}

    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    monkeypatch.setattr(pexels_provider.requests, "get", lambda *a, **k: _Response())
    monkeypatch.setattr(pexels_provider, "download_asset", lambda url, kind, query: f"/tmp/{url}")

    first = pexels_provider.PexelsProvider().search("cargo ship")
    second = pexels_provider.PexelsProvider().search(
        "cargo ship", exclude={first["source_url"]}
    )

    assert first["source_url"] != second["source_url"]
    assert second["asset_path"]


def test_a_library_with_nothing_left_to_offer_says_so(monkeypatch):
    """Better an empty scene the fallback chain can serve than a repeat."""
    class _Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"videos": [_pexels_video("cargo-ship-at-sea", "a.mp4")]}

    monkeypatch.setenv("PEXELS_API_KEY", "test-key")
    monkeypatch.setattr(pexels_provider.requests, "get", lambda *a, **k: _Response())
    monkeypatch.setattr(pexels_provider, "download_asset", lambda url, kind, query: f"/tmp/{url}")

    assert pexels_provider.PexelsProvider().search("cargo ship", exclude={"a.mp4"})["asset_path"] == ""


# --------------------------------------------------------------------------
# The agent side: what has been used is carried between scenes
# --------------------------------------------------------------------------

class _Library:
    """A stock library with a fixed shelf, honouring `exclude`."""

    def __init__(self, *urls):
        self.shelf = list(urls)
        self.asked = []

    def search(self, query, asset_type="video", exclude=None, **kwargs):
        self.asked.append((query, frozenset(exclude or ())))
        for url in self.shelf:
            if url not in (exclude or set()):
                return {"asset_type": "video", "asset_path": f"/cache/{url}",
                        "source_url": url}
        return {"asset_type": "video", "asset_path": ""}


def _providers(monkeypatch, library):
    empty = _Library()
    monkeypatch.setattr(
        visual_agent, "get_provider",
        lambda kind, config: library if config["ACTIVE_PROVIDERS"]["visual"] == "pexels" else empty,
    )
    return empty


CONFIG = {"ACTIVE_PROVIDERS": {"visual": "pexels"}}


def test_two_scenes_asking_for_the_same_thing_get_different_clips(monkeypatch):
    library = _Library("one.mp4", "two.mp4", "three.mp4", "four.mp4")
    _providers(monkeypatch, library)

    result = visual_agent.run(
        {"scenes": [
            {"text": "short", "visual_hint": "a port"},
            {"text": "short", "visual_hint": "a port"},
        ]},
        CONFIG,
    )

    paths = [a["asset_path"] for a in result["output"]["scene_assets"] if a["asset_path"]]
    assert len(paths) == len(set(paths)), f"the same clip was used twice: {paths}"


def test_a_scene_that_runs_the_library_dry_is_left_for_the_fallbacks(monkeypatch):
    """An empty scene goes down the chain; a repeat would just look wrong."""
    library = _Library("only.mp4")
    _providers(monkeypatch, library)

    result = visual_agent.run(
        {"scenes": [
            {"text": "short", "visual_hint": "a port"},
            {"text": "short", "visual_hint": "a port"},
        ]},
        CONFIG,
    )

    paths = [a["asset_path"] for a in result["output"]["scene_assets"] if a["asset_path"]]
    assert paths == ["/cache/only.mp4"]


def test_the_library_is_told_what_has_already_been_taken(monkeypatch):
    library = _Library("one.mp4", "two.mp4", "three.mp4")
    _providers(monkeypatch, library)

    visual_agent.run(
        {"scenes": [{"text": "short", "visual_hint": "a port"},
                    {"text": "short", "visual_hint": "a port"}]},
        CONFIG,
    )

    assert any(taken for _, taken in library.asked), "exclude was never populated"
