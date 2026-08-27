"""Measuring and repairing a voice sample before it is used for cloning.

A cloning model copies whatever it is given. Hand it a phone recording made in
a room with a fan running and it will faithfully reproduce the fan, the room,
and the phone - for every video, forever. The sample is the one input in this
whole pipeline that a user cannot regenerate, and it is also the one they are
least equipped to judge, because everybody's own voice sounds fine to them on
the device they recorded it with.

So this does two separate jobs:

* **Measure** the sample and say what is wrong with it in words the person who
  recorded it can act on - "there is a hum at 50 Hz", "you clipped at 0:03",
  "this is four seconds and needs at least eight" - rather than a number.
* **Repair** what can be repaired: rumble, broadband noise, clipping,
  sibilance, uneven level.

What it deliberately does not do is flatter the input. If a sample is too
short, or too noisy for denoising to save, the honest answer is to record it
again, and saying so costs thirty seconds where not saying so costs every
video made afterwards.

`providers/voice/filters.py` is a different thing that happens to sound
similar. Those are six cosmetic presets - pitch down, add warmth - applied
because someone wanted a different-sounding voice. This is repair: making a
recording usable at all. A filter is a choice; this is maintenance.

Processing is a single FFmpeg filtergraph rather than a pile of Python DSP.
FFmpeg is already a hard dependency, its filters are far better tested than
anything worth writing here, and it runs at a speed that makes the whole chain
feel instant on a sample of this length.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile

from providers._ffmpeg_setup import ensure_ffmpeg_on_path

# What a clone reference should look like by the time it is handed to a model.
TARGET_RATE = 24000
TARGET_LUFS = -18.0
TARGET_PEAK_DB = -2.0

# Anything shorter than this is not enough for a model to characterise a voice;
# anything past the second figure adds nothing and slows every step that reads
# it.
MIN_SECONDS = 8.0
IDEAL_SECONDS = 20.0
MAX_USEFUL_SECONDS = 60.0

# Signal-to-noise below this cannot be rescued by denoising without leaving the
# voice sounding like it is underwater.
MIN_SNR_DB = 12.0
GOOD_SNR_DB = 25.0

# A sample that has already been through a low-bitrate codec has nothing above
# this, and cloning it produces a muffled voice no amount of EQ will fix.
MIN_BANDWIDTH_HZ = 7000

CLIPPING_TOLERANCE = 0.001   # 0.1% of samples touching full scale


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------

def _samples(path: str):
    """Mono float samples in -1..1, plus the sample rate."""
    ensure_ffmpeg_on_path()
    import numpy as np
    from pydub import AudioSegment

    audio = AudioSegment.from_file(path).set_channels(1)
    raw = np.array(audio.get_array_of_samples()).astype(np.float64)
    full_scale = float(1 << (8 * audio.sample_width - 1))
    return raw / full_scale, audio.frame_rate


def _db(value: float) -> float:
    return -120.0 if value <= 1e-9 else 20 * math.log10(value)


def _windows(signal, rate: int, milliseconds: int = 50):
    import numpy as np

    size = max(1, int(rate * milliseconds / 1000))
    usable = (len(signal) // size) * size
    if usable == 0:
        return np.array([signal])
    return signal[:usable].reshape(-1, size)


def analyse(path: str) -> dict:
    """Everything measurable about a sample, in units a human can reason about."""
    import numpy as np

    signal, rate = _samples(path)
    if signal.size == 0:
        return {"duration": 0.0, "rate": rate, "empty": True}

    frames = _windows(signal, rate)
    energies = np.sqrt(np.mean(frames ** 2, axis=1))
    ordered = np.sort(energies)

    # The noise floor is the quietest tenth of the recording - the gaps between
    # words. Taking a percentile rather than the single quietest window keeps
    # one freak silent frame from flattering the result.
    quiet = ordered[: max(1, len(ordered) // 10)]
    loud = ordered[max(1, int(len(ordered) * 0.75)) :]
    noise_floor = float(np.mean(quiet))
    speech_level = float(np.mean(loud))

    peak = float(np.max(np.abs(signal)))
    clipped = np.abs(signal) >= 0.999
    clip_ratio = float(np.mean(clipped))

    # Where the clipping happens, so the message can point at it.
    clip_times = []
    if clip_ratio > 0:
        indices = np.flatnonzero(clipped)
        gaps = np.flatnonzero(np.diff(indices) > rate // 10)
        starts = np.concatenate(([indices[0]], indices[gaps + 1])) if gaps.size else indices[:1]
        clip_times = [round(float(i) / rate, 2) for i in starts[:5]]

    # Highest frequency still carrying real energy, which is how a sample that
    # has already been through a low-bitrate codec gives itself away.
    spectrum = np.abs(np.fft.rfft(signal * np.hanning(len(signal))))
    freqs = np.fft.rfftfreq(len(signal), 1 / rate)
    if spectrum.max() > 0:
        cumulative = np.cumsum(spectrum ** 2)
        cumulative /= cumulative[-1]
        bandwidth = float(freqs[int(np.searchsorted(cumulative, 0.995))])
    else:
        bandwidth = 0.0

    # A steady tone in the bottom of the spectrum is mains hum, and it is worth
    # naming because the fix is to move away from a cable or a charger.
    hum = _detect_hum(spectrum, freqs)

    silence_ratio = float(np.mean(energies < max(noise_floor * 2, 1e-4)))

    return {
        "duration": len(signal) / rate,
        "rate": rate,
        "peak_db": _db(peak),
        "rms_db": _db(float(np.sqrt(np.mean(signal ** 2)))),
        "noise_floor_db": _db(noise_floor),
        "speech_db": _db(speech_level),
        "snr_db": _db(speech_level) - _db(noise_floor),
        "clip_ratio": clip_ratio,
        "clip_times": clip_times,
        "bandwidth_hz": bandwidth,
        "silence_ratio": silence_ratio,
        "dc_offset": float(np.mean(signal)),
        "hum_hz": hum,
        "empty": False,
    }


def _detect_hum(spectrum, freqs) -> float | None:
    """Mains hum at 50 or 60 Hz, if it stands well clear of its neighbours."""
    import numpy as np

    for candidate in (50.0, 60.0):
        band = (freqs > candidate - 2) & (freqs < candidate + 2)
        around = (freqs > candidate - 20) & (freqs < candidate + 20) & ~band
        if not band.any() or not around.any():
            continue
        if np.mean(spectrum[band]) > np.mean(spectrum[around]) * 8:
            return candidate
    return None


# --------------------------------------------------------------------------
# Judgement
# --------------------------------------------------------------------------

def _timestamp(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def score(analysis: dict) -> dict:
    """Turns measurements into a verdict and a list of things to do about it.

    Every problem carries the fix, because "SNR 8 dB" tells the person who
    recorded it nothing at all, and "record somewhere quieter, away from
    fans and open windows" tells them everything.
    """
    problems: list[dict] = []

    def fault(severity, message, fix):
        problems.append({"severity": severity, "message": message, "fix": fix})

    if analysis.get("empty"):
        fault("fatal", "This file contains no audio.",
              "Check the recording actually saved, and upload it again.")
        return {"usable": False, "grade": "unusable", "score": 0, "problems": problems}

    duration = analysis["duration"]
    if duration < MIN_SECONDS:
        fault("fatal",
              f"Only {duration:.1f} seconds of audio - a voice needs at least "
              f"{MIN_SECONDS:.0f} to be characterised.",
              f"Record around {IDEAL_SECONDS:.0f} seconds of natural speech.")
    elif duration < IDEAL_SECONDS:
        fault("minor",
              f"{duration:.1f} seconds is workable but short.",
              f"Around {IDEAL_SECONDS:.0f} seconds gives a noticeably closer match.")

    snr = analysis["snr_db"]
    if snr < MIN_SNR_DB:
        fault("fatal",
              f"The background is almost as loud as the voice ({snr:.0f} dB of separation).",
              "Record somewhere quieter - away from fans, traffic and open windows. "
              "Denoising cannot rescue this without making the voice sound underwater.")
    elif snr < GOOD_SNR_DB:
        fault("minor",
              f"There is audible background noise ({snr:.0f} dB of separation).",
              "Repair will reduce it, but a quieter room would be better.")

    if analysis["clip_ratio"] > CLIPPING_TOLERANCE:
        where = ", ".join(_timestamp(t) for t in analysis["clip_times"])
        fault("major",
              f"The recording is clipped - it distorts at {where}.",
              "Move further from the microphone or lower the input gain, and record again. "
              "Repair will soften it, but the detail that was lost is gone.")

    if analysis["bandwidth_hz"] < MIN_BANDWIDTH_HZ:
        fault("major",
              f"The recording only reaches {analysis['bandwidth_hz'] / 1000:.1f} kHz, "
              "so it will clone as a muffled voice.",
              "Either it has already been compressed - a voice note or a call "
              "recording, in which case use the original file - or it was "
              "captured with echo cancellation and noise suppression on, which "
              "band-limits a browser recording to call quality.")

    if analysis["hum_hz"]:
        fault("minor",
              f"There is {analysis['hum_hz']:.0f} Hz mains hum in the recording.",
              "Move the microphone away from power cables and chargers. Repair removes most of it.")

    if analysis["silence_ratio"] > 0.5:
        fault("minor",
              f"{analysis['silence_ratio'] * 100:.0f}% of the recording is silence.",
              "Trim the gaps, or record a continuous passage of speech.")

    if analysis["peak_db"] < -20:
        fault("minor",
              f"The recording is very quiet (peaks at {analysis['peak_db']:.0f} dB).",
              "Repair will bring it up, which also brings up the noise. "
              "Recording closer to the microphone is better.")

    if abs(analysis["dc_offset"]) > 0.01:
        fault("minor", "The waveform is offset from centre.",
              "Harmless, and repair corrects it.")

    fatal = sum(1 for p in problems if p["severity"] == "fatal")
    major = sum(1 for p in problems if p["severity"] == "major")
    minor = sum(1 for p in problems if p["severity"] == "minor")

    value = max(0, 100 - fatal * 60 - major * 20 - minor * 7)
    if fatal:
        grade = "unusable"
    elif value >= 85:
        grade = "excellent"
    elif value >= 70:
        grade = "good"
    elif value >= 50:
        grade = "usable"
    else:
        grade = "poor"

    return {
        "usable": fatal == 0,
        "grade": grade,
        "score": value,
        "problems": problems,
    }


def inspect(path: str) -> dict:
    """Measure and judge in one call - what a caller usually wants."""
    analysis = analyse(path)
    return {"analysis": analysis, **score(analysis)}


# --------------------------------------------------------------------------
# Repair
# --------------------------------------------------------------------------

def build_chain(analysis: dict) -> list[str]:
    """The FFmpeg filters this particular sample needs, in order.

    Built from the measurements rather than applied uniformly: denoising a
    clean recording costs clarity for nothing, and de-essing a voice with no
    sibilance dulls it. Every stage here is present because something was
    measured that calls for it.
    """
    chain = []

    # Rumble, handling noise and desk thumps live below anything in a voice.
    # This is unconditional because there is never anything wanted down there.
    chain.append("highpass=f=75:poles=2")

    if analysis.get("hum_hz"):
        base = analysis["hum_hz"]
        # The harmonics matter as much as the fundamental.
        for harmonic in (1, 2, 3):
            chain.append(f"equalizer=f={base * harmonic}:t=q:w=8:g=-22")

    if analysis.get("clip_ratio", 0) > CLIPPING_TOLERANCE:
        chain.append("adeclip")

    snr = analysis.get("snr_db", 99)
    if snr < GOOD_SNR_DB:
        # Denoise proportionally. A heavy setting on a nearly-clean recording
        # is what produces the watery, artefacted sound people associate with
        # noise reduction.
        strength = 6 if snr > 18 else (12 if snr > MIN_SNR_DB else 18)
        floor = max(-45.0, analysis.get("noise_floor_db", -40.0) - 5)
        chain.append(f"afftdn=nr={strength}:nf={floor:.0f}")

    # Cut the boxiness a small room adds, and lift the range that carries
    # consonants so the voice reads as close rather than distant.
    chain.append("equalizer=f=250:t=q:w=1.2:g=-2.5")
    chain.append("equalizer=f=3200:t=q:w=1.4:g=2.5")

    chain.append("deesser=i=0.4")

    # Even out the distance between loud and quiet passages, so a cloned voice
    # does not swing in level mid-sentence.
    chain.append("acompressor=threshold=-20dB:ratio=3:attack=8:release=180:makeup=2")
    chain.append(f"alimiter=limit={10 ** (TARGET_PEAK_DB / 20):.3f}")

    chain.append(f"loudnorm=I={TARGET_LUFS}:TP={TARGET_PEAK_DB}:LRA=7")
    chain.append(f"aformat=sample_fmts=s16:sample_rates={TARGET_RATE}:channel_layouts=mono")
    return chain


def repair(source_path: str, destination_path: str = "") -> dict:
    """Runs the repair chain and reports what it did and what it achieved.

    Returns the path plus before/after measurements, because the useful
    question after repair is not "did it run" but "is it good enough now".
    """
    ensure_ffmpeg_on_path()

    if not os.path.exists(source_path):
        raise FileNotFoundError(f"No voice sample at {source_path!r}")

    before = analyse(source_path)
    verdict_before = score(before)
    chain = build_chain(before)

    if not destination_path:
        handle, destination_path = tempfile.mkstemp(suffix=".wav")
        os.close(handle)

    parent = os.path.dirname(destination_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", source_path,
        "-af", ",".join(chain),
        destination_path,
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(destination_path):
        raise RuntimeError(
            "Repairing the voice sample failed.\n"
            f"  {result.stderr.strip()[:400]}"
        )

    after = analyse(destination_path)
    return {
        "path": destination_path,
        "chain": chain,
        "before": before,
        "after": after,
        "verdict_before": verdict_before,
        "verdict_after": score(after),
    }


def describe(result: dict) -> str:
    """A short readable summary of a repair, for a CLI or a log."""
    before, after = result["before"], result["after"]
    lines = [
        f"  duration     {before['duration']:.1f}s",
        f"  noise floor  {before['noise_floor_db']:.0f} dB  ->  {after['noise_floor_db']:.0f} dB",
        f"  separation   {before['snr_db']:.0f} dB  ->  {after['snr_db']:.0f} dB",
        f"  peak         {before['peak_db']:.0f} dB  ->  {after['peak_db']:.0f} dB",
        f"  grade        {result['verdict_before']['grade']}  ->  {result['verdict_after']['grade']}",
    ]
    return "\n".join(lines)
