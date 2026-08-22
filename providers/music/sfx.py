"""Procedural SFX generator: synthesizes clean, punchy sound effects for video editing.

Generates:
- whoosh: Fast frequency-swept white noise with exponential envelope (for transitions)
- impact: Deep resonant sub-bass transient with subtle punch (for reveals and titles)
- riser: Pitch-bent rising tone with crescendo (for section breaks and build-ups)
- pop: Sharp, snappy transient (for callouts and badge appearances)

Zero API keys, CC0/public domain by construction, instant generation, cached locally.
"""

from __future__ import annotations

import hashlib
import os
import numpy as np
import scipy.io.wavfile as wav

import paths

SFX_TYPES = ("whoosh", "impact", "riser", "pop")


def _sfx_dir() -> str:
    directory = paths.home() / "cache" / "sfx"
    os.makedirs(directory, exist_ok=True)
    return str(directory)


def generate_sfx(kind: str, duration: float | None = None, sample_rate: int = 44100) -> str:
    """Generates or retrieves a cached procedural SFX file. Returns path to wav."""
    kind = kind.lower().strip()
    if kind not in SFX_TYPES:
        kind = "whoosh"

    if duration is None:
        duration = {
            "whoosh": 0.45,
            "impact": 1.2,
            "riser": 2.0,
            "pop": 0.15,
        }[kind]

    digest = hashlib.md5(f"{kind}_{duration}_{sample_rate}".encode()).hexdigest()[:8]
    output_path = os.path.join(_sfx_dir(), f"sfx_{kind}_{digest}.wav")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
        return output_path

    n_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, n_samples, False)

    if kind == "whoosh":
        # Swept noise filtered by a Gaussian-like bell envelope
        noise = np.random.normal(0, 1, n_samples)
        envelope = np.exp(-((t - duration * 0.45) ** 2) / (2 * (duration * 0.18) ** 2))
        # Frequency sweep simulation via phase modulation
        mod = np.sin(2 * np.pi * (150 + 600 * (t / duration) ** 2) * t)
        audio = (noise * 0.7 + mod * 0.3) * envelope

    elif kind == "impact":
        # Sub-bass exponential pitch-drop plus punchy click
        f_start, f_end = 120.0, 35.0
        decay = 4.0
        freqs = f_start * np.exp(-t * decay) + f_end
        phase = 2 * np.pi * np.cumsum(freqs) / sample_rate
        sub = np.sin(phase) * np.exp(-t * 3.0)
        # Click transient in the first 10ms
        click_samples = min(int(sample_rate * 0.015), n_samples)
        click = np.random.normal(0, 1, click_samples) * np.linspace(1, 0, click_samples)
        audio = sub
        audio[:click_samples] += click * 0.4

    elif kind == "riser":
        # Pitch ramp from 100Hz to 800Hz with volume crescendo
        f_start, f_end = 90.0, 750.0
        freqs = np.linspace(f_start, f_end, n_samples)
        phase = 2 * np.pi * np.cumsum(freqs) / sample_rate
        # Exponential volume swell
        crescendo = (np.exp(t / duration * 3.0) - 1.0) / (np.exp(3.0) - 1.0)
        audio = np.sin(phase) * crescendo

    elif kind == "pop":
        # Fast 400Hz to 150Hz blip
        freqs = np.linspace(500, 180, n_samples)
        phase = 2 * np.pi * np.cumsum(freqs) / sample_rate
        envelope = np.exp(-t * 25.0)
        audio = np.sin(phase) * envelope

    else:
        audio = np.zeros(n_samples)

    # Master and normalize to -3dB peak
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = (audio / max_val) * 0.85

    audio_int16 = (audio * 32767).astype(np.int16)
    wav.write(output_path, sample_rate, audio_int16)
    return output_path
