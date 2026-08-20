"""Preset-based voice filter chain - the engine behind the 'Instagram
filter for your voice' concept. Applied to cloned audio after generation,
before it becomes the video's final voice track.

Built on pydub (which shells out to ffmpeg), so providers._ffmpeg_setup
must run before any of these are called.
"""

import os

from pydub import AudioSegment
from pydub.effects import normalize

from providers._ffmpeg_setup import ensure_ffmpeg_on_path

FILTER_DIR = "runs/filtered_audio"


def _pitch_shift(audio: AudioSegment, semitones: float) -> AudioSegment:
    # Resampling the frame rate shifts pitch (and speed together, like a
    # classic tape/vinyl pitch shift) - simple and dependency-free.
    factor = 2 ** (semitones / 12)
    shifted = audio._spawn(
        audio.raw_data, overrides={"frame_rate": int(audio.frame_rate * factor)}
    )
    return shifted.set_frame_rate(audio.frame_rate)


def _warmth(audio: AudioSegment) -> AudioSegment:
    # Cheap "warmth" approximation: gentle low-end boost via a low-pass
    # blend, no external EQ library required.
    bass = audio.low_pass_filter(700).apply_gain(4)
    return audio.overlay(bass - 6)


def _energy_boost(audio: AudioSegment) -> AudioSegment:
    return normalize(audio).apply_gain(2).speedup(playback_speed=1.05)


def _calm(audio: AudioSegment) -> AudioSegment:
    return _pitch_shift(audio, -1).apply_gain(-2)


PRESETS = {
    "natural": lambda a: normalize(a),
    "warm": lambda a: normalize(_warmth(a)),
    "deep": lambda a: normalize(_pitch_shift(a, -2)),
    "bright": lambda a: normalize(_pitch_shift(a, 2)),
    "energetic": lambda a: normalize(_energy_boost(a)),
    "calm": lambda a: normalize(_calm(a)),
}


def apply_filter(audio_path: str, preset: str) -> str:
    """Applies a named preset to the audio at audio_path and returns the
    path to the filtered output file. Raises ValueError for an unknown
    preset name.
    """
    if preset not in PRESETS:
        raise ValueError(f"Unknown voice filter preset {preset!r}. Available: {list(PRESETS)}")

    ensure_ffmpeg_on_path()
    os.makedirs(FILTER_DIR, exist_ok=True)

    audio = AudioSegment.from_file(audio_path)
    filtered = PRESETS[preset](audio)

    base = os.path.splitext(os.path.basename(audio_path))[0]
    output_path = os.path.join(FILTER_DIR, f"{base}__{preset}.wav")
    filtered.export(output_path, format="wav")
    return output_path
