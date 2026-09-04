"""How the narration is *read*, as opposed to whether it exists.

Every check here is about a specific way the finished voice track sounded
wrong rather than a way it failed: dead air between every sentence, a level
that stepped at each join, and a reading pinned to the pace of the reference
clip whatever the video needed.
"""

import pytest

pytest.importorskip("pydub")
from pydub import AudioSegment  # noqa: E402
from pydub.generators import Sine  # noqa: E402

from providers.voice import pace  # noqa: E402
from providers.voice.chunking import (  # noqa: E402
    PAUSE_MS,
    chunk_script,
    pause_after,
    stitch_audio_chunks,
)


def _piece(tmp_path, name, tone_ms, lead_silence_ms=0, tail_silence_ms=0, gain=0.0):
    """A synthesised piece, padded with silence the way the model pads its own."""
    audio = (
        AudioSegment.silent(duration=lead_silence_ms, frame_rate=24000)
        + Sine(220).to_audio_segment(duration=tone_ms).apply_gain(gain - 3)
        + AudioSegment.silent(duration=tail_silence_ms, frame_rate=24000)
    )
    path = str(tmp_path / name)
    audio.set_frame_rate(24000).set_channels(1).export(path, format="wav")
    return path


def test_a_comma_gets_a_breath_and_a_full_stop_gets_a_beat():
    assert pause_after("mid-thought,") == PAUSE_MS["clause"]
    assert pause_after("A finished sentence.") == PAUSE_MS["sentence"]
    assert pause_after("Ek poora vakya।") == PAUSE_MS["sentence"]
    assert pause_after("End of the scene.\n") == PAUSE_MS["paragraph"]
    assert PAUSE_MS["clause"] < PAUSE_MS["sentence"] < PAUSE_MS["paragraph"]


def test_a_scene_break_survives_chunking():
    """The newline is the only surviving record that a scene ended here.

    Chunking used to strip it, so the stitcher could not tell a section
    break from a comma and held the same gap for both.
    """
    chunks = chunk_script("Pehla scene khatam.\nDoosra scene shuru.")
    assert chunks[0].endswith("\n")
    assert pause_after(chunks[0]) == PAUSE_MS["paragraph"]
    assert not chunks[-1].endswith("\n")


def test_the_model_s_own_padding_is_taken_off_before_the_pause_is_added(tmp_path):
    """Trimming is what stops two sentences sitting a second apart.

    Each piece arrives with silence on both ends. Left in, it lands on top
    of the pause and the narration reads as though it were being spoken at
    half speed.
    """
    pieces = [
        _piece(tmp_path, "a.wav", tone_ms=400, lead_silence_ms=300, tail_silence_ms=300),
        _piece(tmp_path, "b.wav", tone_ms=400, lead_silence_ms=300, tail_silence_ms=300),
    ]
    out, spans = stitch_audio_chunks(
        pieces, output_path=str(tmp_path / "out.wav"), texts=["First.", "Second."]
    )

    untrimmed = 400 + 300 + 300
    assert spans[0]["duration"] * 1000 < untrimmed - 300

    gap_ms = (spans[1]["start"] - spans[0]["end"]) * 1000
    assert gap_ms == pytest.approx(PAUSE_MS["sentence"], abs=5)
    assert len(AudioSegment.from_file(out)) > 0


def test_pieces_are_brought_to_one_level_so_the_joins_do_not_step(tmp_path):
    """Pieces are synthesised independently and drift a few dB apart."""
    pieces = [
        _piece(tmp_path, "loud.wav", tone_ms=500, gain=0.0),
        _piece(tmp_path, "quiet.wav", tone_ms=500, gain=-9.0),
    ]
    out, spans = stitch_audio_chunks(
        pieces, output_path=str(tmp_path / "level.wav"), texts=["One.", "Two."]
    )

    stitched = AudioSegment.from_file(out)
    first = stitched[int(spans[0]["start"] * 1000):int(spans[0]["end"] * 1000)]
    second = stitched[int(spans[1]["start"] * 1000):int(spans[1]["end"] * 1000)]
    assert abs(first.dBFS - second.dBFS) < 1.5


def test_an_explicit_pause_still_overrides_the_punctuation(tmp_path):
    pieces = [
        _piece(tmp_path, "x.wav", tone_ms=300),
        _piece(tmp_path, "y.wav", tone_ms=300),
    ]
    _, spans = stitch_audio_chunks(
        pieces, output_path=str(tmp_path / "fixed.wav"), pause_ms=500, texts=["One,", "Two,"]
    )
    assert (spans[1]["start"] - spans[0]["end"]) * 1000 == pytest.approx(500, abs=5)


def test_retiming_leaves_a_factor_of_one_alone(tmp_path):
    path = _piece(tmp_path, "same.wav", tone_ms=500)
    assert pace.retime(path, 1.0) == path


def test_retiming_shortens_the_track_without_resampling_it(tmp_path):
    path = _piece(tmp_path, "slow.wav", tone_ms=2000)
    before = AudioSegment.from_file(path)

    faster = pace.retime(path, 1.25, output_path=str(tmp_path / "fast.wav"))
    if faster == path:
        pytest.skip("ffmpeg is unavailable, so retiming degraded to a no-op")

    after = AudioSegment.from_file(faster)
    assert len(after) == pytest.approx(len(before) / 1.25, rel=0.05)
    # A resample would have moved the pitch with the speed; a time-stretch
    # keeps the frame rate, and so the voice, exactly where it was.
    assert after.frame_rate == before.frame_rate


def test_spans_follow_the_track_onto_its_new_clock():
    spans = [{"start": 0.0, "end": 2.0, "duration": 2.0}, {"start": 2.5, "end": 4.5, "duration": 2.0}]
    moved = pace.rescale_spans(spans, 1.25)
    assert moved[0]["end"] == 1.6
    assert moved[1]["start"] == 2.0
    assert pace.rescale_spans(spans, 1.0) == spans


# --------------------------------------------------------------------------
# What the model is actually asked for
# --------------------------------------------------------------------------

def _runner():
    """The synthesis runner, loaded by path.

    It runs in Chatterbox's own interpreter and deliberately imports nothing
    from the project, so it is not importable as `providers.voice...` from
    here - only as the standalone file it is.
    """
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parent.parent / "providers" / "voice" / "chatterbox_runner.py"
    spec = importlib.util.spec_from_file_location("chatterbox_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Multilingual:
    def generate(self, text, language_id, audio_prompt_path=None, exaggeration=0.5,
                 cfg_weight=0.5, temperature=0.8, repetition_penalty=2.0,
                 min_p=0.05, top_p=1.0):
        ...


class _ChatterboxTurboTTS:
    def generate(self, text, repetition_penalty=1.2, min_p=0.0, top_p=0.95,
                 audio_prompt_path=None, exaggeration=0.0, cfg_weight=0.0,
                 temperature=0.8, top_k=1000, norm_loudness=True):
        ...


def test_the_pacing_dial_is_moved_off_the_librarys_default():
    """cfg_weight at 0.5 is what made every sentence land at one laboured pace.

    Chatterbox's own guidance for a normally-paced reference speaker is 0.3.
    """
    dials = _runner().dials_for(_Multilingual(), {})
    assert dials["cfg_weight"] == 0.3
    assert dials["exaggeration"] < 0.5


def test_a_models_own_tuning_is_not_overridden_with_a_guess():
    """repetition_penalty differs by nearly a factor of two between these
    models. Naming one number for both would be replacing a tuning."""
    assert "repetition_penalty" not in _runner().dials_for(_Multilingual(), {})


def test_the_turbo_model_is_left_with_emphasis_and_guidance_off():
    """Turbo ignores cfg_weight and exaggeration and warns when they are set.

    Its defaults are already the narration setting, so passing the numbers
    that help the other models would have printed a warning per chunk and
    changed nothing.
    """
    dials = _runner().dials_for(_ChatterboxTurboTTS(), {})
    assert "cfg_weight" not in dials
    assert "exaggeration" not in dials
    assert dials["temperature"] == 0.7


def test_what_the_caller_asked_for_beats_both():
    dials = _runner().dials_for(_ChatterboxTurboTTS(), {"cfg_weight": 0.9})
    assert dials["cfg_weight"] == 0.9


def test_a_dial_a_model_has_never_heard_of_is_not_passed_to_it():
    runner = _runner()
    accepted = runner._accepted(_ChatterboxTurboTTS.generate)
    chosen = runner.dials_for(_ChatterboxTurboTTS(), {"nonsense": 1.0})
    assert {k: v for k, v in chosen.items() if k in accepted} == {"temperature": 0.7}
