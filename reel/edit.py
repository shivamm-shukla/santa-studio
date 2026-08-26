"""Cuts the reel together, frame by frame.

Everything upstream of this is footage: room/reel.mjs films each scene and each
title card as a numbered sequence of stills. This is the edit - which shot is
on screen at which frame, what is laid over it, and what happens in between.

It is done here rather than in one enormous ffmpeg filtergraph because the
interesting parts of an edit are per frame. A dissolve is a weighted average of
two frames. A flash cut is one white frame at a known time. A title is an alpha
composite whose position is a function of where in the shot it is. Written as a
filtergraph all of that becomes an unreadable line; written as a loop it is
just the edit, and you can change a cut by changing a number.

The whole thing is built on the music, which reel/music.py wrote at 128 BPM.
A bar is 1.875 seconds, sixteen bars is thirty seconds, and every cut in here
lands on one of them.

    python reel/edit.py
"""

import os
import subprocess
import sys

import numpy as np
from PIL import Image

FPS = 30
W, H = 1080, 1920
BAR = 1.875
BARS = 16
TOTAL = BAR * BARS

REEL = "build/reel"
FRAMES_OUT = os.path.join(REEL, "cut")
TRACK = os.path.join(REEL, "track.wav")
MASTER = "santa_studio_reel.mp4"

FF = "venv/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"


def bars(n):
    return n * BAR


# --- the cut ---------------------------------------------------------------
#
# Each entry is (start bar, scene, where in that scene to start). The scene
# runs at its own speed from there; nothing is retimed, because these were all
# filmed at thirty for exactly this.

SHOTS = [
    (0,  "laptop", 0.0),      # asleep, dark room, one edge of light
    (1,  "laptop", 1.875),    # low three-quarter, still dark
    (2,  "laptop", 3.75),     # down the barrel at dark glass
    (3,  "laptop", 5.625),    # the last dark bar, waiting
    (4,  "laptop", 7.5),      # THE DROP: lights up, the site is on it
    (5,  "laptop", 9.375),    # round the shoulder
    (6,  "laptop", 11.25),    # over the top, onto the deck
    (7,  "laptop", 13.125),   # hard in on the screen
    (8,  "studio", 4.6),      # cut inside: the drone, climbing
    (9,  "studio", 10.4),     # down onto a desk
    (10, "board",  1.2),      # the brief, being written
    (11, "booth",  1.4),      # the microphone
    (12, "tv",     2.2),      # the television, running Clips
    (13, "studio", 26.0),     # the crane out
    (14, "laptop", 13.125),   # back to the desk, wide
    (15, "laptop", 13.9),     # and hold for the end card
]

# --- the titles ------------------------------------------------------------
#
# (card index, start in seconds, seconds on screen). Each was filmed at the
# length it is used at, so its own animation already fits.

TITLES = [
    (0, 0.30, 3.30),                 # SANTA STUDIO
    (1, bars(2) + 0.15, 1.60),       # Give it a topic.
    (2, bars(3) + 0.15, 1.60),       # Get the video back.
    (3, bars(5) + 0.15, 1.60),       # It researches. It checks itself.
    (4, bars(8) + 0.10, 1.65),       # A studio you can walk into.
    (5, bars(10) + 0.10, 1.65),      # Commission it at the board.
    (6, bars(11) + 0.10, 1.65),      # Read it in your own voice.
    (7, bars(12) + 0.10, 1.65),      # Cut shorts on the wall.
    (8, bars(15) + 0.05, 1.80),      # end card
]

# --- transitions -----------------------------------------------------------
#
# Most cuts are cuts. These are the exceptions, and each one is doing a job:
# the dissolves cover a change of place, and the flash is the drop.

DISSOLVE = {8: 0.22, 13: 0.18, 14: 0.20}   # bar -> seconds of cross fade
FLASH_AT = bars(4)                          # the frame the kick lands on
FLASH_LEN = 0.10


class Scene:
    """One filmed sequence, read off disk and cached a few frames at a time."""

    def __init__(self, name):
        self.dir = os.path.join(REEL, name)
        self.name = name
        self.count = len([f for f in os.listdir(self.dir) if f.endswith(".png")])
        self._cache = {}

    def at(self, seconds):
        index = max(0, min(self.count - 1, int(round(seconds * FPS))))
        if index in self._cache:
            return self._cache[index]
        path = os.path.join(self.dir, f"f{index:05d}.png")
        image = Image.open(path).convert("RGB")
        if image.size != (W, H):
            image = image.resize((W, H), Image.LANCZOS)
        if len(self._cache) > 4:
            self._cache.pop(next(iter(self._cache)))
        self._cache[index] = image
        return image


class Title:
    """A card, filmed with a transparent background."""

    def __init__(self, index):
        self.dir = os.path.join(REEL, f"title{index}")
        self.count = len([f for f in os.listdir(self.dir) if f.endswith(".png")])

    def at(self, i):
        index = max(0, min(self.count - 1, i))
        return Image.open(os.path.join(self.dir, f"f{index:05d}.png")).convert("RGBA")


def shot_for(frame):
    """Which shot is on screen at this frame, and how far into it we are."""
    t = frame / FPS
    bar = min(BARS - 1, int(t / BAR))
    start_bar, scene, offset = SHOTS[bar]
    return bar, scene, offset + (t - bars(start_bar))


def grade(array):
    """One look over the whole reel, so the cuts do not change stock.

    A gentle S on the curve, a little desaturation, a vignette and a breath of
    grain. The same operations the pipeline's own renders get - see
    render/grade.py - because the reel should look like what it is selling.
    """
    x = array.astype(np.float32) / 255.0

    # Lift the floor slightly and roll the top: film does not clip to black.
    x = 0.02 + x * 0.965
    x = np.clip(x, 0, 1)
    x = x * x * (3 - 2 * x) * 0.45 + x * 0.55        # a soft S

    grey = x.mean(axis=2, keepdims=True)
    x = grey + (x - grey) * 0.94                      # a touch off full colour

    # Warm the highlights, cool the shadows. Two numbers, and it stops looking
    # like a screenshot.
    x[..., 0] += (x[..., 0] ** 2) * 0.020
    x[..., 2] += ((1 - x[..., 2]) ** 2) * 0.016

    return x


VIGNETTE = None
GRAIN = None


def vignette():
    global VIGNETTE
    if VIGNETTE is None:
        yy, xx = np.mgrid[0:H, 0:W]
        cx, cy = W / 2, H / 2
        r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2) / np.sqrt(2)
        VIGNETTE = (1 - 0.30 * r ** 2.1)[..., None].astype(np.float32)
    return VIGNETTE


def grain(frame):
    """A different tile every frame, cycled rather than generated each time."""
    global GRAIN
    if GRAIN is None:
        rng = np.random.default_rng(7)
        GRAIN = rng.normal(0, 1, (8, H, W, 1)).astype(np.float32)
    return GRAIN[frame % 8]


def build():
    scenes = {name: Scene(name) for name in {s[1] for s in SHOTS}}
    titles = {i: Title(i) for i, _, _ in TITLES}

    os.makedirs(FRAMES_OUT, exist_ok=True)
    for stale in os.listdir(FRAMES_OUT):
        os.remove(os.path.join(FRAMES_OUT, stale))

    total_frames = int(TOTAL * FPS)
    vig = vignette()

    for frame in range(total_frames):
        t = frame / FPS
        bar, scene_name, offset = shot_for(frame)
        picture = scenes[scene_name].at(offset)

        # A dissolve reaches back into the shot that is ending, so the frame
        # is a blend of where we were and where we are going.
        fade = DISSOLVE.get(bar)
        if fade and t - bars(bar) < fade and bar > 0:
            k = (t - bars(bar)) / fade
            prev_bar, prev_scene, prev_offset = SHOTS[bar - 1]
            behind = scenes[prev_scene].at(prev_offset + (t - bars(prev_bar)))
            picture = Image.blend(behind, picture, k)

        array = np.asarray(picture, dtype=np.uint8)
        x = grade(array)
        x *= vig
        x += grain(frame) * 0.006

        # The drop, as one frame of light rather than a transition. It is the
        # loudest moment in the music and it should be the loudest in the
        # picture too.
        if FLASH_AT <= t < FLASH_AT + FLASH_LEN:
            k = 1 - (t - FLASH_AT) / FLASH_LEN
            x = x + (1.0 - x) * (k ** 2.2) * 0.85

        out = Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8))

        # Titles go on after the grade, so the type stays clean white rather
        # than being pushed around by the look.
        for index, start, length in TITLES:
            if start <= t < start + length:
                card = titles[index]
                which = int(((t - start) / length) * (card.count - 1))
                out = Image.alpha_composite(out.convert("RGBA"), card.at(which)).convert("RGB")

        out.save(os.path.join(FRAMES_OUT, f"f{frame:05d}.png"))
        if frame % 60 == 0:
            print(f"  {t:5.2f}s  {frame}/{total_frames}  {scene_name}", flush=True)

    return total_frames


def encode():
    subprocess.run(
        [
            FF, "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", str(FPS), "-i", os.path.join(FRAMES_OUT, "f%05d.png"),
            "-i", TRACK,
            "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", "-movflags", "+faststart",
            MASTER,
        ],
        check=True,
    )


if __name__ == "__main__":
    if "--encode-only" not in sys.argv:
        print(f"cutting {TOTAL:.1f}s at {FPS}fps")
        build()
    encode()
    print(f"-> {MASTER}")
