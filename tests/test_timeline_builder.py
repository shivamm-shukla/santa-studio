"""Converting a finished run into a Timeline.

The scene-timing tests are the important ones. The old assembler divided the
narration equally between scenes, so picture and words drifted apart within
about half a minute, while the script agent had been emitting a
timestamp_estimate for every scene that nothing read.
"""

import pytest

pytest.importorskip("pydub")

import style_profile as sp  # noqa: E402
import timeline_builder as builder  # noqa: E402


@pytest.fixture
def voice_file(tmp_path):
    from pydub import AudioSegment
    from pydub.generators import WhiteNoise

    audio = AudioSegment.silent(duration=0)
    for _ in range(3):
        audio += WhiteNoise().to_audio_segment(duration=1500).apply_gain(-12)
        audio += AudioSegment.silent(duration=1000)
    path = tmp_path / "voice.wav"
    audio.export(path, format="wav")
    return str(path)


@pytest.fixture
def stills(tmp_path):
    from PIL import Image

    made = []
    for name in "abcd":
        path = tmp_path / f"{name}.jpg"
        Image.new("RGB", (800, 600), (100, 120, 140)).save(path)
        made.append(str(path))
    return made


def a_state(voice_file, stills, scenes=None, timestamps=True):
    scenes = scenes or [
        {"text": "one two three four five six seven eight nine ten",
         "timestamp_estimate": "0:00-0:10", "visual_hint": "first"},
        {"text": "eleven twelve", "timestamp_estimate": "0:10-0:14", "visual_hint": "second"},
        {"text": "a b c d e f g h i j k l m n o p q r s t",
         "timestamp_estimate": "0:14-0:30", "visual_hint": "third"},
    ]
    if not timestamps:
        scenes = [{k: v for k, v in s.items() if k != "timestamp_estimate"} for s in scenes]

    return {
        "run_id": "test-run-0001",
        "topic": "A test topic",
        "script": {"scenes": scenes, "script_text": " ".join(s["text"] for s in scenes)},
        "voice_output": {
            "audio_path": voice_file,
            "word_timestamps": [
                {"word": f"w{i}", "start": i * 0.4, "end": (i + 1) * 0.4} for i in range(18)
            ],
        },
        "visual_output": {"scene_assets": [
            {"scene_index": i, "asset_type": "image", "asset_path": stills[i]}
            for i in range(len(scenes))
        ]},
    }


# --------------------------------------------------------------------------
# Scene timing
# --------------------------------------------------------------------------

def test_durations_follow_the_scripts_own_timestamps():
    scenes = [
        {"text": "x", "timestamp_estimate": "0:00-0:10"},
        {"text": "x", "timestamp_estimate": "0:10-0:40"},
        {"text": "x", "timestamp_estimate": "0:40-0:50"},
    ]
    durations = builder.scene_durations(scenes, 60.0)
    # The middle scene has three times the range of the others.
    assert durations[1] > durations[0] * 2.5
    assert sum(durations) == pytest.approx(60.0)


def test_durations_are_not_all_equal():
    """The behaviour this replaces: total / len(scenes) for every scene."""
    scenes = [
        {"text": "short", "timestamp_estimate": "0:00-0:05"},
        {"text": "much much longer scene", "timestamp_estimate": "0:05-0:35"},
    ]
    durations = builder.scene_durations(scenes, 40.0)
    assert len(set(round(d, 2) for d in durations)) > 1


def test_word_counts_are_used_when_there_are_no_timestamps():
    scenes = [{"text": "one two three four"}, {"text": "one"}]
    durations = builder.scene_durations(scenes, 50.0)
    assert durations[0] == pytest.approx(40.0)
    assert durations[1] == pytest.approx(10.0)


def test_scrambled_timestamps_are_ignored_rather_than_trusted():
    # A partially filled or out-of-order set of estimates is worse than none,
    # because it puts the picture confidently in the wrong place.
    scenes = [
        {"text": "one two three four", "timestamp_estimate": "0:30-0:40"},
        {"text": "one", "timestamp_estimate": "0:00-0:10"},
    ]
    durations = builder.scene_durations(scenes, 50.0)
    assert durations[0] == pytest.approx(40.0)   # fell back to word counts


def test_a_missing_timestamp_disables_the_whole_estimate_path():
    scenes = [
        {"text": "one two three four", "timestamp_estimate": "0:00-0:10"},
        {"text": "one"},
    ]
    durations = builder.scene_durations(scenes, 50.0)
    assert durations[0] == pytest.approx(40.0)


def test_durations_fall_back_to_an_equal_split_with_nothing_to_go_on():
    scenes = [{"text": ""}, {"text": ""}, {"text": ""}]
    durations = builder.scene_durations(scenes, 30.0)
    assert durations == pytest.approx([10.0, 10.0, 10.0])


@pytest.mark.parametrize("total", [1.0, 7.3, 60.0, 1200.0])
def test_durations_always_sum_exactly_to_the_narration(total):
    # A drift becomes a gap, and the timeline validator treats a gap as an
    # error rather than a rounding detail.
    scenes = [
        {"text": "a b c", "timestamp_estimate": "0:00-0:07"},
        {"text": "d", "timestamp_estimate": "0:07-0:09"},
        {"text": "e f", "timestamp_estimate": "0:09-0:20"},
    ]
    assert sum(builder.scene_durations(scenes, total)) == pytest.approx(total)


def test_a_single_scene_takes_the_whole_video():
    assert builder.scene_durations([{"text": "only"}], 42.0) == [42.0]


def test_no_scenes_produces_no_durations():
    assert builder.scene_durations([], 10.0) == []


# --------------------------------------------------------------------------
# Building
# --------------------------------------------------------------------------

def test_a_built_timeline_is_valid(voice_file, stills):
    timeline = builder.build(a_state(voice_file, stills))
    assert timeline.problems() == []


def test_shots_cover_the_whole_narration(voice_file, stills):
    timeline = builder.build(a_state(voice_file, stills))
    assert timeline.shots[0].start == 0
    assert timeline.shots[-1].end == pytest.approx(timeline.duration, abs=0.01)


def test_the_duration_comes_from_the_voice_track(voice_file, stills):
    timeline = builder.build(a_state(voice_file, stills))
    assert timeline.duration == pytest.approx(7.5, abs=0.1)


def test_stills_are_given_motion(voice_file, stills):
    profile = sp.load("documentary")
    profile.motion.still_probability = 1.0
    timeline = builder.build(a_state(voice_file, stills), profile)
    assert all(shot.motion is not None for shot in timeline.shots)


def test_motion_can_be_switched_off_by_the_profile(voice_file, stills):
    profile = sp.load("documentary")
    profile.motion.still_probability = 0.0
    profile.motion.video_probability = 0.0
    timeline = builder.build(a_state(voice_file, stills), profile)
    assert all(shot.motion is None for shot in timeline.shots)


def test_a_scene_with_no_asset_becomes_a_colour_card(voice_file, stills):
    state = a_state(voice_file, stills)
    state["visual_output"]["scene_assets"] = state["visual_output"]["scene_assets"][:1]
    timeline = builder.build(state)
    assert timeline.problems() == []
    assert any(shot.source_type == "color" for shot in timeline.shots)


def test_image_and_video_sources_are_told_apart(voice_file, stills, tmp_path):
    state = a_state(voice_file, stills)
    fake_video = tmp_path / "clip.mp4"
    fake_video.write_bytes(b"not really a video")
    state["visual_output"]["scene_assets"][0] = {
        "scene_index": 0, "asset_path": str(fake_video)
    }
    timeline = builder.build(state)
    assert timeline.shots[0].source_type == "video"
    assert timeline.shots[1].source_type == "image"


def test_captions_are_grouped_to_the_profiles_line_length(voice_file, stills):
    profile = sp.load("documentary")
    profile.captions.words_per_line = 3
    timeline = builder.build(a_state(voice_file, stills), profile)
    assert len(timeline.captions) == 6          # 18 words, 3 per line
    assert all(len(caption.words) <= 3 for caption in timeline.captions)


def test_captions_can_be_switched_off(voice_file, stills):
    profile = sp.load("documentary")
    profile.captions.enabled = False
    assert builder.build(a_state(voice_file, stills), profile).captions == []


def test_a_transition_sits_at_every_cut_but_the_first(voice_file, stills):
    timeline = builder.build(a_state(voice_file, stills))
    assert len(timeline.transitions) == len(timeline.shots) - 1
    starts = {round(shot.start, 3) for shot in timeline.shots[1:]}
    assert {round(t.at, 3) for t in timeline.transitions} == starts


def test_the_voice_track_is_always_present(voice_file, stills):
    timeline = builder.build(a_state(voice_file, stills))
    assert timeline.voice_track is not None
    assert timeline.voice_track.duration == pytest.approx(timeline.duration)


def test_music_gets_a_duck_curve_that_moves(voice_file, stills, tmp_path):
    from pydub import AudioSegment
    from pydub.generators import Sine

    music = tmp_path / "bed.wav"
    Sine(220).to_audio_segment(duration=3000).export(music, format="wav")

    timeline = builder.build(a_state(voice_file, stills), music_path=str(music))
    bed = [track for track in timeline.audio if track.kind == "music"]
    assert bed, "no music track was added"
    levels = {round(bed[0].gain_at(t), 1) for t in (0.5, 2.0, 3.5, 5.0)}
    assert len(levels) > 1, "the bed sat at one level for the whole video"


def test_no_music_is_added_when_the_file_is_missing(voice_file, stills):
    timeline = builder.build(a_state(voice_file, stills), music_path="/nowhere/bed.mp3")
    assert [t for t in timeline.audio if t.kind == "music"] == []


def test_a_run_without_a_voice_track_says_what_to_do(stills):
    state = {"run_id": "x", "voice_output": {"audio_path": "/nowhere/voice.wav"}}
    with pytest.raises(ValueError) as caught:
        builder.build(state)
    assert "voice stage" in str(caught.value)


# --------------------------------------------------------------------------
# Reproducibility
# --------------------------------------------------------------------------

def test_the_same_run_always_cuts_the_same_way(voice_file, stills):
    # Re-rendering a project should not silently produce a different edit.
    state = a_state(voice_file, stills)
    first = builder.build(state)
    second = builder.build(state)
    assert first.to_dict() == second.to_dict()


def test_different_runs_get_different_edits(voice_file, stills):
    first = builder.build(a_state(voice_file, stills))
    other = a_state(voice_file, stills)
    other["run_id"] = "a-completely-different-run"
    second = builder.build(other)
    assert first.to_dict() != second.to_dict()


def test_an_explicit_seed_is_honoured(voice_file, stills):
    state = a_state(voice_file, stills)
    assert builder.build(state, seed=1).to_dict() != builder.build(state, seed=2).to_dict()


def test_the_profile_used_is_recorded(voice_file, stills):
    timeline = builder.build(a_state(voice_file, stills), sp.load("fast-explainer"))
    assert timeline.meta["style_profile"] == "fast-explainer"


def test_a_faster_profile_is_visible_in_the_result(voice_file, stills):
    calm = builder.build(a_state(voice_file, stills), sp.load("calm-narrative"))
    fast = builder.build(a_state(voice_file, stills), sp.load("fast-explainer"))
    # Same footage, so the same shot count - but the caption density differs.
    assert len(fast.captions) > len(calm.captions)
