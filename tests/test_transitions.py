"""Whip and speed ramp, which used to be dissolves wearing their names.

The Timeline has had five transition kinds since Phase 2 and the renderer
implemented three: `whip` and `speed_ramp` both fell through to a crossfade,
so a style profile weighting whips at a quarter of its cuts produced a video
of dissolves. These cover what each one now actually does to the picture.
"""

import numpy as np
import pytest

pytest.importorskip("moviepy")

from moviepy import ImageClip

import render.moviepy_renderer as renderer


def _striped(width=640, height=360):
    """Vertical stripes: a horizontal smear is unmistakable on them."""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, ::16] = 255
    frame[:, 1::16] = 255
    return frame


def _clip(duration=2.0):
    return ImageClip(_striped()).with_duration(duration)


def _picture_contrast(frame):
    """Sharpness measured inside the frame, away from the shifted edge."""
    return float(frame[:, 300:600, 0].std())


# ---- whip ------------------------------------------------------------------


def test_a_whip_starts_smeared_and_ends_sharp():
    whipped = renderer._whip_in(_clip(), 0.4)

    assert _picture_contrast(whipped.get_frame(0.0)) < 20
    assert _picture_contrast(whipped.get_frame(0.4)) == pytest.approx(
        _picture_contrast(_striped()), abs=0.5
    )


def test_a_whip_settles_rather_than_sliding_at_one_speed():
    whipped = renderer._whip_in(_clip(), 0.4)
    contrasts = [_picture_contrast(whipped.get_frame(t)) for t in (0.0, 0.1, 0.2, 0.3)]

    assert contrasts == sorted(contrasts), "the smear did not clear monotonically"


def test_a_whip_leaves_the_shot_alone_once_it_is_over():
    whipped = renderer._whip_in(_clip(), 0.4)

    assert np.array_equal(whipped.get_frame(1.0), _striped())


def test_a_whip_of_no_length_changes_nothing():
    clip = _clip()

    assert renderer._whip_in(clip, 0.0) is clip


def test_the_smear_is_a_smear_and_not_a_row_of_ghosts():
    """Copies fixed at eight read as eight ghosts across a hard whip, which is
    worse than no effect. The count follows the width."""
    heavy = renderer._directional_blur(_striped(), 60)

    assert _picture_contrast(heavy) < 15


def test_a_blur_too_small_to_see_is_not_computed():
    frame = _striped()

    assert renderer._directional_blur(frame, 1) is frame


# ---- how the frame is moved ------------------------------------------------


def test_shifting_does_not_wrap_the_far_edge_into_view():
    """A wrapped edge reads as a seam tearing across the picture."""
    frame = np.tile(np.arange(64, dtype=np.uint8).reshape(1, 64, 1), (8, 1, 3))
    shifted = renderer._shift(frame, 10)

    assert (shifted[:, :10] == frame[0, 0, 0]).all(), "the right edge wrapped round"
    assert np.array_equal(shifted[:, 10:], frame[:, :54])


def test_shifting_the_other_way_holds_the_other_edge():
    frame = np.tile(np.arange(64, dtype=np.uint8).reshape(1, 64, 1), (8, 1, 3))
    shifted = renderer._shift(frame, -10)

    assert (shifted[:, -10:] == frame[0, -1, 0]).all()


def test_shifting_by_nothing_returns_the_same_frame():
    frame = _striped()

    assert renderer._shift(frame, 0) is frame


# ---- speed ramp ------------------------------------------------------------


def _clock(duration=4.0):
    """A clip whose picture encodes the source time it was read from.

    A static ImageClip will not do: MoviePy never calls a time function for
    one, so a retime applied to it is invisible to the test as well as to the
    viewer.
    """
    from moviepy import VideoClip

    def frame(t):
        return np.full((8, 8, 3), min(255, int(round(float(t) * 50))), dtype=np.uint8)

    return VideoClip(frame_function=frame, duration=duration)


def _source_time(clip, t):
    return float(clip.get_frame(t)[0, 0, 0]) / 50.0


def test_a_ramp_opens_further_ahead_in_the_shot_than_the_clock():
    """A speed ramp is retiming: it opens fast and decelerates to real time."""
    ramped = renderer._ramp_in(_clock(), 0.5)

    assert _source_time(ramped, 0.0) > 0.05, "the ramp opened at real time"


def test_a_ramp_is_back_in_step_by_the_time_it_ends():
    ramped = renderer._ramp_in(_clock(), 0.5)

    assert _source_time(ramped, 1.5) == pytest.approx(1.5, abs=0.05)


def test_a_ramp_slows_down_rather_than_jumping_back_into_step():
    ramped = renderer._ramp_in(_clock(), 0.5)
    ahead = [_source_time(ramped, t) - t for t in (0.0, 0.1, 0.2, 0.3, 0.4)]

    assert ahead == sorted(ahead, reverse=True), "the retime did not decelerate"
    assert all(value >= -0.05 for value in ahead)


def test_a_ramp_never_reads_past_the_end_of_its_shot():
    clip = _clock(1.0)
    ramped = renderer._ramp_in(clip, 0.5)

    for t in (0.0, 0.2, 0.6, 0.99):
        assert _source_time(ramped, t) <= 1.0 + 1e-6


def test_a_ramp_of_no_length_changes_nothing():
    clip = _clip()

    assert renderer._ramp_in(clip, 0.0) is clip


# ---- counters that count ---------------------------------------------------

class _Piece:
    """Stands in for a rendered text bitmap, remembering what it was asked to draw."""

    def __init__(self, text):
        self.text = text
        self.duration = 0.0

    def with_duration(self, duration):
        self.duration = duration
        return self


def _drawn(overlay):
    """The sequence of strings a counting overlay would render."""
    seen = []

    def draw(text):
        seen.append(text)
        return _Piece(text)

    import moviepy

    original = renderer.concatenate_videoclips if hasattr(renderer, "concatenate_videoclips") else None
    result = None
    try:
        # concatenate is imported inside the function; patch it at source.
        real = moviepy.concatenate_videoclips
        moviepy.concatenate_videoclips = lambda clips, method=None: clips
        result = renderer._counting_clip(draw, overlay)
    finally:
        moviepy.concatenate_videoclips = real
        if original is not None:
            renderer.concatenate_videoclips = original
    return seen, result


def _overlay(text, data, duration=2.0):
    from timeline import Overlay

    return Overlay(start=0.0, duration=duration, kind="counter", text=text, data=data)


def test_a_quantity_counts_up_to_its_figure():
    seen, clips = _drawn(_overlay("45,000", {"to": "45,000", "from": "0"}))

    assert clips, "nothing was rendered"
    assert seen[0] != "45,000", "the counter opened on its answer"
    assert seen[-1] == "45,000"


def test_the_figure_is_spelled_exactly_as_it_was_written():
    """Not re-formatted: the last frame has to match the word on screen."""
    seen, _ = _drawn(_overlay("2,000", {"to": "2,000", "from": "0"}))

    assert seen[-1] == "2,000"


def test_the_words_around_the_number_are_kept_at_every_step():
    seen, _ = _drawn(_overlay("45 tonnes", {"to": "45 tonnes", "from": "0"}))

    assert all(step.endswith(" tonnes") for step in seen)
    assert seen[-1] == "45 tonnes"


def test_the_count_decelerates_onto_its_figure():
    seen, _ = _drawn(_overlay("1000", {"to": "1000", "from": "0"}))
    values = [int(step.replace(",", "")) for step in seen]
    steps = [b - a for a, b in zip(values, values[1:])]

    assert values == sorted(values)
    assert steps[0] > steps[-1], "the count did not slow down"


def test_an_overlay_with_no_starting_value_is_drawn_as_it_is():
    """A year is a counter that does not count."""
    seen, clips = _drawn(_overlay("1902", {"to": "1902"}))

    assert clips is None and seen == []


def test_something_with_no_digits_in_it_is_not_counted():
    seen, clips = _drawn(_overlay("Kolar", {"to": "Kolar", "from": "0"}))

    assert clips is None and seen == []


def test_a_counter_already_at_its_figure_is_not_animated():
    seen, clips = _drawn(_overlay("0", {"to": "0", "from": "0"}))

    assert clips is None and seen == []


# ---- where a full-frame overlay lands --------------------------------------

def test_a_chart_is_drawn_where_it_was_built_not_halfway_down_the_frame(tmp_path):
    """with_position sets the top-left corner, so asking for the middle of the
    frame put a full-height chart's top edge halfway down it and pushed the
    bars off the bottom of the screen.

    Measured on the bars rather than on brightness: the shot underneath is not
    black, so both halves of a wrongly placed frame still carry colour and the
    mistake averages away. Placed correctly the bars run from row 86 to 133 of
    180; placed wrongly, from 176 to 179.
    """
    from render.base import get_renderer
    from timeline import Overlay, Shot, Timeline

    width, height = 320, 180
    timeline = Timeline(
        run_id="chart", width=width, height=height, fps=10, duration=1.5,
        shots=[Shot(start=0.0, duration=1.5, source_type="color")],
        overlays=[Overlay(
            start=0.0, duration=1.5, kind="chart", position=(0.5, 0.5), anchor="center",
            animate_in="none", animate_out="none",
            data={"series": [["Cost", 500.0, "usd/oz"], ["Price", 350.0, "usd/oz"]],
                  "title": "Compared"},
        )],
    )
    assert timeline.problems() == []

    out = tmp_path / "chart.mp4"
    get_renderer("moviepy").render(timeline, str(out))

    from moviepy import VideoFileClip

    with VideoFileClip(str(out)) as clip:
        frame = np.asarray(clip.get_frame(1.0), dtype=np.float32)

    red, green, blue = frame[:, :, 0], frame[:, :, 1], frame[:, :, 2]
    bars = (red > 150) & (green > 80) & (green < 190) & (blue < 110)
    rows = np.where(bars.any(axis=1))[0]

    assert rows.size, "no chart bars were drawn at all"
    assert rows.min() < height * 0.6, "the chart starts below the middle of the frame"
    assert rows.max() < height - 2, "the chart runs off the bottom of the frame"
    assert rows.size > height * 0.1, "only a sliver of the chart is on screen"
