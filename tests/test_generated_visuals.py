"""Generation is the last resort in the visual chain, and it has to fail quietly.

Every provider before this one returns an empty asset_path rather than raising
when it has nothing, because visual_agent reads that as "try the next one".
Generation is the end of the chain, so if it throws, a scene that could have
been left blank takes the whole run down with it.

Past that, these cover what the provider now does with what comes back: it
generates several, throws away the ones that are not photographs, keeps the
best, and finishes it to the timeline's frame before anything sees it.
"""

import io

import numpy as np
import pytest
from PIL import Image

from providers.visual import generated_provider as gen


def _bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _textured(width=1024, height=576, sigma=60, seed=0) -> bytes:
    """A frame with real texture in it - what a good return looks like.

    Texture over a full tonal ramp, not texture alone: the quality score
    weights range as well as detail, and flat noise scores like the soft
    returns the gate exists to catch.
    """
    rng = np.random.default_rng(seed)
    ramp = np.linspace(8, 247, width, dtype=np.float32)[None, :, None]
    pixels = np.clip(ramp + rng.normal(0, sigma, (height, width, 3)), 0, 255)
    return _bytes(Image.fromarray(pixels.astype(np.uint8)))


def _flat() -> bytes:
    """A frame with no tonal range - the failure the quality gate is for."""
    return _bytes(Image.new("RGB", (1024, 576), (90, 92, 94)))


NOT_AN_IMAGE = b'{"error":"busy"}'


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """A cache that records what was adopted, without touching the real one."""
    import asset_cache

    store = {}
    monkeypatch.setattr(gen, "_backends", lambda: [("stub", lambda prompt, seed: _textured())])
    monkeypatch.setattr(asset_cache, "by_url", lambda url: store.get(url))
    monkeypatch.setattr(
        asset_cache, "temp_path", lambda ext: str(tmp_path / f"partial{len(store)}{ext}")
    )

    def adopt(temp_path, extension, kind="assets", source_url="", query=""):
        destination = str(tmp_path / f"kept{len(store)}{extension}")
        with open(destination, "wb") as out, open(temp_path, "rb") as src:
            out.write(src.read())
        store[source_url] = destination
        return destination

    monkeypatch.setattr(asset_cache, "adopt", adopt)
    return store


# ---- the contract with visual_agent ----------------------------------------


def test_a_generated_still_comes_back_as_an_image_asset(cache):
    result = gen.GeneratedImageProvider().search("a mine headframe at dusk")

    assert result["asset_type"] == "image"
    assert result["asset_path"].endswith(".jpg")


def test_a_backend_that_raises_falls_through_to_the_next(cache, monkeypatch):
    def broken(prompt, seed):
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(gen, "_backends", lambda: [
        ("broken", broken), ("ok", lambda p, s: _textured()),
    ])

    assert gen.GeneratedImageProvider().search("a mine headframe")["asset_path"]


def test_an_error_page_served_with_a_200_is_not_an_image(cache, monkeypatch):
    monkeypatch.setattr(gen, "_backends", lambda: [("html", lambda p, s: NOT_AN_IMAGE)])

    assert gen.GeneratedImageProvider().search("anything")["asset_path"] == ""


def test_every_backend_failing_is_an_empty_path_not_an_exception(cache, monkeypatch):
    def broken(prompt, seed):
        raise RuntimeError("no")

    monkeypatch.setattr(gen, "_backends", lambda: [("a", broken), ("b", broken)])

    assert gen.GeneratedImageProvider().search("anything")["asset_path"] == ""


def test_an_empty_query_never_reaches_a_backend(monkeypatch):
    monkeypatch.setattr(gen, "_backends", lambda: [("boom", lambda p, s: pytest.fail("called"))])

    assert gen.GeneratedImageProvider().search("   ")["asset_path"] == ""


# ---- what gets generated, and how often ------------------------------------


def test_the_backend_is_asked_for_a_camera_brief_not_the_bare_query(cache, monkeypatch):
    seen = []

    def record(prompt, seed):
        seen.append(prompt)
        return _textured()

    monkeypatch.setattr(gen, "_backends", lambda: [("stub", record)])
    gen.GeneratedImageProvider().search("abandoned mine headframe")

    assert "abandoned mine headframe" in seen[0]
    assert "f/" in seen[0], "no aperture, so no camera was specified"
    assert "no watermark" in seen[0]


def test_the_same_shot_is_not_generated_twice(cache, monkeypatch):
    calls = []
    monkeypatch.setattr(gen, "_backends", lambda: [
        ("stub", lambda p, s: (calls.append(s), _textured())[1]),
    ])
    provider = gen.GeneratedImageProvider()

    first = provider.search("a mine headframe at dusk")
    spent = len(calls)
    second = provider.search("a mine headframe at dusk")

    assert first == second
    assert len(calls) == spent, "the quota was spent twice on one shot"


def test_the_same_subject_in_another_scene_is_a_different_photograph(cache):
    provider = gen.GeneratedImageProvider()

    third = provider.search("a mine headframe", variation=3)
    ninth = provider.search("a mine headframe", variation=9)

    assert third["asset_path"] != ninth["asset_path"]


def test_several_seeds_are_tried_and_the_best_one_kept(cache, monkeypatch):
    """The service is inconsistent seed to seed; that is the whole reason."""
    offered = {}

    def varying(prompt, seed):
        # Ascending texture, so the last seed offered is the best one.
        sigma = 8 + len(offered) * 30
        data = _textured(sigma=sigma, seed=seed)
        offered[seed] = sigma
        return data

    monkeypatch.setattr(gen, "_backends", lambda: [("stub", varying)])
    monkeypatch.setattr(gen, "GOOD_ENOUGH", 10_000.0)  # never satisfied, so all are tried

    result = gen.GeneratedImageProvider().search("a mine headframe")

    assert len(offered) == gen.CANDIDATES
    assert result["asset_path"], "every candidate was discarded"


def test_a_strong_first_result_ends_the_search(cache, monkeypatch):
    tried = []
    monkeypatch.setattr(gen, "_backends", lambda: [
        ("stub", lambda p, s: (tried.append(s), _textured(sigma=70, seed=s))[1]),
    ])

    gen.GeneratedImageProvider().search("a mine headframe")

    assert len(tried) == 1, "round trips spent after the shot was already good"


def test_a_flat_wash_is_not_offered_as_a_photograph(cache, monkeypatch):
    monkeypatch.setattr(gen, "_backends", lambda: [("stub", lambda p, s: _flat())])

    assert gen.GeneratedImageProvider().search("a mine headframe")["asset_path"] == ""


# ---- what the file that ships looks like -----------------------------------


def test_what_ships_is_the_timeline_frame_size(cache):
    result = gen.GeneratedImageProvider().search("a mine headframe")

    with Image.open(result["asset_path"]) as image:
        assert image.size == (1920, 1080)


def test_the_model_that_made_it_is_not_written_into_the_file(cache, monkeypatch):
    """Pollinations tags returns with the prompt and the model name in EXIF."""
    def with_exif(prompt, seed):
        rng = np.random.default_rng(seed)
        image = Image.fromarray(
            np.clip(rng.normal(128, 60, (576, 1024, 3)), 0, 255).astype(np.uint8)
        )
        buffer = io.BytesIO()
        exif = image.getexif()
        exif[271] = "sana"  # Make
        image.save(buffer, format="JPEG", exif=exif)
        return buffer.getvalue()

    monkeypatch.setattr(gen, "_backends", lambda: [("stub", with_exif)])
    result = gen.GeneratedImageProvider().search("a mine headframe")

    with Image.open(result["asset_path"]) as image:
        assert dict(image.getexif()) == {}


# ---- which backends are even available -------------------------------------


def test_gemini_stays_out_of_the_chain_until_billing_is_on(monkeypatch):
    """Its image models refuse a free-tier key outright - limit 0, not spent."""
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    monkeypatch.delenv("GEMINI_IMAGE_ENABLED", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    assert [name for name, _ in gen._backends()] == ["pollinations"]


def test_gemini_joins_once_it_is_paid_for(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "a-key")
    monkeypatch.setenv("GEMINI_IMAGE_ENABLED", "true")
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    assert [name for name, _ in gen._backends()] == ["gemini", "pollinations"]


def test_cloudflare_leads_when_the_account_exists(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.delenv("GEMINI_IMAGE_ENABLED", raising=False)

    assert [name for name, _ in gen._backends()][0] == "cloudflare"


def test_half_a_cloudflare_account_is_not_a_backend(monkeypatch):
    """A request that cannot succeed is worse than a request not made."""
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    monkeypatch.delenv("GEMINI_IMAGE_ENABLED", raising=False)

    assert "cloudflare" not in [name for name, _ in gen._backends()]


def test_improving_the_brief_does_not_hand_back_the_old_picture(cache, monkeypatch):
    """Keyed on the subject, a better prompt reached nothing already generated."""
    from providers.visual import art_direction

    generated = []
    monkeypatch.setattr(gen, "_backends", lambda: [
        ("stub", lambda p, s: (generated.append(p), _textured(seed=s))[1]),
    ])
    provider = gen.GeneratedImageProvider()

    first = provider.search("a mine headframe")
    monkeypatch.setattr(art_direction, "brief", lambda subject, variation=0: "a better brief")
    second = provider.search("a mine headframe")

    assert second["asset_path"] != first["asset_path"]
    assert "a better brief" in generated[-1]


def test_cloudflare_is_sent_only_what_it_accepts(monkeypatch):
    """Workers AI validates the body strictly: an unknown property is a 400,
    not a property it ignores. `seed`, `width` and `height` are all refused."""
    sent = {}

    class _Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            import base64
            return {"result": {"image": base64.b64encode(_textured()).decode()}}

    def post(url, headers=None, json=None, timeout=None):
        sent.update(json or {})
        return _Response()

    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "token")
    monkeypatch.setattr(gen.requests, "post", post)

    gen._from_cloudflare("a brief", 4242)

    assert set(sent) == {"prompt", "steps"}
    assert sent["steps"] <= 8, "schnell is a few-step model and caps at eight"


def test_a_document_never_reaches_a_backend(cache, monkeypatch):
    """Refused before a request is made, not filtered after one comes back."""
    monkeypatch.setattr(gen, "_backends", lambda: [
        ("boom", lambda p, s: pytest.fail("a document was sent to be generated")),
    ])

    result = gen.GeneratedImageProvider().search("official closure notice BGML 2001")
    assert result["asset_path"] == ""
