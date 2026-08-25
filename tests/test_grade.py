"""One look over every shot, whatever it was cut from.

A finished run cuts a Pexels clip against a generated still against a Commons
photograph. Each arrives with its own colour, contrast and grain, so the
picture changes character at every cut - which is what makes an edit feel
assembled out of parts rather than filmed. The grade exists to stop that, and
it only works if it reaches *every* frame, which is why it is applied by the
encoder rather than to the assets.
"""

import numpy as np
import pytest

pytest.importorskip("moviepy")

from PIL import Image, ImageDraw

from render import grade
from render.base import get_renderer
from timeline import Shot, Timeline


@pytest.fixture
def still(tmp_path):
    """A structured picture, so a grade has something to act on."""
    image = Image.new("RGB", (800, 600), (150, 90, 60))
    draw = ImageDraw.Draw(image)
    for x in range(0, 800, 40):
        draw.line([(x, 0), (x, 600)], fill=(20, 20, 24), width=3)
    path = tmp_path / "still.jpg"
    image.save(path)
    return str(path)


# ---- what the look is ------------------------------------------------------


def test_the_blacks_are_lifted_off_zero():
    """Digital black at zero is most of what separates footage that looks
    rendered from footage that looks photographed."""
    assert "curves" in grade.filter_chain()
    assert grade.CURVES.startswith("0/0.0"), "the curve starts at pure black"
    assert float(grade.CURVES.split("/")[1].split()[0]) > 0


def test_the_grain_moves():
    """Static grain reads as dirt on the lens rather than as film."""
    assert "allf=t" in grade.filter_chain()


def test_the_look_is_gentle():
    """Here to make sources agree with each other, not to impose a style."""
    assert 0.85 <= grade.SATURATION <= 1.0
    assert grade.GRAIN <= 12, "past this it reads as a damaged tape"


def test_the_lift_is_the_last_thing_applied():
    """Everything else can undo it. `eq` round-trips through limited-range
    YUV where black is 16 rather than 0, and the vignette multiplies whatever
    is left towards nothing at the corners; in the obvious order a black frame
    came out at 0.2 where the curve asked for 8."""
    chain = grade.filter_chain()

    assert chain.rindex("curves") > chain.rindex("vignette")
    assert chain.rindex("curves") > chain.rindex("eq=")
    assert chain.rindex("curves") > chain.rindex("noise")


def test_the_grade_has_no_contrast_term_of_its_own():
    """eq's contrast is computed about mid-grey, so on limited-range black it
    pushes below the floor and clips. The S it provided is in the curve."""
    assert "contrast" not in grade.filter_chain()


def test_it_is_handed_to_the_encoder_as_a_filter():
    params = grade.ffmpeg_params()

    assert params[0] == "-vf"
    assert params[1] == grade.filter_chain()


# ---- that it actually reaches the picture ----------------------------------


def _render(tmp_path, shots, size=(320, 180), duration=1.5):
    timeline = Timeline(
        run_id="grade", width=size[0], height=size[1], fps=10, duration=duration,
        shots=shots,
    )
    assert timeline.problems() == []
    out = tmp_path / "graded.mp4"
    get_renderer("moviepy").render(timeline, str(out))
    return out


def _frame(path, at):
    from moviepy import VideoFileClip

    with VideoFileClip(str(path)) as clip:
        return np.asarray(clip.get_frame(at), dtype=np.float32)


def test_a_black_shot_does_not_come_out_pure_black(tmp_path):
    """The clearest sign the grade reached the picture at all."""
    out = _render(tmp_path, [Shot(start=0.0, duration=1.5, source_type="color",
                                  color=(0, 0, 0))])

    frame = _frame(out, 0.8)
    assert frame.mean() > 1.5, "the shot is still pure black; the grade never ran"


def test_the_grain_is_different_from_one_frame_to_the_next(tmp_path):
    out = _render(tmp_path, [Shot(start=0.0, duration=1.5, source_type="color",
                                  color=(40, 40, 44))])

    first, second = _frame(out, 0.5), _frame(out, 0.6)
    assert np.abs(first - second).mean() > 0.3, "every frame carries the same grain"


def test_every_shot_gets_it_and_not_just_the_first(tmp_path, still):
    """The whole point: a generated still and a stock clip end up in the same
    film rather than looking like two different ones."""
    out = _render(
        tmp_path,
        [
            Shot(start=0.0, duration=1.0, source=still, source_type="image"),
            Shot(start=1.0, duration=1.0, source_type="color", color=(0, 0, 0)),
        ],
        duration=2.0,
    )

    assert _frame(out, 1.5).mean() > 1.5, "the second shot was left ungraded"
