"""The audio mixer: automation curves rendered onto real samples.

The point of these is that the score's level actually moves. The old mix
applied one constant to the whole video, so the only thing worth proving here
is that different moments come out at different levels for the right reasons.
"""

import pytest

pytest.importorskip("pydub")

from pydub import AudioSegment  # noqa: E402

import style_profile as sp  # noqa: E402
from render import audio_mix  # noqa: E402
from timeline import AudioTrack, GainPoint, Timeline  # noqa: E402


@pytest.fixture
def voice_file(tmp_path):
    """Narration with four 1.5s bursts separated by 1s pauses."""
    from pydub.generators import WhiteNoise

    audio = AudioSegment.silent(duration=0)
    for _ in range(4):
        audio += WhiteNoise().to_audio_segment(duration=1500).apply_gain(-12)
        audio += AudioSegment.silent(duration=1000)
    path = tmp_path / "voice.wav"
    audio.export(path, format="wav")
    return str(path)


@pytest.fixture
def music_file(tmp_path):
    from pydub.generators import Sine

    path = tmp_path / "bed.wav"
    Sine(220).to_audio_segment(duration=3000).apply_gain(-6).export(path, format="wav")
    return str(path)


# --------------------------------------------------------------------------
# Automation
# --------------------------------------------------------------------------

def test_a_curve_produces_different_levels_at_different_times(music_file, tmp_path):
    track = AudioTrack(source=music_file, kind="music", duration=3,
                       gain=[GainPoint(0, 0), GainPoint(3, -40)])
    rendered = audio_mix.render_track(track, 3.0)
    assert rendered[:300].dBFS > rendered[-300:].dBFS + 20


def test_a_single_gain_point_is_a_flat_level(music_file):
    flat = audio_mix.render_track(
        AudioTrack(source=music_file, duration=3, gain=[GainPoint(0, -10)]), 3.0
    )
    reference = AudioSegment.from_file(music_file)
    assert flat.dBFS == pytest.approx(reference.dBFS - 10, abs=0.5)


def test_no_curve_leaves_the_level_alone(music_file):
    rendered = audio_mix.render_track(AudioTrack(source=music_file, duration=3), 3.0)
    assert rendered.dBFS == pytest.approx(AudioSegment.from_file(music_file).dBFS, abs=0.2)


def test_slice_count_follows_how_much_the_curve_moves(music_file):
    # A steady section should not be chopped up just because it is long.
    steady = AudioTrack(source=music_file, gain=[GainPoint(0, -12), GainPoint(600, -12)])
    moving = AudioTrack(source=music_file, gain=[GainPoint(0, 0), GainPoint(10, -60)])
    assert len(audio_mix._slice_points(steady, 600_000)) < len(
        audio_mix._slice_points(moving, 10_000)
    )


def test_automation_is_cheaper_than_a_fixed_grid(music_file):
    track = AudioTrack(source=music_file,
                       gain=[GainPoint(0, -15), GainPoint(5, -26), GainPoint(10, -15)])
    slices = len(audio_mix._slice_points(track, 10_000)) - 1
    assert slices < 10_000 / audio_mix.MIN_SLICE_MS


# --------------------------------------------------------------------------
# Ducking against the real narration envelope
# --------------------------------------------------------------------------

def test_duck_curve_follows_the_pauses(voice_file):
    # A fixed offset under the voice track ducks through the pauses too, which
    # is exactly the flat result this replaces.
    style = sp.load("documentary").music
    curve = audio_mix.duck_curve(voice_file, None, style)
    track = AudioTrack(source="unused", gain=curve)

    during_speech = track.gain_at(0.8)     # inside the first burst
    during_pause = track.gain_at(2.1)      # inside the first pause, after release
    assert during_speech == pytest.approx(style.duck_db, abs=0.5)
    assert during_pause == pytest.approx(style.bed_db, abs=0.5)
    assert during_pause > during_speech


def test_duck_happens_before_the_word_arrives(voice_file):
    style = sp.load("documentary").music
    curve = audio_mix.duck_curve(voice_file, None, style)
    track = AudioTrack(source="unused", gain=curve)
    # Speech resumes at 2.5s; the level should already be moving by then.
    assert track.gain_at(2.5) < track.gain_at(2.5 - style.duck_attack - 0.05)


def test_duck_curve_survives_silent_audio(tmp_path):
    path = tmp_path / "silence.wav"
    AudioSegment.silent(duration=2000).export(path, format="wav")
    curve = audio_mix.duck_curve(str(path), None, sp.load("documentary").music)
    assert len(curve) >= 1


# --------------------------------------------------------------------------
# Fitting tracks into their slot
# --------------------------------------------------------------------------

def test_a_short_cue_loops_when_asked(music_file):
    track = AudioTrack(source=music_file, duration=10, loop=True)
    assert len(audio_mix.render_track(track, 10.0)) == pytest.approx(10_000, abs=50)


def test_a_short_cue_is_padded_rather_than_stretched(music_file):
    # A cue that ends should end, not be time-warped to fill its slot.
    track = AudioTrack(source=music_file, duration=10, loop=False)
    rendered = audio_mix.render_track(track, 10.0)
    assert len(rendered) == pytest.approx(10_000, abs=50)
    assert rendered[-1000:].dBFS == float("-inf")


def test_a_track_never_runs_past_the_end_of_the_video(music_file):
    track = AudioTrack(source=music_file, start=8.0, duration=30, loop=True)
    assert len(audio_mix.render_track(track, 10.0)) <= 2_100


def test_in_point_skips_into_the_source(music_file):
    full = audio_mix.render_track(AudioTrack(source=music_file), 3.0)
    trimmed = audio_mix.render_track(AudioTrack(source=music_file, in_point=1.0), 3.0)
    assert len(trimmed) < len(full)


# --------------------------------------------------------------------------
# The mix
# --------------------------------------------------------------------------

def test_mix_is_exactly_the_timeline_length(voice_file, music_file, tmp_path):
    timeline = Timeline(run_id="t", duration=10.0)
    timeline.audio = [
        AudioTrack(source=voice_file, kind="voice", duration=10),
        AudioTrack(source=music_file, kind="music", duration=10, loop=True),
    ]
    out = audio_mix.mix(timeline, str(tmp_path / "mix.wav"))
    assert len(AudioSegment.from_file(out)) == pytest.approx(10_000, abs=50)


def test_a_cue_lands_where_the_timeline_puts_it(music_file, tmp_path):
    timeline = Timeline(run_id="t", duration=10.0)
    timeline.audio = [AudioTrack(source=music_file, kind="music", start=5.0, duration=3)]
    mixed = AudioSegment.from_file(audio_mix.mix(timeline, str(tmp_path / "mix.wav")))
    assert mixed[:4000].dBFS == float("-inf")     # nothing before the cue
    assert mixed[5500:7500].dBFS > -60            # audible once it starts


def test_a_missing_music_cue_does_not_fail_the_mix(voice_file, tmp_path):
    timeline = Timeline(run_id="t", duration=10.0)
    timeline.audio = [
        AudioTrack(source=voice_file, kind="voice", duration=10),
        AudioTrack(source="/nowhere/absent.mp3", kind="music", duration=10),
    ]
    assert audio_mix.mix(timeline, str(tmp_path / "mix.wav"))


def test_a_missing_voice_track_does_fail_the_mix(tmp_path):
    # A video with no narration is a broken result, not a degraded one.
    timeline = Timeline(run_id="t", duration=10.0)
    timeline.audio = [AudioTrack(source="/nowhere/voice.wav", kind="voice", duration=10)]
    with pytest.raises(FileNotFoundError):
        audio_mix.mix(timeline, str(tmp_path / "mix.wav"))


def test_mixing_needs_a_duration(tmp_path):
    with pytest.raises(ValueError):
        audio_mix.mix(Timeline(run_id="t", duration=0), str(tmp_path / "mix.wav"))


def test_the_bed_really_is_quieter_under_speech(voice_file, music_file, tmp_path):
    """End to end: narration plus a ducked bed, measured off the finished mix."""
    style = sp.load("documentary").music
    timeline = Timeline(run_id="t", duration=10.0)
    timeline.audio = [
        AudioTrack(source=voice_file, kind="voice", duration=10),
        AudioTrack(source=music_file, kind="music", duration=10, loop=True,
                   gain=audio_mix.duck_curve(voice_file, None, style)),
    ]
    mixed = AudioSegment.from_file(audio_mix.mix(timeline, str(tmp_path / "mix.wav")))
    # 1.9-2.4s is a pause with the bed recovered; 9.2-9.8s is a pause too, but
    # compare against a speech burst instead.
    speech = mixed[600:1400].dBFS
    pause = mixed[2000:2400].dBFS
    assert speech > pause, "narration should be louder than a recovered bed"


def test_normalisation_lands_near_the_target(voice_file, tmp_path):
    timeline = Timeline(run_id="t", duration=10.0)
    timeline.audio = [AudioTrack(source=voice_file, kind="voice", duration=10)]
    out = audio_mix.mix(timeline, str(tmp_path / "mix.wav"))
    audio_mix.normalize_to_lufs(out, target_db=-14.0)
    assert AudioSegment.from_file(out).dBFS == pytest.approx(-14.0, abs=0.6)
