"""Tests for Phase 3 Sound Design: procedural SFX, dynamic multi-cue music director, and ducking."""

import os
import pytest

pytest.importorskip("pydub")
from pydub import AudioSegment
from pydub.generators import Sine

from providers.music.director import MusicDirector
from providers.music.sfx import generate_sfx
import style_profile as sp
from timeline import Transition, Overlay


@pytest.fixture
def test_voice(tmp_path):
    path = tmp_path / "voice_sample.wav"
    audio = AudioSegment.silent(duration=0)
    for _ in range(4):
        audio += Sine(300).to_audio_segment(duration=2000).apply_gain(-10)
        audio += AudioSegment.silent(duration=1000)
    audio.export(path, format="wav")
    return str(path)


def test_procedural_sfx_generation():
    for kind in ("whoosh", "impact", "riser", "pop"):
        sfx_path = generate_sfx(kind)
        assert os.path.exists(sfx_path)
        assert os.path.getsize(sfx_path) > 0
        audio = AudioSegment.from_file(sfx_path)
        assert len(audio) > 50


def test_music_director_single_cue_and_sfx(test_voice):
    profile = sp.load("documentary")
    director = MusicDirector()

    transitions = [Transition(at=3.0, kind="crossfade", duration=0.4)]
    overlays = [Overlay(start=1.5, duration=2.0, kind="text", text="Hook")]

    tracks = director.build_audio_tracks(
        voice_path=test_voice,
        total_duration=12.0,
        profile=profile,
        transitions=transitions,
        overlays=overlays,
    )

    kinds = [t.kind for t in tracks]
    assert "voice" in kinds
    assert "music" in kinds
    assert "sfx" in kinds

    # Verify SFX tracks for whoosh, impact, pop
    labels = [t.label for t in tracks if t.kind == "sfx"]
    assert any("whoosh" in l for l in labels)
    assert any("impact" in l for l in labels)
    assert any("pop" in l for l in labels)


def test_music_director_multi_cue_for_long_videos(test_voice):
    profile = sp.load("documentary")
    profile.music.change_cue_every = 30.0  # force multi-cue for 90s
    director = MusicDirector()

    tracks = director.build_audio_tracks(
        voice_path=test_voice,
        total_duration=90.0,
        profile=profile,
    )

    music_tracks = [t for t in tracks if t.kind == "music"]
    assert len(music_tracks) >= 3
    # Consecutive cues should have sequential start times
    assert music_tracks[0].start == 0.0
    assert music_tracks[1].start > music_tracks[0].start
