"""The demo film's score: one piece, eight movements, written to the edit.

reel/music.py wrote thirty seconds of one idea. A three minute demo cannot do
that - the same loop under a title card, a room reveal and a voice test makes
all three feel like the same moment, which is the fastest way to make a long
film feel longer. So this is sectioned, and each section has a job:

    open      almost nothing. A pad and a room tone, waiting.
    pulse     the machine wakes. Kick and sub arrive, filter opens.
    drive     the studio reveal. Wide chords, the full kit, movement.
    focus     work being done. Tight, ticking, low - it should not compete
              with what is on screen, because that is the part being read.
    sparse    the voice section. Almost silent by design: a real human voice
              is about to play and music over it is just rudeness.
    lift      the film plays. Warm, major, rising.
    energy    clips. Fastest thing in the piece, and the shortest.
    resolve   the crane out. Everything decays into one last chord.

Still synthesised, still 128 BPM, still original - the reasoning in music.py
applies here and more so, because three minutes of licensed music under a
product film is three minutes of somebody else's copyright.

    python reel/score.py build/demo/score.wav
"""

import math
import os
import struct
import sys
import wave

import numpy as np

RATE = 44100
BPM = 128.0
BEAT = 60.0 / BPM
BAR = BEAT * 4

# (name, bars). 96 bars is three minutes exactly at this tempo.
SECTIONS = [
    # These are the film's acts, bar for bar - see CUT in reel/demo_edit.py.
    # The score exists to hold the shape between the three real sounds in it,
    # so a section that does not line up with a cut is a section working
    # against the picture.
    ("open",    4),   #   0.0 -  7.5   a dark desk, the machine asleep
    ("pulse",   4),   #   7.5 - 15.0   it wakes, the site is on the screen
    ("drive",  20),   #  15.0 - 52.5   into the studio, the lights, the turn
    ("focus",   8),   #  52.5 - 67.5   the brief
    ("focus2", 12),   #  67.5 - 90.0   the work
    ("sparse", 12),   #  90.0 -112.5   the voice - stay out of the way
    ("lift",   12),   # 112.5 -135.0   the film it made
    ("energy", 12),   # 135.0 -157.5   shorts
    ("resolve", 8),   # 157.5 -172.5   the crane out and the end card
]

TOTAL_BARS = sum(b for _, b in SECTIONS)
LENGTH = TOTAL_BARS * BAR


def env(n, attack, curve=2.0):
    out = np.ones(n)
    attack = min(attack, n)
    if attack > 0:
        out[:attack] = np.linspace(0, 1, attack)
    fall = np.linspace(1, 0, max(1, n - attack)) ** curve
    out[attack:] = fall[: n - attack]
    return out


def lowpass(x, cutoff):
    from scipy.signal import lfilter
    a = math.exp(-2 * math.pi * cutoff / RATE)
    y = lfilter([1 - a], [1, -a], x)
    return lfilter([1 - a], [1, -a], y)


def saw(freq, length, harmonics=12):
    n = int(length * RATE)
    t = np.arange(n) / RATE
    out = np.zeros(n)
    for h in range(1, harmonics + 1):
        if freq * h > RATE / 2.2:
            break
        out += np.sin(2 * np.pi * freq * h * t) / h
    return out / 1.9


def sine(freq, length, harmonic=0.0):
    n = int(length * RATE)
    t = np.arange(n) / RATE
    return np.sin(2 * np.pi * freq * t) + harmonic * np.sin(4 * np.pi * freq * t)


def kick(length=0.44):
    n = int(length * RATE)
    t = np.arange(n) / RATE
    pitch = 45 + 120 * np.exp(-t * 36)
    body = np.sin(2 * np.pi * np.cumsum(pitch) / RATE)
    click = np.random.uniform(-1, 1, n) * np.exp(-t * 400) * 0.3
    return (body * env(n, 0, 1.7) + click) * 0.9


def hat(length=0.05, bright=9000):
    n = int(length * RATE)
    noise = np.random.uniform(-1, 1, n)
    return (noise - lowpass(noise, bright)) * env(n, 0, 3.2) * 0.3


def clap(length=0.17):
    n = int(length * RATE)
    noise = np.random.uniform(-1, 1, n)
    return (noise - lowpass(noise, 1300)) * env(n, int(0.003 * RATE), 2.6) * 0.32


def riser(length):
    n = int(length * RATE)
    t = np.linspace(0, 1, n)
    noise = np.random.uniform(-1, 1, n)
    out = np.zeros(n)
    for cut, weight in ((700, 0.5), (2000, 0.75), (5600, 1.0)):
        out += (noise - lowpass(noise, cut)) * weight * (t ** (2.0 + cut / 4200))
    return out * 0.15 * (t ** 1.4)


def impact(length=2.8):
    n = int(length * RATE)
    t = np.arange(n) / RATE
    boom = np.sin(2 * np.pi * (52 + 30 * np.exp(-t * 9)) * t) * np.exp(-t * 2.2)
    tail = lowpass(np.random.uniform(-1, 1, n), 2200) * np.exp(-t * 3.4) * 0.5
    return (boom + tail) * 0.7


# A minor throughout, so the sections are movements of one piece rather than
# eight different tracks stitched together. i - VI - III - VII.
A2, C3, E3, F2, G2, A3, C4, E4, G4, F3 = 110.0, 130.81, 164.81, 87.31, 98.0, 220.0, 261.63, 329.63, 392.0, 174.61
PROG = [
    (A2, [A3, C4, E4]),
    (F2, [F3 * 2, A3, C4]),
    (C3, [C4, E4, G4]),
    (G2, [G2 * 2, C4, E4]),
]


def place(track, when, sound, gain=1.0):
    start = int(when * RATE)
    if start >= len(track):
        return
    end = min(len(track), start + len(sound))
    track[start:end] += sound[: end - start] * gain


def section(track, name, start_bar, bars):
    """Writes one movement. Everything is positioned from the bar it is in."""
    for b in range(bars):
        bar_at = (start_bar + b) * BAR
        root, notes = PROG[b % 4]
        last = b == bars - 1

        # --- the pad, which every section has and none sounds the same ---
        cut = {"open": 380, "pulse": 1500, "drive": 3400, "focus": 900,
               "focus2": 1100, "sparse": 520, "lift": 3000, "energy": 4200,
               "resolve": 1400}[name]
        gain = {"open": 0.20, "pulse": 0.26, "drive": 0.30, "focus": 0.16,
                "focus2": 0.17, "sparse": 0.11, "lift": 0.30, "energy": 0.26,
                "resolve": 0.30}[name]
        pad = np.zeros(int(BAR * RATE))
        for note in notes:
            pad += saw(note / 2, BAR)
        pad = lowpass(pad, cut) * gain
        pad *= env(len(pad), int(0.3 * RATE), 0.3)
        place(track, bar_at, pad)

        if name == "open":
            # Nothing but air, and a lift into the section that follows.
            if last:
                place(track, bar_at, riser(BAR), 1.1)
            elif b % 4 == 3:
                place(track, bar_at + BAR / 2, riser(BAR / 2), 0.35)
            continue

        if name == "sparse":
            # Deliberately almost empty. A held sub and one soft pulse a bar,
            # so there is a tempo to cut to and nothing to listen past.
            place(track, bar_at, sine(root / 2, BAR, 0.15) * env(int(BAR * RATE), int(0.4 * RATE), 0.5), 0.22)
            place(track, bar_at + BEAT * 2, hat(0.04, 12000), 0.18)
            continue

        # --- everything else has a floor ---
        drums = name in ("pulse", "drive", "focus", "focus2", "lift", "energy", "resolve")
        for beat in range(4):
            when = bar_at + beat * BEAT
            if not drums:
                continue
            if name == "resolve" and b >= bars - 4:
                continue          # let the ending breathe
            quiet = name in ("focus", "focus2")
            place(track, when, kick(), 0.55 if quiet else 1.0)
            place(track, when, sine(root, BEAT * 0.9, 0.2) * env(int(BEAT * 0.9 * RATE), 300, 1.1),
                  0.30 if quiet else 0.45)
            place(track, when + BEAT / 2, hat(), 0.5 if quiet else 0.75)
            if name in ("drive", "energy", "lift"):
                place(track, when + BEAT / 4, hat(0.035, 11500), 0.4)
            if name == "energy":
                place(track, when + BEAT * 3 / 4, hat(0.03, 13000), 0.35)

        if name in ("drive", "lift", "energy") and not (name == "resolve"):
            for beat in (1, 3):
                place(track, bar_at + beat * BEAT, clap(), 0.34)

        # --- the moving part ---
        if name in ("focus", "focus2"):
            # A tick rather than a tune. Sixteenths on one note, filtered
            # right down, so it reads as time passing under the picture.
            for i in range(16):
                voice = lowpass(saw(notes[0] * 2, BEAT / 4 * 1.4, harmonics=5), 1700)
                voice *= env(len(voice), 120, 3.0)
                place(track, bar_at + i * (BEAT / 4), voice, 0.055)
        elif name in ("drive", "energy"):
            for i in range(16):
                note = notes[i % len(notes)] * (2 if (i // len(notes)) % 2 else 1)
                voice = lowpass(saw(note, BEAT / 4 * 1.6, harmonics=8), 5200)
                voice *= env(len(voice), 90, 3.0)
                place(track, bar_at + i * (BEAT / 4), voice, 0.15)
        elif name == "lift":
            # Longer notes, up an octave: the same chords, but singing.
            for i, note in enumerate(notes):
                voice = lowpass(saw(note * 2, BAR / 2, harmonics=9), 4200)
                voice *= env(len(voice), int(0.08 * RATE), 1.2)
                place(track, bar_at + (i % 2) * (BAR / 2), voice, 0.10)

        # Off-beat stab, which is most of what makes a section move.
        if name in ("pulse", "drive", "energy"):
            for beat in (1, 3):
                stab = np.zeros(int(BEAT * 0.5 * RATE))
                for note in notes:
                    stab += saw(note, BEAT * 0.5)
                stab = lowpass(stab, 2800) * env(len(stab), 180, 2.4)
                place(track, bar_at + beat * BEAT + BEAT * 0.5, stab, 0.20)


def build():
    track = np.zeros(int((LENGTH + 3.0) * RATE))
    bar = 0
    for name, bars in SECTIONS:
        section(track, name, bar, bars)
        # Every section change gets a hit on its downbeat, which is what makes
        # a cut feel intended rather than abrupt.
        if bar:
            place(track, bar * BAR, impact(2.2), 0.42 if name in ("focus", "sparse") else 0.62)
        bar += bars

    # The last chord, left ringing after the drums have gone.
    place(track, (TOTAL_BARS - 4) * BAR, impact(3.2), 0.7)
    tail = np.zeros(int(BAR * 4 * RATE))
    for note in PROG[0][1]:
        tail += saw(note / 2, BAR * 4)
    tail = lowpass(tail, 2200) * env(len(tail), int(0.2 * RATE), 0.8)
    place(track, (TOTAL_BARS - 4) * BAR, tail, 0.26)

    track = np.tanh(track * 1.2) * 0.9
    ramp = int(0.03 * RATE)
    track[:ramp] *= np.linspace(0, 1, ramp)
    track[-int(0.8 * RATE):] *= np.linspace(1, 0, int(0.8 * RATE))
    return track


def write(path, mono):
    stereo = np.empty(len(mono) * 2)
    delay = int(0.012 * RATE)
    right = np.concatenate([np.zeros(delay), mono[:-delay]])
    stereo[0::2] = mono
    stereo[1::2] = mono * 0.8 + right * 0.2
    data = np.clip(stereo, -1, 1)
    with wave.open(path, "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(struct.pack("<%dh" % len(data), *(data * 32000).astype(np.int16)))


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "build/demo/score.wav"
    os.makedirs(os.path.dirname(target), exist_ok=True)
    write(target, build())
    at = 0.0
    print(f"{target}  {LENGTH:.1f}s  {TOTAL_BARS} bars")
    for name, bars in SECTIONS:
        print(f"  {at:7.2f}s  {name}")
        at += bars * BAR
