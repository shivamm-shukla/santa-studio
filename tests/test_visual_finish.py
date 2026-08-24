"""What decides a generated frame is good enough, and what is done to it after.

Two modules, one job between them: a free image service is inconsistent seed to
seed, so `quality` has to tell a photograph from a soft smear without a human
looking, and `filmic` has to leave what survives able to sit in a cut next to
1920-wide filmed footage without announcing itself.
"""

import numpy as np
import pytest
from PIL import Image

from providers.visual import filmic, quality


def _photograph(width=1024, height=576, sigma=45, seed=0) -> Image.Image:
    """Texture over a full tonal ramp - what a good return measures like."""
    rng = np.random.default_rng(seed)
    ramp = np.linspace(6, 249, width, dtype=np.float32)[None, :, None]
    return Image.fromarray(
        np.clip(ramp + rng.normal(0, sigma, (height, width, 3)), 0, 255).astype(np.uint8)
    )


def _smear() -> Image.Image:
    """Range but no texture - the soft return the gate exists to catch."""
    ramp = np.linspace(6, 249, 1024, dtype=np.float32)[None, :, None]
    return Image.fromarray(
        np.repeat(np.repeat(ramp, 576, axis=0), 3, axis=2).astype(np.uint8)
    )


def _letterboxed(image: Image.Image, band=60) -> Image.Image:
    """The same frame with true black bands baked into the pixels."""
    boxed = Image.new("RGB", (image.width, image.height + band * 2), (0, 0, 0))
    boxed.paste(image, (0, band))
    return boxed


# ---- telling a photograph from a smear -------------------------------------


def test_a_textured_frame_passes_and_a_soft_one_does_not():
    assert quality.usable(_photograph())[0] is True

    ok, reason = quality.usable(_smear())
    assert ok is False
    assert "soft" in reason


def test_a_flat_wash_is_named_as_such():
    ok, reason = quality.usable(Image.new("RGB", (1024, 576), (90, 92, 94)))

    assert ok is False and "flat" in reason


def test_a_frame_crushed_past_recovery_is_refused():
    half = _photograph()
    pixels = np.asarray(half).copy()
    pixels[:, : pixels.shape[1] // 2] = 0

    ok, reason = quality.usable(Image.fromarray(pixels))
    assert ok is False and "clipped" in reason


def test_a_frame_too_small_to_fill_the_timeline_is_refused():
    assert quality.usable(_photograph(width=200, height=112))[0] is False


def test_the_sharper_of_two_frames_scores_higher():
    assert quality.score(_photograph(sigma=45)) > quality.score(_photograph(sigma=6))


def test_the_score_does_not_move_with_the_size_it_was_measured_at():
    """Thresholds have to survive a backend that returns a different size."""
    big = quality.score(_photograph(width=1536, height=864, seed=3))
    small = quality.score(_photograph(width=1024, height=576, seed=3))

    assert small * 0.75 < big < small * 1.35


# ---- baked-in bars ---------------------------------------------------------


def test_black_bands_are_cropped_off_rather_than_scaled_as_picture():
    trimmed = quality.trim(_letterboxed(_photograph()))

    # A row either side goes with them, deliberately: JPEG smears the boundary
    # into something just light enough to read as picture, and a surviving
    # black row stretched across the finished frame is the worse outcome.
    assert 574 <= trimmed.height <= 576
    assert np.asarray(trimmed.convert("L"))[0].max() > 0, "a black row survived"


def test_a_dark_sky_is_not_mistaken_for_a_letterbox():
    dark = np.asarray(_photograph()).copy()
    dark[:100] = dark[:100] // 6 + 3  # dark, but not black

    assert quality.trim(Image.fromarray(dark)).size == (1024, 576)


def test_a_frame_that_is_mostly_bars_is_left_for_the_gate_to_refuse():
    """Cropping it would leave a sliver; the whole frame is the real problem."""
    mostly = _letterboxed(_photograph(height=80), band=300)

    assert quality.trim(mostly).size == mostly.size


def _print_bordered(image: Image.Image, margin=40, shade=190) -> Image.Image:
    """The same frame as a photograph of a print, paper margin and all.

    The margin carries noise rather than being one flat colour, because a real
    one does: measured off a return that came back like this, the border lines
    ran a standard deviation of about five, and a detector tuned for a
    perfectly flat margin walked straight past it.
    """
    rng = np.random.default_rng(11)
    paper = rng.normal(shade, 5.0, (image.height + margin * 2, image.width + margin * 2, 3))
    bordered = Image.fromarray(np.clip(paper, 0, 255).astype(np.uint8))
    bordered.paste(image, (margin, margin))
    return bordered


def test_a_paper_margin_is_cropped_off_like_a_black_one():
    """Naming a film stock can get a photograph of a print back."""
    trimmed = quality.trim(_print_bordered(_photograph()))

    assert trimmed.size[0] < 1024 + 80 and trimmed.size[1] < 576 + 80
    assert abs(trimmed.width - 1024) <= 4 and abs(trimmed.height - 576) <= 4


def test_a_blown_white_sky_is_not_cropped_as_a_paper_margin():
    """It is flat enough to read as border, and it is the picture."""
    sky = np.asarray(_photograph()).copy()
    sky[:120] = 250

    assert quality.trim(Image.fromarray(sky)).size == (1024, 576)


def test_a_margin_on_three_sides_is_not_a_border():
    """A border goes all the way round; that is what tells it from a subject."""
    lopsided = _print_bordered(_photograph())
    kept = np.asarray(lopsided).copy()
    kept[-40:] = np.asarray(_photograph(width=lopsided.width, height=40, seed=5))

    assert quality.border(Image.fromarray(kept)) == (0, 0, 0, 0)


def test_a_border_wider_than_the_picture_is_left_alone():
    """Not a bordered photograph - a photograph of something else."""
    huge = _print_bordered(_photograph(width=200, height=120), margin=400)

    assert quality.border(huge) == (0, 0, 0, 0)


# ---- the finish ------------------------------------------------------------


def test_what_comes_out_is_the_timeline_frame():
    assert filmic.finish(_photograph(), "key").size == (1920, 1080)


def test_a_frame_of_the_wrong_shape_is_cropped_not_padded():
    """Padding would put back the bars the trim just took off."""
    finished = filmic.finish(_photograph(width=800, height=800), "key")

    assert finished.size == (1920, 1080)
    corner = np.asarray(finished)[:4, :4]
    assert corner.mean() > 6, "the frame was padded with black"


def test_bars_are_gone_before_the_finish_scales_anything():
    finished = filmic.finish(_letterboxed(_photograph()), "key")
    top = np.asarray(finished)[:20].mean()

    assert top > 12, "a black band survived into the finished frame"


def test_the_shadows_are_lifted_off_pure_black():
    """Digital zero is a render; film has a toe.

    Not "no pixel is zero" - grain is added after the lift and will put the
    odd one there, exactly as film does. What matters is that the shadows as a
    body sit above zero rather than clamped to it.
    """
    pixels = np.asarray(filmic.finish(_photograph(sigma=10), "key"))

    assert np.percentile(pixels, 1) > 0
    assert (pixels == 0).mean() < 0.001


def test_the_finish_adds_texture_rather_than_softening_the_upscale():
    source = _photograph()
    scaled = source.resize((1920, 1080), Image.LANCZOS)

    assert quality.detail(filmic.finish(source, "key")) > quality.detail(scaled)


def test_the_same_frame_finishes_identically_every_time():
    """A rerun must not regenerate the cut with different grain."""
    source = _photograph()
    first = np.asarray(filmic.finish(source, "key"))
    second = np.asarray(filmic.finish(source, "key"))

    assert np.array_equal(first, second)


def test_two_frames_do_not_share_one_grain_pattern():
    source = _photograph()
    first = np.asarray(filmic.finish(source, "scene-1"))
    second = np.asarray(filmic.finish(source, "scene-2"))

    assert not np.array_equal(first, second)


def test_the_finish_is_not_visible_as_an_effect():
    """Every step is meant to go unnoticed; a big move here is a bug."""
    source = _photograph()
    before = np.asarray(source.resize((1920, 1080), Image.LANCZOS), dtype=np.float32)
    after = np.asarray(filmic.finish(source, "key"), dtype=np.float32)

    assert abs(after.mean() - before.mean()) < 12


def test_the_model_that_made_it_is_not_written_into_the_file(tmp_path):
    source = _photograph()
    exif = source.getexif()
    exif[271] = "sana"
    tagged = tmp_path / "tagged.jpg"
    source.save(tagged, exif=exif)

    out = tmp_path / "finished.jpg"
    with Image.open(tagged) as loaded:
        filmic.save(filmic.finish(loaded, "key"), str(out))

    with Image.open(out) as written:
        assert dict(written.getexif()) == {}


def test_a_grainy_full_frame_still_actually_writes(tmp_path):
    """The JPEG encoder's optimise pass overruns its buffer on one of these."""
    out = tmp_path / "grainy.jpg"
    filmic.save(filmic.finish(_photograph(sigma=70), "key"), str(out))

    assert out.stat().st_size > 0
