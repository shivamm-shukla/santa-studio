"""Moving a still as a scene with depth in it.

A Ken Burns move slides every pixel at one rate, which is what a photograph of
a photograph looks like. With a depth map the near parts of the picture can
cross the frame faster than the far parts.

The first attempt cut the picture into planes by depth and is the reason these
say what they say: a mine headframe is a steel lattice spanning most of the
depth range, so any threshold ran through the middle of it and the halves slid
apart, leaving the tower with a ghost of itself beside it. A continuous warp
has no thresholds and nothing to tear along.
"""

import numpy as np
import pytest
from PIL import Image

from render import parallax


def _picture(width=320, height=180):
    """Vertical stripes: a horizontal displacement is obvious on them."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, ::16] = 255
    frame[:, 1::16] = 255
    return Image.fromarray(frame)


def _ramp_depth(width=320, height=180):
    """Near on the left, far on the right."""
    return np.tile(np.linspace(1.0, 0.0, width, dtype=np.float32), (height, 1))


# ---- preparing the map -----------------------------------------------------


def test_a_map_of_another_size_is_brought_to_the_frame():
    prepared = parallax.prepare(_ramp_depth(160, 90), (320, 180))

    assert prepared.shape == (180, 320)


def test_the_map_is_normalised_however_it_arrived():
    prepared = parallax.prepare(_ramp_depth() * 0.2 + 0.5, (320, 180))

    assert prepared.min() == pytest.approx(0.0, abs=0.02)
    assert prepared.max() == pytest.approx(1.0, abs=0.02)


def test_a_flat_map_is_no_map_at_all():
    """Nothing to separate, so the caller should use the flat move."""
    assert parallax.prepare(np.full((180, 320), 0.5, dtype=np.float32), (320, 180)) is None
    assert parallax.prepare(None, (320, 180)) is None


def test_the_map_is_smoothed_before_it_displaces_anything():
    """Local detail in an estimated map becomes a ripple in a straight line."""
    noisy = np.random.default_rng(0).random((180, 320)).astype(np.float32)

    prepared = parallax.prepare(noisy, (320, 180))
    assert np.abs(np.diff(prepared, axis=1)).mean() < np.abs(np.diff(noisy, axis=1)).mean() / 4


# ---- the warp itself -------------------------------------------------------


def test_near_pixels_travel_further_than_far_ones():
    """The whole effect, and the thing a flat move cannot do."""
    picture = _picture()
    depth = parallax.prepare(_ramp_depth(), picture.size)

    moved = np.asarray(parallax.warp(picture, depth, (30, 0)).convert("L"), dtype=np.float32)
    still = np.asarray(picture.convert("L"), dtype=np.float32)

    near = np.abs(moved[:, :80] - still[:, :80]).mean()
    far = np.abs(moved[:, -80:] - still[:, -80:]).mean()
    assert near > far, "the near side did not move further than the far side"


def test_the_frame_is_always_full():
    """Reading backwards is what guarantees this: every output pixel is given
    something, so a near part moving away never leaves a hole."""
    picture = _picture()
    depth = parallax.prepare(_ramp_depth(), picture.size)

    out = np.asarray(parallax.warp(picture, depth, (60, 0), 1.0))
    assert out.shape == (180, 320, 3)
    assert not np.all(out[:, :4] == 0), "a hole opened at the edge"


def test_no_move_leaves_the_picture_alone():
    picture = _picture()
    depth = parallax.prepare(_ramp_depth(), picture.size)

    out = np.asarray(parallax.warp(picture, depth, (0, 0), 1.0), dtype=np.float32)
    assert np.abs(out - np.asarray(picture, dtype=np.float32)).mean() < 1.0


def test_a_missing_map_returns_the_picture_untouched():
    picture = _picture()

    assert parallax.warp(picture, None, (30, 0)) is picture


def test_a_map_of_the_wrong_shape_is_refused_rather_than_guessed_at():
    picture = _picture()
    wrong = np.zeros((90, 160), dtype=np.float32)

    assert parallax.warp(picture, wrong, (30, 0)) is picture


def test_the_displacement_stays_small_enough_not_to_bend_the_picture():
    """An estimated depth map is not smooth along a straight edge, and the
    warp bends the picture to match it faithfully. Architecture is the hard
    case: too much relief and a headframe's steel visibly bows."""
    assert parallax.RELIEF <= 0.5


def test_zooming_reads_from_a_smaller_part_of_the_source():
    picture = _picture(320, 180)
    depth = parallax.prepare(_ramp_depth(), picture.size)

    plain = np.asarray(parallax.warp(picture, depth, (0, 0), 1.0), dtype=np.float32)
    zoomed = np.asarray(parallax.warp(picture, depth, (0, 0), 1.3), dtype=np.float32)

    assert np.abs(plain - zoomed).mean() > 1.0
