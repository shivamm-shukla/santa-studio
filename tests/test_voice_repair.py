"""Tests for the voice sample repair and measurement chain."""

import numpy as np
import pytest

pytest.importorskip("pydub")
from pydub import AudioSegment  # noqa: E402
from pydub.generators import Sine, WhiteNoise  # noqa: E402

import providers.voice.repair as repair  # noqa: E402


@pytest.fixture
def clean_sample(tmp_path):
    """A clean 10s voice-like synthetic sample."""
    path = tmp_path / "clean.wav"
    audio = AudioSegment.silent(duration=0)
    for _ in range(5):
        audio += Sine(440).to_audio_segment(duration=1500).apply_gain(-12)
        audio += AudioSegment.silent(duration=500)
    audio.set_frame_rate(24000).set_channels(1).set_sample_width(2).export(path, format="wav")
    return str(path)


@pytest.fixture
def noisy_sample(tmp_path):
    """A 10s sample with strong background white noise."""
    path = tmp_path / "noisy.wav"
    audio = AudioSegment.silent(duration=0)
    for _ in range(5):
        speech = Sine(300).to_audio_segment(duration=1500).apply_gain(-10)
        noise = WhiteNoise().to_audio_segment(duration=1500).apply_gain(-18)
        audio += speech.overlay(noise)
        audio += WhiteNoise().to_audio_segment(duration=500).apply_gain(-18)
    audio.set_frame_rate(24000).set_channels(1).set_sample_width(2).export(path, format="wav")
    return str(path)


@pytest.fixture
def hum_sample(tmp_path):
    """A 10s sample with prominent 50 Hz mains hum."""
    path = tmp_path / "hum.wav"
    audio = AudioSegment.silent(duration=0)
    for _ in range(5):
        speech = Sine(500).to_audio_segment(duration=1500).apply_gain(-8)
        hum = Sine(50).to_audio_segment(duration=1500).apply_gain(-14)
        audio += speech.overlay(hum)
        audio += Sine(50).to_audio_segment(duration=500).apply_gain(-14)
    audio.set_frame_rate(24000).set_channels(1).set_sample_width(2).export(path, format="wav")
    return str(path)


@pytest.fixture
def short_sample(tmp_path):
    """A sample too short (<8s)."""
    path = tmp_path / "short.wav"
    audio = Sine(440).to_audio_segment(duration=3000).apply_gain(-10)
    audio.set_frame_rate(24000).set_channels(1).set_sample_width(2).export(path, format="wav")
    return str(path)


# --------------------------------------------------------------------------
# Measurement & Analysis
# --------------------------------------------------------------------------

def test_analyse_empty_file(tmp_path):
    path = tmp_path / "empty.wav"
    AudioSegment.silent(duration=0).export(path, format="wav")
    res = repair.analyse(str(path))
    assert res.get("empty") is True
    assert res["duration"] == 0.0


def test_analyse_measures_duration_and_peak(clean_sample):
    res = repair.analyse(clean_sample)
    assert not res["empty"]
    assert res["duration"] == pytest.approx(10.0, abs=0.1)
    assert res["rate"] == 24000
    assert -25 < res["peak_db"] < 0


def test_analyse_detects_hum(hum_sample):
    res = repair.analyse(hum_sample)
    assert res["hum_hz"] in (50.0, 60.0)


def test_detect_hum_none_on_clean(clean_sample):
    res = repair.analyse(clean_sample)
    assert res["hum_hz"] is None


# --------------------------------------------------------------------------
# Scoring & Verdict
# --------------------------------------------------------------------------

def test_score_unusable_on_empty(tmp_path):
    path = tmp_path / "empty.wav"
    AudioSegment.silent(duration=0).export(path, format="wav")
    res = repair.inspect(str(path))
    assert not res["usable"]
    assert res["grade"] == "unusable"
    assert any("no audio" in p["message"].lower() for p in res["problems"])


def test_score_fails_on_short_sample(short_sample):
    res = repair.inspect(short_sample)
    assert not res["usable"]
    assert res["grade"] == "unusable"
    assert any("seconds of audio" in p["message"] for p in res["problems"])


def test_score_clean_sample_is_usable(clean_sample):
    res = repair.inspect(clean_sample)
    assert res["usable"]
    assert res["grade"] in ("excellent", "good", "usable")


# --------------------------------------------------------------------------
# Repair & Chain Execution
# --------------------------------------------------------------------------

def test_build_chain_adds_hum_filter(hum_sample):
    analysis = repair.analyse(hum_sample)
    chain = repair.build_chain(analysis)
    assert any("equalizer=f=50" in f or "equalizer=f=60" in f for f in chain)


def test_repair_executes_and_outputs_valid_audio(noisy_sample, tmp_path):
    dest = str(tmp_path / "repaired.wav")
    result = repair.repair(noisy_sample, dest)
    assert result["path"] == dest
    assert len(result["chain"]) > 0
    assert result["after"]["duration"] == pytest.approx(result["before"]["duration"], abs=0.2)
    assert result["after"]["rate"] == repair.TARGET_RATE
    desc = repair.describe(result)
    assert "noise floor" in desc
