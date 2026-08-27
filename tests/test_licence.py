"""Who may use the output commercially, and what the check is worth.

Santa Studio is source-available: anyone may make videos, and putting them on
a channel you earn from needs a grant that a merged pull request earns. Output
carries a corner mark until one is installed.

What is being pinned here is narrow and worth stating exactly. The signature
stops anyone *issuing themselves* a grant - that is real, and these tests hold
it. It does not stop anyone deleting the check, and no test here pretends
otherwise, because nothing running on somebody else's machine could. LICENSE
and the trademark are what stand behind that; this is the part that makes the
honest path the easy one.
"""

import base64
import importlib
import json

import pytest

import licence
import watermark


@pytest.fixture
def signing_key():
    """A throwaway key standing in for the project's own."""
    from cryptography.hazmat.primitives.asymmetric import ed25519

    return ed25519.Ed25519PrivateKey.generate()


def _grant(key, holder="Ada Lovelace", reason="PR #14 merged", issued="2026-08-27"):
    body = {"holder": holder, "reason": reason, "issued": issued}
    message = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    return json.dumps({
        "grant": body,
        "signature": base64.b64encode(key.sign(message)).decode(),
    })


def _trusting(monkeypatch, key):
    """Points the checker at `key` as the project's signing key."""
    from cryptography.hazmat.primitives import serialization

    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    monkeypatch.setattr(licence, "SIGNING_KEY", raw.hex())


# ---------------------------------------------------------------------------
# The default
# ---------------------------------------------------------------------------


def test_output_is_marked_when_there_is_no_grant(monkeypatch):
    monkeypatch.setattr(licence, "_token", lambda: "")

    grant = licence.status()
    assert grant.valid is False
    assert grant.watermark is True
    assert licence.marks_output() is True


def test_a_grant_stops_the_mark(monkeypatch, signing_key):
    _trusting(monkeypatch, signing_key)
    monkeypatch.setattr(licence, "_token", lambda: _grant(signing_key))

    grant = licence.status()
    assert grant.valid is True
    assert grant.holder == "Ada Lovelace"
    assert grant.reason == "PR #14 merged"
    assert grant.watermark is False


# ---------------------------------------------------------------------------
# What the signature is actually for
# ---------------------------------------------------------------------------


def test_nobody_can_write_themselves_a_grant(monkeypatch, signing_key):
    """The whole point. A grant is not a flag in a file - it is a signature,
    and producing one needs a key that is not in this repository."""
    from cryptography.hazmat.primitives.asymmetric import ed25519

    _trusting(monkeypatch, signing_key)
    forged = _grant(ed25519.Ed25519PrivateKey.generate(), holder="Not A Contributor")
    monkeypatch.setattr(licence, "_token", lambda: forged)

    assert licence.status().valid is False
    assert licence.marks_output() is True


def test_editing_the_name_on_a_real_grant_invalidates_it(monkeypatch, signing_key):
    """A grant is issued to a person; it is not a licence file to pass around
    with the name swapped."""
    _trusting(monkeypatch, signing_key)
    real = json.loads(_grant(signing_key))
    real["grant"]["holder"] = "Somebody Else"
    monkeypatch.setattr(licence, "_token", lambda: json.dumps(real))

    assert licence.status().valid is False


def test_reformatting_a_grant_does_not_break_it(monkeypatch, signing_key):
    """Signed over the canonical form, so a file that has been through a
    formatter still works."""
    _trusting(monkeypatch, signing_key)
    real = json.loads(_grant(signing_key))
    monkeypatch.setattr(
        licence, "_token",
        lambda: json.dumps({"signature": real["signature"], "grant": dict(reversed(list(real["grant"].items())))}, indent=4),
    )

    assert licence.status().valid is True


def test_rubbish_in_the_file_is_not_a_grant(monkeypatch):
    for text in ("", "{}", "not json at all", '{"grant": {}}'):
        monkeypatch.setattr(licence, "_token", lambda t=text: t)
        assert licence.status().valid is False


def test_a_grant_cannot_be_checked_without_the_crypto_library(monkeypatch, signing_key):
    """An unchecked grant is not a grant. Failing open here would make the
    signature decorative."""
    _trusting(monkeypatch, signing_key)
    monkeypatch.setattr(licence, "_token", lambda: _grant(signing_key))

    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def without_crypto(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", without_crypto)
    assert licence.status().valid is False


# ---------------------------------------------------------------------------
# The mark itself
# ---------------------------------------------------------------------------


def test_the_mark_is_drawn_in_the_corner_and_nowhere_else():
    """A mark over the middle of the picture teaches people to strip it."""
    image = watermark.image(1920, 1080)
    assert image.size == (1920, 1080)

    alpha = image.split()[-1]
    assert alpha.crop((0, 0, 1400, 900)).getbbox() is None, "nothing outside the corner"
    assert alpha.crop((1400, 900, 1920, 1080)).getbbox() is not None, "something in it"


def test_the_mark_scales_with_the_frame_rather_than_being_a_pixel_count():
    """So a vertical short carries the same mark as a 1080p master."""
    def height_of(w, h):
        box = watermark.image(w, h).split()[-1].getbbox()
        return (box[3] - box[1]) / h

    assert height_of(1920, 1080) == pytest.approx(height_of(1080, 1920), abs=0.02)


def test_no_clip_is_made_when_there_is_a_grant(monkeypatch):
    monkeypatch.setattr(licence, "marks_output", lambda: False)
    assert watermark.clip(1920, 1080, 5.0) is None


def test_stamping_a_finished_file_is_a_no_op_under_a_grant(monkeypatch, tmp_path):
    """So a caller can use it unconditionally."""
    monkeypatch.setattr(licence, "marks_output", lambda: False)
    video = tmp_path / "master.mp4"
    video.write_bytes(b"not really a video")

    assert watermark.burn_into(str(video)) == str(video)
    assert video.read_bytes() == b"not really a video"
