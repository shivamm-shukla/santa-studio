"""The reel's music, synthesised rather than licensed.

Every other part of this project refuses to use something it does not have the
right to, and a soundtrack is not the place to make an exception - a borrowed
track is the one thing that could get the whole reel taken down. So it is
built here out of oscillators and noise: original by construction, free to use
anywhere, and - more usefully - it can be written to the exact length and
tempo the edit needs, with the drop on the frame the picture wants it.

128 BPM, sixteen bars, thirty seconds. The structure is the edit:

    bars 1-4    the room is dark, titles - pad and a rising noise sweep
    bar  5      the drop: the screen comes on, kick and bass land together
    bars 5-8    the laptop, filmed from four angles, one to a bar
    bars 9-12   inside the studio, arp on top
    bars 13-15  the product, cuts on the half bar
    bar  16     the crane out, everything decays into the impact

    python reel/music.py build/reel/track.wav
"""

import math
import struct
import sys
import wave

import numpy as np

RATE = 44100
BPM = 128.0
BEAT = 60.0 / BPM          # 0.46875s
BAR = BEAT * 4             # 1.875s
BARS = 16
LENGTH = BAR * BARS        # 30.0s

DROP_BAR = 4               # zero-based: the fifth bar
ARP_BAR = 8
PEAK_BAR = 12


def seconds(n):
    return np.zeros(int(n * RATE))


def at(track, when, sound, gain=1.0):
    """Mixes `sound` into `track` at `when` seconds, clipped to the end."""
    start = int(when * RATE)
    if start >= len(track):
        return
    end = min(len(track), start + len(sound))
    track[start:end] += sound[: end - start] * gain


def env(n, attack, decay, curve=2.0):
    """Attack-decay envelope over n samples, both in samples."""
    out = np.ones(n)
    if attack > 0:
        out[:attack] = np.linspace(0, 1, attack)
    fall = np.linspace(1, 0, max(1, n - attack)) ** curve
    out[attack:] = fall[: n - attack]
    return out


def kick(length=0.42):
    """Pitch drops from a click to a thud - the whole character is in that."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    pitch = 46 + 118 * np.exp(-t * 38)
    body = np.sin(2 * np.pi * np.cumsum(pitch) / RATE)
    click = np.random.uniform(-1, 1, n) * np.exp(-t * 420) * 0.35
    return (body * env(n, 0, n, 1.7) + click) * 0.92


def sub(freq, length):
    n = int(length * RATE)
    t = np.arange(n) / RATE
    wave_ = np.sin(2 * np.pi * freq * t) + 0.24 * np.sin(4 * np.pi * freq * t)
    return wave_ * env(n, int(0.006 * RATE), n, 1.1) * 0.5


def saw(freq, length, harmonics=13):
    """A saw built from its harmonics, so nothing aliases into a whistle."""
    n = int(length * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for h in range(1, harmonics + 1):
        if freq * h > RATE / 2.2:
            break
        out += np.sin(2 * np.pi * freq * h * t) / h
    return out / 1.9


def lowpass(x, cutoff):
    """One pole, applied twice. Gentle, and enough to take the glare off."""
    a = math.exp(-2 * math.pi * cutoff / RATE)
    out = np.empty_like(x)
    prev = 0.0
    for _ in range(2):
        for i, value in enumerate(x):
            prev = value * (1 - a) + prev * a
            out[i] = prev
        x = out.copy()
        prev = 0.0
    return out


def lowpass_fast(x, cutoff):
    """The same shape, done with a filter rather than a Python loop."""
    a = math.exp(-2 * math.pi * cutoff / RATE)
    b = 1 - a
    # y[n] = b*x[n] + a*y[n-1], twice
    from scipy.signal import lfilter  # noqa: PLC0415
    y = lfilter([b], [1, -a], x)
    return lfilter([b], [1, -a], y)


def filt(x, cutoff):
    try:
        return lowpass_fast(x, cutoff)
    except Exception:
        return lowpass(x, cutoff)


def hat(length=0.055, bright=9000):
    n = int(length * RATE)
    noise = np.random.uniform(-1, 1, n)
    return (noise - filt(noise, bright)) * env(n, 0, n, 3.2) * 0.34


def riser(length):
    """Noise through a filter that opens as it goes. The lift into the drop."""
    n = int(length * RATE)
    t = np.linspace(0, 1, n)
    noise = np.random.uniform(-1, 1, n)
    out = np.zeros(n)
    # A handful of bands, each opening at its own rate: cheaper than sweeping
    # a filter sample by sample and it sounds wider.
    for cut, weight in ((600, 0.5), (1800, 0.7), (5200, 1.0)):
        band = noise - filt(noise, cut)
        out += band * weight * (t ** (2.2 + cut / 4000))
    return out * 0.16 * (t ** 1.4)


def impact(length=2.6):
    n = int(length * RATE)
    t = np.arange(n) / RATE
    boom = np.sin(2 * np.pi * (54 + 30 * np.exp(-t * 9)) * t) * np.exp(-t * 2.4)
    tail = filt(np.random.uniform(-1, 1, n), 2400) * np.exp(-t * 3.6) * 0.5
    return (boom + tail) * 0.75


# A minor: the chords are i - VI - III - VII, which is every trailer ever
# written and works for the same reason every time.
A2, C3, E3, F3, G3, A3, C4, E4 = 110.0, 130.81, 164.81, 174.61, 196.0, 220.0, 261.63, 329.63
CHORDS = [
    (A2, [A3, C4, E4]),
    (F3 / 2, [F3 * 2, A3 * 2 / 2 * 2, C4]),
    (C3, [C4, E4, G3 * 2]),
    (G3 / 2, [G3, C4, E4]),
]


def build():
    track = seconds(LENGTH + 2.2)

    for bar in range(BARS):
        top = bar * BAR
        root, notes = CHORDS[bar % 4]
        after_drop = bar >= DROP_BAR

        # --- pad, all the way through, opening up at the drop ---
        pad = np.zeros(int(BAR * RATE))
        for note in notes:
            pad += saw(note / 2, BAR)
        cut = 480 if not after_drop else 3200
        pad = filt(pad, cut) * (0.16 if not after_drop else 0.3)
        n = len(pad)
        pad *= env(n, int(0.25 * RATE), n, 0.35)
        at(track, top, pad)

        if not after_drop:
            # Intro: no drums. The riser does the work, and the last bar
            # before the drop gets the long one.
            if bar == DROP_BAR - 1:
                at(track, top, riser(BAR), 1.0)
            elif bar % 2 == 1:
                at(track, top + BAR / 2, riser(BAR / 2), 0.5)
            continue

        # --- the drop and everything after ---
        at(track, top, impact(1.8), 0.55 if bar == DROP_BAR else 0.0)

        for beat in range(4):
            when = top + beat * BEAT
            at(track, when, kick())
            at(track, when, sub(root, BEAT * 0.92), 0.9)
            at(track, when + BEAT / 2, hat(), 0.7)
            if bar >= ARP_BAR:
                at(track, when + BEAT / 4, hat(0.04, 11000), 0.45)

            # Off-beat stab, the thing that makes it move rather than sit.
            if beat % 2 == 1:
                stab = np.zeros(int(BEAT * 0.5 * RATE))
                for note in notes:
                    stab += saw(note, BEAT * 0.5)
                stab = filt(stab, 2600) * env(len(stab), int(0.004 * RATE), len(stab), 2.4)
                at(track, when + BEAT * 0.5, stab, 0.22)

        if bar >= ARP_BAR:
            # Sixteenths, climbing the chord. This is the "it is building" part.
            step = BEAT / 4
            for i in range(16):
                note = notes[i % len(notes)] * (2 if (i // len(notes)) % 2 else 1)
                voice = saw(note, step * 1.6, harmonics=7)
                voice = filt(voice, 3800 if bar < PEAK_BAR else 6500)
                voice *= env(len(voice), int(0.002 * RATE), len(voice), 3.0)
                at(track, top + i * step, voice, 0.13 if bar < PEAK_BAR else 0.17)

        # A snare-ish clap on two and four, from the peak on.
        if bar >= PEAK_BAR:
            for beat in (1, 3):
                n2 = int(0.16 * RATE)
                clap = np.random.uniform(-1, 1, n2)
                clap = (clap - filt(clap, 1400)) * env(n2, int(0.003 * RATE), n2, 2.6)
                at(track, top + beat * BEAT, clap, 0.3)

    # The last hit, landing on the final bar so the picture can cut to black on it.
    at(track, (BARS - 1) * BAR, impact(2.8), 0.8)

    # Soft clip rather than hard: a limiter shape, so the loud parts stay loud
    # without the crackle that clipping puts on a kick.
    track = np.tanh(track * 1.25) * 0.92

    # Fade the very start and end so nothing pops.
    ramp = int(0.02 * RATE)
    track[:ramp] *= np.linspace(0, 1, ramp)
    track[-int(0.4 * RATE):] *= np.linspace(1, 0, int(0.4 * RATE))
    return track


def write(path, mono):
    stereo = np.empty(len(mono) * 2)
    # A touch of width: the sides get a few milliseconds of delay.
    delay = int(0.011 * RATE)
    right = np.concatenate([np.zeros(delay), mono[:-delay]]) if delay else mono
    stereo[0::2] = mono
    stereo[1::2] = mono * 0.82 + right * 0.18
    data = np.clip(stereo, -1, 1)
    with wave.open(path, "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(struct.pack("<%dh" % len(data), *(data * 32000).astype(np.int16)))


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "build/reel/track.wav"
    import os
    os.makedirs(os.path.dirname(target), exist_ok=True)
    write(target, build())
    print(f"{target}  {LENGTH:.1f}s  {BPM:.0f} BPM  drop at {DROP_BAR * BAR:.3f}s")
