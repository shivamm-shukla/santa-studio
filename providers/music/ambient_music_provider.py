"""Procedural ambient music provider: synthesizes smooth, copyright-free background beds
tailored to video mood without external API dependencies or copyright strikes.
"""

import hashlib
import os
import numpy as np
import scipy.io.wavfile as wav

from providers.base import MusicProvider

MUSIC_DIR = "runs/music"

MOOD_FREQS = {
    "curious": [130.81, 164.81, 196.00, 246.94, 293.66],  # Cmaj9
    "cinematic": [110.00, 130.81, 164.81, 196.00],        # Amin7
    "mysterious": [98.00, 116.54, 146.83, 174.61],        # Gdim/min
    "energetic": [146.83, 185.00, 220.00, 293.66],        # Dmaj
    "calm": [116.54, 146.83, 174.61, 220.00],             # Bbmaj7
}


class AmbientMusicProvider(MusicProvider):
    """Generates clean, subtle, looped ambient audio beds for YouTube background score."""

    def search(self, mood: str = "curious") -> dict:
        os.makedirs(MUSIC_DIR, exist_ok=True)
        mood_key = mood.lower().strip()
        freqs = MOOD_FREQS.get(mood_key, MOOD_FREQS["curious"])

        digest = hashlib.md5(f"{mood_key}_{freqs}".encode()).hexdigest()[:8]
        track_path = os.path.join(MUSIC_DIR, f"bg_music_{mood_key}_{digest}.wav")

        if os.path.exists(track_path) and os.path.getsize(track_path) > 0:
            return {"track_path": track_path}

        sample_rate = 44100
        duration = 60.0  # 60s base loop
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        audio = np.zeros_like(t)

        for i, f in enumerate(freqs):
            weight = 0.25 / (1.0 + 0.3 * i)
            # Soft sine with gentle chorus detuning and subtle LFO modulation
            lfo = 1.0 + 0.05 * np.sin(2 * np.pi * 0.2 * t + i)
            audio += weight * np.sin(2 * np.pi * f * t) * lfo
            audio += (weight * 0.4) * np.sin(2 * np.pi * (f * 1.003) * t)

        # Smooth loop envelope (fade in 3s, fade out 3s)
        fade_len = int(sample_rate * 3.0)
        fade_in = np.linspace(0, 1, fade_len)
        fade_out = np.linspace(1, 0, fade_len)
        audio[:fade_len] *= fade_in
        audio[-fade_len:] *= fade_out

        # Normalize and master to soft background loudness
        max_val = np.max(np.abs(audio))
        if max_val > 0:
            audio = (audio / max_val) * 0.35

        audio_int16 = (audio * 32767).astype(np.int16)
        wav.write(track_path, sample_rate, audio_int16)

        return {"track_path": track_path}
