"""Text drawn into a frame has to include the parts below the baseline.

Asked for a height of None, the drawing backend returns a bitmap that ends on
the last inked row, so p, y, g and j were sliced off flush. It is not a
subtle defect: "saump diya" rendered as "saumo diva", which is a different
sentence to anyone reading it.
"""

import numpy as np
import pytest

pytest.importorskip("moviepy")

from render import fonts  # noqa: E402
from render.moviepy_renderer import MoviePyRenderer, _text_margin  # noqa: E402

DESCENDERS = "BGML ko saump diya gaya"


def _ink_rows(clip):
    """First and last row of the clip that has anything drawn on it."""
    frame = clip.get_frame(0)
    mask = clip.mask.get_frame(0) if clip.mask is not None else (frame.sum(axis=2) > 10)
    rows = np.where(mask.max(axis=1) > 0.05)[0]
    return frame.shape[0], int(rows.min()), int(rows.max())


def test_descenders_are_not_cut_off():
    clip = MoviePyRenderer()._text_clip(
        DESCENDERS, (1920, 1080), 48, "#FFFFFF", "black", 3
    )
    assert clip is not None
    height, _, last_inked = _ink_rows(clip)
    assert last_inked < height - 1, (
        "text runs to the final row of its own bitmap, so anything below the "
        "baseline is clipped"
    )


def test_text_without_descenders_is_unaffected():
    clip = MoviePyRenderer()._text_clip(
        "KOLAR MINE", (1920, 1080), 48, "#FFFFFF", "black", 3
    )
    height, _, last_inked = _ink_rows(clip)
    assert last_inked < height - 1


def test_the_margin_scales_with_the_type_size():
    """The same renderer draws a small caption and a large overlay."""
    assert _text_margin(90) > _text_margin(30)
    assert _text_margin(1) >= 6


def test_the_stroke_widens_the_glyph_so_it_widens_the_margin():
    assert _text_margin(48, stroke_width=6) > _text_margin(48, stroke_width=0)


def test_devanagari_matras_are_not_cut_off():
    """Hindi sits below the baseline too, and further down than Latin does."""
    clip = MoviePyRenderer()._text_clip(
        "कोलार गोल्ड फील्ड्स बंद हुई", (1920, 1080), 48, "#FFFFFF", "black", 3
    )
    assert clip is not None
    height, _, last_inked = _ink_rows(clip)
    assert last_inked < height - 1


def test_a_caption_keeps_its_place_on_screen():
    """The margin is added above the text as well as below it.

    Left uncompensated, every caption drifts down the frame by that much,
    which on a 9:16 crop pushes it under the platform's own UI.
    """
    size = (1920, 1080)
    style = {"position": 0.82, "font_size_ratio": 0.045}

    class OneCaption:
        captions = [type("C", (), {"text": DESCENDERS, "start": 0.0, "end": 1.0})()]

    clips = MoviePyRenderer()._caption_clips(OneCaption(), size, style)
    assert clips, "the caption was dropped"

    font_size = max(12, int(size[1] * style["font_size_ratio"]))
    top = clips[0].pos(0)[1]
    assert top == int(size[1] * style["position"]) - _text_margin(font_size, 3)
