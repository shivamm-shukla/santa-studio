"""Ken Burns geometry.

A motion bug is otherwise only visible by watching the output, which is a slow
and unreliable way to find out that every still has been drifting off the edge
of its own frame.
"""

import random

import pytest

import style_profile as sp
from render import motion as m
from timeline import Motion


# --------------------------------------------------------------------------
# Easing
# --------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["linear", "ease_in", "ease_out", "ease_in_out"])
def test_easing_starts_at_zero_and_ends_at_one(kind):
    assert m.ease(0.0, kind) == pytest.approx(0.0)
    assert m.ease(1.0, kind) == pytest.approx(1.0)


@pytest.mark.parametrize("kind", ["linear", "ease_in", "ease_out", "ease_in_out"])
def test_easing_never_goes_backwards(kind):
    values = [m.ease(i / 20, kind) for i in range(21)]
    assert values == sorted(values)


def test_easing_clamps_outside_its_range():
    assert m.ease(-1.0) == 0.0
    assert m.ease(2.0) == 1.0


def test_ease_in_out_is_slower_at_the_edges_than_linear():
    # This is what makes a move read as a camera rather than a slider.
    assert m.ease(0.1, "ease_in_out") < m.ease(0.1, "linear")
    assert m.ease(0.9, "ease_in_out") > m.ease(0.9, "linear")


# --------------------------------------------------------------------------
# Fitting
# --------------------------------------------------------------------------

def test_cover_box_matches_the_output_aspect_ratio():
    left, upper, right, lower = m.cover_box((1600, 1200), (1920, 1080))
    assert (right - left) / (lower - upper) == pytest.approx(16 / 9, abs=0.01)


def test_cover_box_is_centred():
    left, upper, right, lower = m.cover_box((1600, 1200), (1920, 1080))
    assert left == 1600 - right
    assert upper == 1200 - lower


def test_cover_trims_the_sides_of_a_wide_source():
    left, upper, right, lower = m.cover_box((3000, 1000), (1000, 1000))
    assert lower - upper == 1000        # full height kept
    assert right - left == 1000         # sides trimmed


def test_cover_trims_the_top_and_bottom_of_a_tall_source():
    left, upper, right, lower = m.cover_box((1000, 3000), (1000, 1000))
    assert right - left == 1000
    assert lower - upper == 1000


def test_a_matching_aspect_ratio_is_left_alone():
    assert m.cover_box((1920, 1080), (1280, 720)) == (0, 0, 1920, 1080)


def test_a_source_with_no_size_is_rejected():
    with pytest.raises(ValueError):
        m.cover_box((0, 100), (16, 9))


# --------------------------------------------------------------------------
# crop_box
# --------------------------------------------------------------------------

def test_no_motion_gives_the_plain_fit_box():
    source, output = (1600, 1200), (1920, 1080)
    assert m.crop_box(source, output) == m.cover_box(source, output)


def test_a_static_motion_gives_the_plain_fit_box():
    static = Motion(start_rect=(0.1, 0.1, 0.5, 0.5), end_rect=(0.1, 0.1, 0.5, 0.5))
    source, output = (1600, 1200), (1920, 1080)
    assert m.crop_box(source, output, static, 0.5) == m.cover_box(source, output)


def test_a_push_in_ends_tighter_than_it_starts():
    push = Motion(start_rect=(0, 0, 1, 1), end_rect=(0.1, 0.1, 0.8, 0.8), easing="linear")
    source, output = (1920, 1080), (1920, 1080)
    start = m.crop_box(source, output, push, 0.0)
    end = m.crop_box(source, output, push, 1.0)
    assert (end[2] - end[0]) < (start[2] - start[0])


def test_the_move_is_continuous():
    push = Motion(start_rect=(0, 0, 1, 1), end_rect=(0.2, 0.2, 0.6, 0.6), easing="linear")
    widths = [
        m.crop_box((1920, 1080), (1920, 1080), push, i / 20)[2]
        - m.crop_box((1920, 1080), (1920, 1080), push, i / 20)[0]
        for i in range(21)
    ]
    assert widths == sorted(widths, reverse=True)


@pytest.mark.parametrize("source", [(1920, 1080), (1600, 1200), (800, 2000), (4000, 900)])
@pytest.mark.parametrize("progress", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_a_crop_box_never_leaves_the_source(source, progress):
    # Rounding at the end of a move can push a box past the edge, and Pillow
    # will quietly return a black border rather than complain.
    move = Motion(start_rect=(0, 0, 1, 1), end_rect=(0.25, 0.25, 0.75, 0.75))
    left, upper, right, lower = m.crop_box(source, (1920, 1080), move, progress)
    assert 0 <= left < right <= source[0]
    assert 0 <= upper < lower <= source[1]


def test_a_crop_box_is_always_at_least_one_pixel():
    tiny = Motion(start_rect=(0, 0, 1, 1), end_rect=(0.0, 0.0, 0.0001, 0.0001))
    left, upper, right, lower = m.crop_box((100, 100), (100, 100), tiny, 1.0)
    assert right > left and lower > upper


def test_motion_stays_inside_the_fit_box_not_the_raw_source():
    # Applying the move before fitting lets a pan wander onto the letterbox.
    source = (4000, 1000)          # very wide
    output = (1000, 1000)          # square
    fit = m.cover_box(source, output)
    pan = Motion(start_rect=(0, 0, 0.5, 0.5), end_rect=(0.5, 0.5, 0.5, 0.5), easing="linear")
    for progress in (0.0, 0.5, 1.0):
        left, upper, right, lower = m.crop_box(source, output, pan, progress)
        assert left >= fit[0] and right <= fit[2]


# --------------------------------------------------------------------------
# Generated moves
# --------------------------------------------------------------------------

@pytest.mark.parametrize("preset", list(sp.PRESETS))
def test_generated_moves_are_always_renderable(preset):
    style = sp.load(preset).motion
    rng = random.Random(11)
    for _ in range(200):
        move = m.build_motion(style, rng)
        assert move.problems("m") == [], move


def test_generated_moves_actually_move():
    style = sp.load("documentary").motion
    rng = random.Random(3)
    moves = [m.build_motion(style, rng) for _ in range(50)]
    assert not any(move.is_static for move in moves)


def test_moves_go_in_more_than_one_direction():
    # A run of stills all drifting the same way is its own kind of obviously
    # generated.
    style = sp.load("documentary").motion
    rng = random.Random(5)
    moves = [m.build_motion(style, rng) for _ in range(40)]
    pushes = sum(1 for move in moves if move.start_rect == (0.0, 0.0, 1.0, 1.0))
    assert 0 < pushes < len(moves), "every move went the same way"


def test_intensity_scales_how_far_a_move_travels():
    rng_seed = 21
    gentle = sp.MotionStyle(intensity=0.15, max_zoom=0.3, max_pan=0.2)
    strong = sp.MotionStyle(intensity=1.0, max_zoom=0.3, max_pan=0.2)

    def average_zoom(style):
        rng = random.Random(rng_seed)
        moves = [m.build_motion(style, rng) for _ in range(60)]
        return sum(min(mv.start_rect[2], mv.end_rect[2]) for mv in moves) / len(moves)

    # A tighter rectangle means a bigger push, so lower is stronger.
    assert average_zoom(strong) < average_zoom(gentle)


def test_a_calm_profile_moves_less_than_a_fast_one():
    def average_zoom(preset):
        style = sp.load(preset).motion
        rng = random.Random(9)
        moves = [m.build_motion(style, rng) for _ in range(60)]
        return sum(min(mv.start_rect[2], mv.end_rect[2]) for mv in moves) / len(moves)

    assert average_zoom("calm-narrative") > average_zoom("fast-explainer")
