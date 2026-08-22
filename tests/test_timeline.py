"""The edit decision list: automation, validation, and round-tripping.

These are the assertions the Timeline exists to make possible. Before it, none
of this could be checked without rendering a file and watching it.
"""

import pytest

from timeline import (
    AudioTrack,
    Caption,
    GainPoint,
    Motion,
    Shot,
    Timeline,
    Transition,
    Word,
)


def a_valid_timeline() -> Timeline:
    timeline = Timeline(run_id="test", duration=12.0)
    timeline.shots = [
        Shot(start=0, duration=4, source="a.mp4", scene_index=0),
        Shot(start=4, duration=4, source="b.jpg", source_type="image", scene_index=0,
             motion=Motion(start_rect=(0, 0, 1, 1), end_rect=(0.1, 0.1, 0.8, 0.8))),
        Shot(start=8, duration=4, source="c.mp4", scene_index=1),
    ]
    timeline.audio = [AudioTrack(source="voice.wav", kind="voice", duration=12)]
    return timeline


# --------------------------------------------------------------------------
# Gain automation - the reason this schema exists
# --------------------------------------------------------------------------

def test_gain_interpolates_between_points():
    track = AudioTrack(
        source="bed.mp3",
        gain=[GainPoint(0, -12), GainPoint(4, -24)],
    )
    assert track.gain_at(0) == pytest.approx(-12)
    assert track.gain_at(2) == pytest.approx(-18)
    assert track.gain_at(4) == pytest.approx(-24)


def test_gain_holds_at_the_nearest_point_outside_its_range():
    # A curve should not have to span the whole track to be usable.
    track = AudioTrack(source="bed.mp3", gain=[GainPoint(2, -6), GainPoint(4, -20)])
    assert track.gain_at(0) == pytest.approx(-6)
    assert track.gain_at(99) == pytest.approx(-20)


def test_a_track_with_no_curve_is_unity():
    assert AudioTrack(source="bed.mp3").gain_at(5) == 0.0


def test_a_bed_can_duck_and_recover_across_one_video():
    # The whole of the old sound design was a single constant applied to the
    # entire video. This is the thing that replaces it.
    bed = AudioTrack(
        source="bed.mp3", kind="music",
        gain=[GainPoint(0, -12), GainPoint(3, -6), GainPoint(4, -24),
              GainPoint(10, -24), GainPoint(12, -9)],
    )
    assert bed.gain_at(3) > bed.gain_at(0)      # swells into the reveal
    assert bed.gain_at(7) < bed.gain_at(3)      # pulls back under narration
    assert bed.gain_at(12) > bed.gain_at(7)     # recovers at the tail
    assert len({round(bed.gain_at(t), 2) for t in (0, 3, 7, 12)}) == 4


def test_gain_points_out_of_order_still_interpolate():
    track = AudioTrack(source="x.mp3", gain=[GainPoint(4, -24), GainPoint(0, -12)])
    assert track.gain_at(2) == pytest.approx(-18)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------

def test_a_well_formed_timeline_has_no_problems():
    assert a_valid_timeline().problems() == []


def test_gaps_between_shots_are_caught():
    # A gap renders as a black flash, which is easy to produce by accident when
    # durations come from estimated timings.
    timeline = a_valid_timeline()
    timeline.shots[1].start = 5
    problems = " ".join(timeline.problems())
    assert "gap" in problems


def test_overlapping_shots_are_caught():
    timeline = a_valid_timeline()
    timeline.shots[2].start = 6
    assert any("overlap" in p for p in timeline.problems())


def test_picture_shorter_than_the_declared_duration_is_caught():
    timeline = a_valid_timeline()
    timeline.duration = 20
    assert any("before the declared duration" in p for p in timeline.problems())


def test_a_shot_needs_something_to_show():
    timeline = a_valid_timeline()
    timeline.shots[0].source = ""
    assert any("needs a source path" in p for p in timeline.problems())


def test_a_colour_shot_needs_no_source():
    timeline = a_valid_timeline()
    timeline.shots[0].source = ""
    timeline.shots[0].source_type = "color"
    assert timeline.problems() == []


def test_only_one_voice_track_is_allowed():
    timeline = a_valid_timeline()
    timeline.audio.append(AudioTrack(source="second.wav", kind="voice"))
    assert any("voice tracks" in p for p in timeline.problems())


def test_a_motion_rect_may_not_leave_the_frame():
    motion = Motion(start_rect=(0.5, 0.5, 0.9, 0.9))
    assert any("past the frame edge" in p for p in motion.problems("m"))


def test_a_cut_may_not_have_a_duration():
    assert any("instantaneous" in p for p in Transition(at=1, kind="cut", duration=0.5).problems(0))


def test_a_crossfade_must_have_a_duration():
    assert any("positive duration" in p for p in Transition(at=1, kind="crossfade").problems(0))


def test_emphasis_must_point_at_a_real_word():
    caption = Caption(start=0, end=1, text="hi there",
                      words=[Word("hi", 0, 0.5), Word("there", 0.5, 1)], emphasis=[5])
    assert any("no matching word" in p for p in caption.problems(0))


def test_validate_reports_every_problem_at_once():
    # Fixing one error only to be handed the next is a miserable way to debug a
    # generated document.
    timeline = Timeline(run_id="x", duration=10)
    timeline.shots = [Shot(start=0, duration=3, source="a.mp4"),
                      Shot(start=5, duration=2, source="")]
    with pytest.raises(ValueError) as caught:
        timeline.validate()
    assert str(caught.value).count("\n  - ") >= 3


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------

def test_round_trip_preserves_the_document(tmp_path):
    timeline = a_valid_timeline()
    timeline.captions = [Caption(start=0, end=2, text="Kya aapko pata hai",
                                 words=[Word("Kya", 0, 0.5), Word("hai", 0.5, 2)],
                                 emphasis=[0])]
    timeline.audio.append(AudioTrack(source="bed.mp3", kind="music",
                                     gain=[GainPoint(0, -12), GainPoint(6, -24)]))
    timeline.transitions = [Transition(at=4, kind="crossfade", duration=0.4)]

    path = tmp_path / "timeline.json"
    timeline.save(path)
    loaded = Timeline.load(path)
    assert loaded.to_dict() == timeline.to_dict()


def test_round_trip_rehydrates_nested_types(tmp_path):
    # JSON has no tuple type and no notion of our dataclasses; a renderer
    # reading a loaded timeline must not have to care where it came from.
    timeline = a_valid_timeline()
    timeline.audio.append(AudioTrack(source="bed.mp3", kind="music", gain=[GainPoint(0, -12)]))
    timeline.captions = [Caption(start=0, end=1, text="x", words=[Word("x", 0, 1)])]
    path = tmp_path / "timeline.json"
    timeline.save(path)
    loaded = Timeline.load(path)

    assert isinstance(loaded.shots[1].motion, Motion)
    assert isinstance(loaded.shots[1].motion.start_rect, tuple)
    assert isinstance(loaded.audio[1].gain[0], GainPoint)
    assert isinstance(loaded.captions[0].words[0], Word)
    assert loaded.audio[1].gain_at(0) == -12


def test_an_unknown_field_does_not_make_a_project_unopenable(tmp_path):
    import json

    timeline = a_valid_timeline()
    payload = timeline.to_dict()
    payload["something_a_later_build_added"] = True
    payload["shots"][0]["also_new"] = 1
    path = tmp_path / "timeline.json"
    path.write_text(json.dumps(payload))

    loaded = Timeline.load(path)
    assert len(loaded.shots) == 3


def test_save_is_atomic(tmp_path):
    path = tmp_path / "timeline.json"
    a_valid_timeline().save(path)
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp.*")), "a temp file was left behind"


# --------------------------------------------------------------------------
# Derived values
# --------------------------------------------------------------------------

def test_cut_rhythm_can_be_read_back_off_a_timeline():
    # Style profiles are written in cuts-per-minute, so a finished timeline has
    # to be measurable in the same unit.
    assert a_valid_timeline().cuts_per_minute() == pytest.approx(15.0)


def test_shots_can_be_grouped_by_script_scene():
    timeline = a_valid_timeline()
    assert len(timeline.shots_in_scene(0)) == 2
    assert len(timeline.shots_in_scene(1)) == 1


def test_the_voice_track_is_findable():
    assert a_valid_timeline().voice_track.kind == "voice"
