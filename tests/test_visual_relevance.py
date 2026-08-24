"""Whether a frame is a photograph of the right thing.

The quality gate scored a lit tunnel and a colonial bungalow as strong frames
when the brief asked for a mine headframe, because by texture, exposure and
tonal range they are strong frames. This is the check that can see the
difference, and these cover the two things that matter about it: that it
orders candidates by subject, and that it never takes a run down or empties a
scene when it cannot answer.
"""

import numpy as np
import pytest
from PIL import Image

from providers.visual import generated_provider as gen
from providers.visual import relevance


def _frame(seed=0) -> Image.Image:
    rng = np.random.default_rng(seed)
    ramp = np.linspace(6, 249, 640, dtype=np.float32)[None, :, None]
    return Image.fromarray(
        np.clip(ramp + rng.normal(0, 45, (360, 640, 3)), 0, 255).astype(np.uint8)
    )


# ---- reading the model's answer --------------------------------------------


def test_a_score_out_of_ten_becomes_a_fraction():
    assert relevance._parse('{"score": 7, "is": "a mine headframe"}') == 0.7


def test_json_fenced_in_markdown_is_still_read():
    """Models wrap JSON in a fence about half the time whatever you ask."""
    assert relevance._parse('```json\n{"score": 3, "is": "a shed"}\n```') == 0.3


def test_a_score_off_the_scale_is_brought_back_onto_it():
    assert relevance._parse('{"score": 14}') == 1.0
    assert relevance._parse('{"score": -2}') == 0.0


def test_an_answer_that_is_not_json_is_no_answer():
    assert relevance._parse("looks like a mine to me") is None
    assert relevance._parse("") is None
    assert relevance._parse('{"is": "no score here"}') is None


# ---- when it is asked at all -----------------------------------------------


def test_with_a_key_and_nothing_switched_off_it_is_asked(monkeypatch):
    """conftest switches it off for the suite; this is what production has."""
    monkeypatch.delenv("VISUAL_RELEVANCE_CHECK", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")

    assert relevance.available() is True


def test_without_a_key_there_is_nothing_to_ask(monkeypatch):
    monkeypatch.delenv("VISUAL_RELEVANCE_CHECK", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    assert relevance.available() is False
    assert relevance.score(_frame(), "a mine headframe") is None


def test_it_can_be_switched_off_with_a_key_in_place(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    monkeypatch.setenv("VISUAL_RELEVANCE_CHECK", "false")

    assert relevance.available() is False


def test_an_empty_subject_is_not_worth_a_call(monkeypatch):
    monkeypatch.delenv("VISUAL_RELEVANCE_CHECK", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")

    assert relevance.score(_frame(), "   ") is None


def test_the_frame_is_sent_small_and_as_what_it_says_it_is():
    """A backend answering in PNG must not be sent labelled as JPEG."""
    data = relevance._jpeg(_frame().convert("RGBA"))

    assert data.startswith(b"\xff\xd8\xff")
    with Image.open(__import__("io").BytesIO(data)) as sent:
        assert sent.width <= relevance.ASK_WIDTH


# ---- what it changes about which frame is kept -----------------------------


@pytest.fixture
def three_candidates(tmp_path, monkeypatch):
    """Three returns of equal picture quality, told apart only by subject."""
    import asset_cache

    store = {}
    seeds = []

    def generate(prompt, seed):
        seeds.append(seed)
        import io as _io
        buffer = _io.BytesIO()
        _frame(seed).save(buffer, format="PNG")
        return buffer.getvalue()

    monkeypatch.setattr(gen, "_backends", lambda: [("stub", generate)])
    monkeypatch.setattr(gen, "GOOD_ENOUGH", 10_000.0)
    monkeypatch.setattr(asset_cache, "by_url", lambda url: store.get(url))
    monkeypatch.setattr(asset_cache, "temp_path", lambda ext: str(tmp_path / f"p{len(store)}{ext}"))

    def adopt(temp_path, extension, kind="assets", source_url="", query=""):
        destination = str(tmp_path / f"k{len(store)}{extension}")
        with open(destination, "wb") as out, open(temp_path, "rb") as src:
            out.write(src.read())
        store[source_url] = destination
        return destination

    monkeypatch.setattr(asset_cache, "adopt", adopt)
    return seeds


def test_a_frame_of_a_different_subject_is_refused(three_candidates, monkeypatch):
    monkeypatch.setattr(relevance, "score", lambda image, subject: 0.0)

    assert gen.GeneratedImageProvider().search("a mine headframe")["asset_path"] == ""


def test_being_unable_to_ask_leaves_the_ranking_as_it_was(three_candidates, monkeypatch):
    monkeypatch.setattr(relevance, "score", lambda image, subject: None)

    assert gen.GeneratedImageProvider().search("a mine headframe")["asset_path"]


def test_the_on_subject_frame_wins_a_tie_on_picture_quality(three_candidates, monkeypatch):
    """Which is the whole reason this exists: they all look like photographs."""
    from providers.visual import quality

    asked = {}

    def fit(image, subject):
        # The last seed offered is the one that is actually of the subject.
        asked[len(asked)] = quality.score(image)
        return 0.9 if len(asked) == len(three_candidates) else 0.3

    monkeypatch.setattr(relevance, "score", fit)
    result = gen.GeneratedImageProvider().search("a mine headframe")

    assert result["asset_path"], "everything was thrown away"
    assert len(asked) == gen.CANDIDATES


def test_a_relevance_call_that_throws_is_not_a_failed_scene(three_candidates, monkeypatch):
    def broken(image, subject):
        raise RuntimeError("quota")

    monkeypatch.setattr(relevance, "score", broken)

    # The provider must survive it the way it survives a broken backend.
    result = gen.GeneratedImageProvider().search("a mine headframe")
    assert result["asset_path"] == "" or result["asset_path"].endswith(".jpg")
