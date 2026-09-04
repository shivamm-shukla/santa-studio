"""Narration speed, without touching the pitch of the voice.

A cloned voice reads at whatever pace the reference clip set, and that is
often not the pace the video wants - the same take that sits right under a
long-form explainer drags under a two-minute short. This is the one knob
that fixes it after the fact.

It has to be ffmpeg's `atempo`, not pydub's `speedup`. speedup() cuts the
audio into windows and drops or repeats them, which on speech is audible as
a stutter on every syllable and is a large part of what makes a sped-up
clone sound mechanical. atempo is a proper time-stretch: the words get
closer together, the voice stays the same voice.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from providers._ffmpeg_setup import ensure_ffmpeg_on_path

# Past these the stretch starts to smear consonants whatever the algorithm,
# and a narration that needed more than this has a script problem rather
# than a speed problem.
MIN_FACTOR = 0.7
MAX_FACTOR = 1.5

# atempo itself only accepts 0.5-2.0 per instance, so anything outside that
# would need chaining; the clamp above keeps us well inside one pass.
NEGLIGIBLE = 0.01


def retime(audio_path: str, factor: float, output_path: str = "") -> str:
    """`audio_path` played `factor` times faster, at the same pitch.

    Returns the original path unchanged when the factor is 1 (or close
    enough that the re-encode would cost more than it is worth), so callers
    can pass a configured value through without checking it first.
    """
    factor = float(factor)
    if abs(factor - 1.0) < NEGLIGIBLE:
        return audio_path
    factor = max(MIN_FACTOR, min(MAX_FACTOR, factor))

    ensure_ffmpeg_on_path()

    if not output_path:
        handle, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(handle)

    command = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", audio_path,
        "-filter:a", f"atempo={factor:.4f}",
        output_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(output_path):
        # A voice track at the wrong speed is a far smaller problem than no
        # voice track, so this degrades rather than raises.
        return audio_path
    return output_path


def rescale_spans(spans, factor: float):
    """Chunk spans moved onto the retimed file's clock.

    atempo is a uniform transform, so every offset simply divides by the
    factor - the alignment stage can keep using the spans instead of falling
    back to transcribing the whole track again.
    """
    if not spans or abs(float(factor) - 1.0) < NEGLIGIBLE:
        return spans
    factor = max(MIN_FACTOR, min(MAX_FACTOR, float(factor)))
    return [
        {
            "start": round(float(s["start"]) / factor, 3),
            "end": round(float(s["end"]) / factor, 3),
            "duration": round(
                float(s.get("duration", float(s["end"]) - float(s["start"]))) / factor, 3
            ),
        }
        for s in spans
    ]
