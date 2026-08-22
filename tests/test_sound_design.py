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

    # dip_to_black is the profile's section-break transition; a plain
    # crossfade is an ordinary cut and no longer earns a whoosh of its own.
    transitions = [Transition(at=3.0, kind="dip_to_black", duration=0.4)]
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


def _noise_file(tmp_path, seconds: int = 60) -> str:
    """A real audio file, so the director measures a genuine envelope."""
    import numpy as np
    import scipy.io.wavfile as wav

    path = tmp_path / f"voice_{seconds}.wav"
    samples = (np.random.randn(44100 * seconds) * 300).astype("int16")
    wav.write(str(path), 44100, samples)
    return str(path)

# ---------------------------------------------------------------------------
# SFX placement
# ---------------------------------------------------------------------------


def test_sfx_land_on_structural_moments_not_every_cut(tmp_path):
    """A documentary cuts every four seconds and a quarter of those are
    dissolves. Whooshing each one is a whoosh every fifteen seconds for the
    length of the video, which stops reading as emphasis within a minute."""
    import random

    import style_profile as sp
    from providers.music.director import MusicDirector
    from timeline import Transition

    voice = _noise_file(tmp_path, seconds=600)
    profile = sp.load("documentary")
    rng = random.Random(0)
    transitions = [
        Transition(at=i * 4.0, kind=profile.transitions.pick(rng), duration=0.4)
        for i in range(1, 150)
    ]

    tracks = MusicDirector().build_audio_tracks(
        voice_path=voice, total_duration=600.0, profile=profile,
        transitions=transitions, overlays=[],
    )

    whooshes = [t for t in tracks if t.label == "sfx_whoosh"]
    non_cut = [t for t in transitions if t.kind != "cut"]

    assert len(whooshes) < len(non_cut) / 2
    starts = sorted(t.start for t in whooshes)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= 15.0 for g in gaps), gaps


def test_no_sfx_when_the_profile_asks_for_none(tmp_path):
    import style_profile as sp
    from providers.music.director import MusicDirector
    from timeline import Transition

    voice = _noise_file(tmp_path, seconds=120)
    profile = sp.load("calm-narrative")
    assert profile.music.sfx_on_transitions is False

    tracks = MusicDirector().build_audio_tracks(
        voice_path=voice, total_duration=120.0, profile=profile,
        transitions=[Transition(at=10.0, kind="dip_to_black", duration=0.5)],
    )

    assert not [t for t in tracks if t.kind == "sfx"]


def test_nothing_is_scheduled_past_the_end(tmp_path):
    import style_profile as sp
    from providers.music.director import MusicDirector
    from timeline import Transition

    voice = _noise_file(tmp_path, seconds=60)
    tracks = MusicDirector().build_audio_tracks(
        voice_path=voice, total_duration=60.0, profile=sp.load("documentary"),
        transitions=[Transition(at=59.9, kind="dip_to_black", duration=0.4)],
    )

    assert all(t.start < 60.0 for t in tracks)
