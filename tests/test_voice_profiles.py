"""Tests for persistent voice profiles with automated repair and scoring."""

import os
import pytest

pytest.importorskip("pydub")
from pydub import AudioSegment  # noqa: E402
from pydub.generators import Sine, WhiteNoise  # noqa: E402

import providers.voice.profiles as profiles  # noqa: E402


@pytest.fixture
def noisy_voice_sample(tmp_path):
    path = tmp_path / "sample.wav"
    audio = AudioSegment.silent(duration=0)
    for _ in range(5):
        speech = Sine(350).to_audio_segment(duration=1500).apply_gain(-10)
        noise = WhiteNoise().to_audio_segment(duration=1500).apply_gain(-20)
        audio += speech.overlay(noise)
        audio += WhiteNoise().to_audio_segment(duration=500).apply_gain(-20)
    audio.set_frame_rate(24000).set_channels(1).set_sample_width(2).export(path, format="wav")
    return str(path)


def test_create_profile_creates_original_and_repaired(studio_home, noisy_voice_sample):
    res = profiles.create_profile("test_speaker", noisy_voice_sample, auto_repair=True)
    profile_id = res["profile_id"]

    assert os.path.exists(res["original_path"])
    assert res["repaired_path"] is not None
    assert os.path.exists(res["repaired_path"])
    assert res["repair_report"] is not None
    assert "verdict_after" in res["repair_report"]
    assert res["score"] is not None

    # Resolving voice path should prefer repaired_path when no filter preset is set
    resolved = profiles.resolve_voice_path(profile_id)
    assert resolved == res["repaired_path"]


def test_apply_filter_to_profile(studio_home, noisy_voice_sample):
    res = profiles.create_profile("speaker_two", noisy_voice_sample, auto_repair=True)
    profile_id = res["profile_id"]

    filtered_res = profiles.apply_filter_to_profile(profile_id, "warm")
    assert filtered_res["filtered_path"] is not None
    assert os.path.exists(filtered_res["filtered_path"])
    assert filtered_res["filter_preset"] == "warm"

    # Resolving voice path now returns filtered_path
    resolved = profiles.resolve_voice_path(profile_id)
    assert resolved == filtered_res["filtered_path"]


def test_delete_profile(studio_home, noisy_voice_sample):
    res = profiles.create_profile("temp_speaker", noisy_voice_sample)
    profile_id = res["profile_id"]
    assert profile_id in profiles.list_profiles()

    profiles.delete_profile(profile_id)
    assert profile_id not in profiles.list_profiles()
