"""Generation is the last resort in the visual chain, and it has to fail quietly.

Every provider before this one returns an empty asset_path rather than raising
when it has nothing, because visual_agent reads that as "try the next one".
Generation is the end of the chain, so if it throws, a scene that could have
been left blank takes the whole run down with it.
"""

import pytest

from providers.visual import generated_provider as gen


PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """A cache that records what was adopted, without touching the real one."""
    import asset_cache

    store = {}

    monkeypatch.setattr(gen, "_backends", lambda: [("stub", lambda prompt: PNG)])
    monkeypatch.setattr(asset_cache, "by_url", lambda url: store.get(url))
    monkeypatch.setattr(asset_cache, "temp_path", lambda ext: str(tmp_path / f"partial{ext}"))

    def adopt(temp_path, extension, kind="assets", source_url="", query=""):
        destination = str(tmp_path / f"kept{extension}")
        with open(destination, "wb") as out, open(temp_path, "rb") as src:
            out.write(src.read())
        store[source_url] = destination
        return destination

    monkeypatch.setattr(asset_cache, "adopt", adopt)
    return store


def test_a_generated_still_comes_back_as_an_image_asset(cache):
    result = gen.GeneratedImageProvider().search("a mine headframe at dusk")

    assert result["asset_type"] == "image"
    assert result["asset_path"].endswith(".png")


def test_the_same_prompt_is_not_generated_twice(cache, monkeypatch):
    calls = []

    def counting(prompt):
        calls.append(prompt)
        return PNG

    monkeypatch.setattr(gen, "_backends", lambda: [("stub", counting)])
    provider = gen.GeneratedImageProvider()

    first = provider.search("a mine headframe at dusk")
    second = provider.search("a mine headframe at dusk")

    assert first == second
    assert len(calls) == 1, "the daily quota was spent twice on one prompt"


def test_a_backend_that_raises_falls_through_to_the_next(cache, monkeypatch):
    def broken(prompt):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(gen, "_backends", lambda: [("broken", broken), ("ok", lambda p: JPG)])

    result = gen.GeneratedImageProvider().search("a mine headframe")
    assert result["asset_path"].endswith(".jpg")


def test_an_error_page_served_with_a_200_is_not_an_image(cache, monkeypatch):
    monkeypatch.setattr(gen, "_backends", lambda: [("html", lambda p: b'{"error":"busy"}')])

    assert gen.GeneratedImageProvider().search("anything")["asset_path"] == ""


def test_every_backend_failing_is_an_empty_path_not_an_exception(cache, monkeypatch):
    def broken(prompt):
        raise RuntimeError("no")

    monkeypatch.setattr(gen, "_backends", lambda: [("a", broken), ("b", broken)])

    assert gen.GeneratedImageProvider().search("anything")["asset_path"] == ""


def test_an_empty_query_never_reaches_a_backend(monkeypatch):
    monkeypatch.setattr(gen, "_backends", lambda: [("boom", lambda p: pytest.fail("called"))])

    assert gen.GeneratedImageProvider().search("   ")["asset_path"] == ""


# ---------------------------------------------------------------------------
# Which backends are even available
# ---------------------------------------------------------------------------

def test_gemini_stays_out_of_the_chain_until_billing_is_on(monkeypatch):
    """Its image models refuse a free-tier key outright - limit 0, not spent."""
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    monkeypatch.delenv("GEMINI_IMAGE_ENABLED", raising=False)

    assert [name for name, _ in gen._backends()] == ["pollinations"]


def test_gemini_leads_once_it_is_paid_for(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    monkeypatch.setenv("GEMINI_IMAGE_ENABLED", "true")

    assert [name for name, _ in gen._backends()] == ["gemini", "pollinations"]


def test_the_prompt_asks_for_a_photograph_and_refuses_watermarks():
    prompt = gen.PROMPT.format(query="a mine")

    assert "photorealistic documentary photograph" in prompt
    assert "No text" in prompt and "watermarks" in prompt
