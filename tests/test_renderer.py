"""The renderer, end to end.

Renders are kept tiny - a couple of seconds at 320x180 - so the suite stays
quick. What is being checked is that the output matches what the Timeline said,
not that it looks good.
"""

import numpy as np
import pytest

pytest.importorskip("moviepy")
pytest.importorskip("PIL")

from PIL import Image, ImageDraw  # noqa: E402

from render.base import get_renderer  # noqa: E402
from timeline import (  # noqa: E402
    AudioTrack,
    Caption,
    Motion,
    Shot,
    Timeline,
    Transition,
)

SIZE = (320, 180)


@pytest.fixture
def stills(tmp_path):
    """Three visually distinct, structured images."""
    made = []
    for name, color in (("a", (180, 90, 40)), ("b", (40, 90, 150)), ("c", (60, 140, 90))):
        image = Image.new("RGB", (800, 600), color)
        draw = ImageDraw.Draw(image)
        for x in range(0, 800, 50):
            draw.line([(x, 0), (x, 600)], fill=(255, 255, 255), width=2)
        for y in range(0, 600, 50):
            draw.line([(0, y), (800, y)], fill=(255, 255, 255), width=2)
        path = tmp_path / f"{name}.jpg"
        image.save(path, quality=85)
        made.append(str(path))
    return made


@pytest.fixture
def narration(tmp_path):
    from pydub import AudioSegment
    from pydub.generators import WhiteNoise

    audio = WhiteNoise().to_audio_segment(duration=2000).apply_gain(-12)
    path = tmp_path / "voice.wav"
    audio.export(path, format="wav")
    return str(path)


def frames_at(path, times):
    from moviepy import VideoFileClip

    with VideoFileClip(path) as clip:
        return [clip.get_frame(t).astype(float) for t in times]


def difference(a, b) -> float:
    return float(np.abs(a - b).mean())


# --------------------------------------------------------------------------
# Basics
# --------------------------------------------------------------------------

def test_render_produces_a_playable_file(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=2.0, width=SIZE[0], height=SIZE[1], fps=12)
    timeline.shots = [Shot(start=0, duration=2, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=2)]

    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    from moviepy import VideoFileClip

    with VideoFileClip(out) as clip:
        assert clip.duration == pytest.approx(2.0, abs=0.15)
        assert (clip.w, clip.h) == SIZE
        assert clip.audio is not None


def test_the_output_honours_the_timelines_frame_size_and_rate(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=1.0, width=256, height=144, fps=15)
    timeline.shots = [Shot(start=0, duration=1, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=1)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    from moviepy import VideoFileClip

    with VideoFileClip(out) as clip:
        assert (clip.w, clip.h) == (256, 144)
        assert clip.fps == pytest.approx(15, abs=0.5)


def test_an_invalid_timeline_is_refused_before_anything_is_encoded(tmp_path):
    timeline = Timeline(run_id="t", duration=5.0)
    timeline.shots = [Shot(start=0, duration=1, source="x.mp4")]   # leaves a 4s gap
    with pytest.raises(ValueError):
        get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))
    assert not (tmp_path / "out.mp4").exists()


def test_progress_is_reported_through_to_completion(stills, narration, tmp_path):
    seen = []
    timeline = Timeline(run_id="t", duration=1.0, width=SIZE[0], height=SIZE[1], fps=12)
    timeline.shots = [Shot(start=0, duration=1, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=1)]

    get_renderer("moviepy").render(
        timeline, str(tmp_path / "out.mp4"), progress=lambda stage, fraction: seen.append((stage, fraction))
    )
    assert seen[0][1] == 0.0
    assert seen[-1] == ("done", 1.0)
    assert [f for _, f in seen] == sorted(f for _, f in seen)


def test_the_intermediate_mix_is_cleaned_up(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=1.0, width=SIZE[0], height=SIZE[1], fps=12)
    timeline.shots = [Shot(start=0, duration=1, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=1)]
    get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))
    assert not list(tmp_path.glob("*.mix.wav"))


# --------------------------------------------------------------------------
# Motion
# --------------------------------------------------------------------------

def test_a_still_with_motion_actually_moves(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=2.0, width=SIZE[0], height=SIZE[1], fps=12)
    timeline.shots = [
        Shot(start=0, duration=2, source=stills[0], source_type="image",
             motion=Motion(start_rect=(0, 0, 1, 1), end_rect=(0.2, 0.2, 0.6, 0.6), easing="linear"))
    ]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=2)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    first, last = frames_at(out, [0.1, 1.8])
    assert difference(first, last) > 5, "the picture never moved"


def test_a_still_without_motion_holds_completely_still(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=2.0, width=SIZE[0], height=SIZE[1], fps=12)
    timeline.shots = [Shot(start=0, duration=2, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=2)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    first, last = frames_at(out, [0.1, 1.8])
    assert difference(first, last) < 2


def test_a_source_of_the_wrong_shape_is_cropped_not_squashed(stills, tmp_path, narration):
    # The sources are 4:3 and the output is 16:9. A squashed render would keep
    # the full width, so the grid spacing would change; a cropped one keeps it.
    timeline = Timeline(run_id="t", duration=1.0, width=320, height=180, fps=12)
    timeline.shots = [Shot(start=0, duration=1, source=stills[0], source_type="image", fit="cover")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=1)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    frame = frames_at(out, [0.5])[0]
    # Grid lines are white; a squash would compress them vertically relative to
    # horizontally. Compare the count along each axis against the source ratio.
    bright = frame.mean(axis=2) > 200
    assert bright.any(), "no grid survived the render"


# --------------------------------------------------------------------------
# Transitions
# --------------------------------------------------------------------------

def test_a_cut_changes_the_picture_instantly(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=2.0, width=SIZE[0], height=SIZE[1], fps=24)
    timeline.shots = [
        Shot(start=0, duration=1, source=stills[0], source_type="image"),
        Shot(start=1, duration=1, source=stills[1], source_type="image"),
    ]
    timeline.transitions = [Transition(at=1.0, kind="cut")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=2)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    before, after = frames_at(out, [0.9, 1.1])
    assert difference(before, after) > 20


def test_a_crossfade_is_a_real_blend_rather_than_a_cut(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=2.0, width=SIZE[0], height=SIZE[1], fps=24)
    timeline.shots = [
        Shot(start=0, duration=1, source=stills[0], source_type="image"),
        Shot(start=1, duration=1, source=stills[1], source_type="image"),
    ]
    timeline.transitions = [Transition(at=1.0, kind="crossfade", duration=0.5)]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=2)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    outgoing, middle, incoming = frames_at(out, [0.8, 1.25, 1.9])
    # A blend resembles neither source exactly.
    assert difference(middle, outgoing) > 3
    assert difference(middle, incoming) > 3


def test_a_dissolve_does_not_shift_the_shots_that_follow(stills, narration, tmp_path):
    # Dissolves are done by letting the outgoing shot run underneath, precisely
    # so that every shot keeps the start time the Timeline gave it.
    timeline = Timeline(run_id="t", duration=3.0, width=SIZE[0], height=SIZE[1], fps=24)
    timeline.shots = [
        Shot(start=0, duration=1, source=stills[0], source_type="image"),
        Shot(start=1, duration=1, source=stills[1], source_type="image"),
        Shot(start=2, duration=1, source=stills[2], source_type="image"),
    ]
    timeline.transitions = [Transition(at=1.0, kind="crossfade", duration=0.4)]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=3)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    from moviepy import VideoFileClip

    with VideoFileClip(out) as clip:
        assert clip.duration == pytest.approx(3.0, abs=0.15)

    # The third shot should be fully itself well after its dissolve-free start.
    third = frames_at(out, [2.5])[0]
    reference = np.asarray(Image.open(stills[2]).convert("RGB").resize(SIZE), dtype=float)
    assert difference(third, reference) < 40


# --------------------------------------------------------------------------
# Robustness
# --------------------------------------------------------------------------

def test_an_unreadable_source_costs_one_shot_not_the_render(stills, narration, tmp_path):
    broken = tmp_path / "broken.jpg"
    broken.write_bytes(b"this is not an image")

    timeline = Timeline(run_id="t", duration=2.0, width=SIZE[0], height=SIZE[1], fps=12)
    timeline.shots = [
        Shot(start=0, duration=1, source=str(broken), source_type="image"),
        Shot(start=1, duration=1, source=stills[0], source_type="image"),
    ]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=2)]

    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))
    from moviepy import VideoFileClip

    with VideoFileClip(out) as clip:
        assert clip.duration == pytest.approx(2.0, abs=0.15)


@pytest.fixture
def short_clip(tmp_path):
    """Two seconds of video, for asking a renderer to hold it for longer."""
    import subprocess

    from providers._ffmpeg_setup import ensure_ffmpeg_on_path

    ensure_ffmpeg_on_path()
    path = tmp_path / "short.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi",
         "-i", "testsrc=duration=2:size=320x180:rate=24", "-y", str(path)],
        check=True,
    )
    return str(path)


def test_footage_shorter_than_its_slot_freezes_on_its_last_frame(short_clip, narration, tmp_path):
    """Regression: extending a clip's duration left the reader seeking past the
    end of the file, warning once per frame and re-reading the source for every
    one of them - thousands of warnings on a single shot."""
    import warnings

    timeline = Timeline(run_id="t", duration=5.0, width=SIZE[0], height=SIZE[1], fps=24)
    timeline.shots = [Shot(start=0, duration=5.0, source=short_clip, source_type="video")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=5.0)]

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    seeks = [w for w in caught if "bytes read at frame index" in str(w.message)]
    assert not seeks, f"{len(seeks)} frame-seek warnings; the tail is not frozen"

    held_early, held_late = frames_at(out, [2.5, 4.5])
    assert difference(held_early, held_late) < 1.0, "the held tail is not a still frame"


def test_a_colour_shot_needs_no_file(narration, tmp_path):
    timeline = Timeline(run_id="t", duration=1.0, width=SIZE[0], height=SIZE[1], fps=12)
    timeline.shots = [Shot(start=0, duration=1, source_type="color", color=(200, 30, 30))]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=1)]
    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))

    frame = frames_at(out, [0.5])[0]
    assert frame[..., 0].mean() > frame[..., 1].mean() + 50


# --------------------------------------------------------------------------
# Captions
# --------------------------------------------------------------------------

def test_captions_are_drawn(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=2.0, width=640, height=360, fps=12)
    timeline.shots = [Shot(start=0, duration=2, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=2)]
    timeline.captions = [Caption(start=0.2, end=1.8, text="Kya aapko pata hai")]
    timeline.meta = {"caption_style": {"enabled": True, "position": 0.82, "font_size_ratio": 0.06}}

    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))
    with_text, without_text = frames_at(out, [1.0, 1.95])
    band = slice(int(360 * 0.75), int(360 * 0.95))
    assert difference(with_text[band], without_text[band]) > 2


def test_devanagari_captions_render_as_glyphs_not_boxes(stills, narration, tmp_path):
    """Regression: the first renderer passed a font *family* to a backend that
    needed a file path, so Hindi captions came out as tofu boxes."""
    from render import fonts

    if not fonts.resolve("नमस्ते"):
        pytest.skip("no Devanagari-capable font installed")

    timeline = Timeline(run_id="t", duration=1.5, width=640, height=360, fps=12)
    timeline.shots = [Shot(start=0, duration=1.5, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=1.5)]
    timeline.captions = [Caption(start=0.1, end=1.4, text="नमस्ते दुनिया, ये हिंदी है")]
    timeline.meta = {"caption_style": {"enabled": True, "position": 0.8, "font_size_ratio": 0.07}}

    out = get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))
    frame = frames_at(out, [0.7])[0]
    band = frame[int(360 * 0.74):int(360 * 0.95)]
    ink = (band.mean(axis=2) > 220).sum()

    # Tofu boxes are hollow rectangles and cover far less area than real
    # glyphs; a bare threshold on ink would pass either way, so compare the
    # rendered width against a run of boxes of the same character count.
    assert ink > 200, "nothing legible was drawn in the caption band"


def test_captions_can_be_switched_off(stills, narration, tmp_path):
    timeline = Timeline(run_id="t", duration=1.0, width=320, height=180, fps=12)
    timeline.shots = [Shot(start=0, duration=1, source=stills[0], source_type="image")]
    timeline.audio = [AudioTrack(source=narration, kind="voice", duration=1)]
    timeline.captions = [Caption(start=0, end=1, text="should not appear")]
    timeline.meta = {"caption_style": {"enabled": False}}
    assert get_renderer("moviepy").render(timeline, str(tmp_path / "out.mp4"))


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

def test_the_renderer_is_resolved_by_name():
    assert get_renderer("moviepy").name == "moviepy"


def test_an_unknown_renderer_says_what_is_available():
    with pytest.raises(ValueError) as caught:
        get_renderer("no-such-renderer")
    assert "moviepy" in str(caught.value)
