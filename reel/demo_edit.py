"""Cuts the demo film together and encodes it in one pass.

The short reel's editor wrote every finished frame to disk and then encoded the
directory. At three minutes and 1080x1920 that is about ten gigabytes of PNG,
which is how the disk came to be full enough to take a pipeline run down with
it. So this one never writes a frame: it composes into an array and pipes raw
video straight into ffmpeg, which is both faster and bounded.

The edit itself is the same idea as the reel's - a loop over frames, because
the interesting parts of an edit are per frame - with two things it did not
need.

  Sections. Three minutes cannot look the same throughout. Each act gets its
  own grade: the cold open is cold and crushed, the studio is warm, the voice
  section goes quiet and neutral so the picture stops competing with what you
  are listening to, and the close warms up again into the end card.

  A mix. There is a music bed, and over it the real voice sample, the real
  cloned line, and the real film's audio - each ducking the music while it
  plays, because this film has no narrator and those three sounds are the only
  evidence that any of it works. See reel/mix.py.

    python -m reel.demo_edit
"""

import os
import subprocess
import sys

import numpy as np
from PIL import Image

FPS = 30
W, H = 1080, 1920
BAR = 1.875

DEMO = "build/demo"
TITLES = os.path.join(DEMO, "titles")
MASTER = "santa_studio_demo.mp4"

FF = "venv/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"


def bars(n):
    return n * BAR


# --- the cut ---------------------------------------------------------------
#
# (start bar, end bar, scene, where in that scene to start, grade).
# Nothing is retimed: every scene was filmed at thirty for exactly this.

CUT = [
    # The tour is 93.75s long and the film asks for more studio than that, so
    # the acts overlap it - each one starting on the shot that act is about.
    # Its shots begin at: arrive 0.0, pass 3.75, raise 7.5, orbit 13.125,
    # descend 28.125, board-in 31.875, board-hold 35.625, desk 41.25,
    # desk-two 46.875, rack 50.625, booth-in 56.25, mic 63.75, tv-in 71.25,
    # tv-hold 75.0, back-out 82.5, crane 86.25.

    # act 1 - a dark desk, a machine asleep
    (0,  4,  "laptop", 0.0,    "cold"),
    # act 2 - it wakes, and the site is on it
    (4,  8,  "laptop", 7.5,    "wake"),
    # act 3 - into the studio: arrival, the lights coming up, the full turn
    (8,  20, "tour",   0.0,    "night"),
    (20, 28, "tour",   22.5,   "warm"),
    # act 4 - the brief, on the board
    (28, 36, "tour",   35.625, "warm"),
    # act 5 - the work, at the desks
    (36, 48, "tour",   41.25,  "work"),
    # act 6 - the voice: into the booth, round the microphone
    (48, 60, "tour",   56.25,  "quiet"),
    # act 7 - the film it made, on the same laptop the demo opened on
    (60, 72, "film",   0.0,    "screen"),
    # act 8 - shorts, on the television
    (72, 84, "tour",   71.25,  "warm"),
    # act 9 - out, and the crane
    (84, 92, "tour",   78.75,  "close"),
]

TOTAL_BARS = CUT[-1][1]
TOTAL = bars(TOTAL_BARS)

# --- the look --------------------------------------------------------------
#
# Small numbers on purpose: a grade that announces itself is one you will be
# tired of by the second act.

LOOKS = {
    "cold":   dict(lift=0.010, gamma=1.10, sat=0.80, warm=-0.010, cool=0.030, vig=0.40),
    "wake":   dict(lift=0.016, gamma=1.02, sat=0.96, warm=0.012,  cool=0.014, vig=0.32),
    "night":  dict(lift=0.014, gamma=1.06, sat=0.88, warm=0.004,  cool=0.024, vig=0.36),
    "warm":   dict(lift=0.022, gamma=0.98, sat=1.04, warm=0.026,  cool=0.008, vig=0.26),
    "work":   dict(lift=0.020, gamma=1.00, sat=0.98, warm=0.016,  cool=0.014, vig=0.28),
    "quiet":  dict(lift=0.024, gamma=1.00, sat=0.90, warm=0.010,  cool=0.010, vig=0.22),
    "screen": dict(lift=0.012, gamma=0.99, sat=1.06, warm=0.014,  cool=0.010, vig=0.20),
    "close":  dict(lift=0.026, gamma=0.97, sat=1.02, warm=0.030,  cool=0.006, vig=0.30),
}

# --- the script ------------------------------------------------------------
#
# (card id, start in seconds). Length comes from the card's own footage, which
# was filmed at the length src/titles/cards.js says it runs for.

CARDS = [
    ("open",    0.60),
    ("promise", bars(4) + 0.20),
    ("site",    bars(6) + 0.10),
    ("place",   bars(10) + 0.20),
    ("c1",      bars(28) + 0.15),
    ("c1b",     bars(32) + 0.15),
    ("c2",      bars(36) + 0.15),
    ("c3",      bars(40) + 0.15),
    ("c3b",     bars(44) + 0.15),
    ("c4",      bars(48) + 0.15),
    ("sample",  bars(51) + 0.10),
    ("clone",   bars(55) + 0.10),
    ("credit",  bars(58) + 0.10),
    ("c5",      bars(60) + 0.15),
    ("deliver", bars(68) + 0.10),
    ("c6",      bars(72) + 0.15),
    ("clips2",  bars(76) + 0.15),
    ("clips3",  bars(80) + 0.15),
    ("end",     bars(88) + 0.30),
]

# Cross fades at the act joins that change place. Everything else is a cut.
DISSOLVE = {8: 0.30, 20: 0.22, 60: 0.28, 72: 0.24, 84: 0.22}
# One frame of light where the machine wakes, on the downbeat.
FLASH_AT = bars(4)
FLASH_LEN = 0.09


class Sequence:
    """Frames on disk, read a few at a time."""

    def __init__(self, path, ext):
        self.dir = path
        self.ext = ext
        self.count = len([f for f in os.listdir(path) if f.endswith(ext)])
        self._cache = {}

    def at_index(self, index):
        index = max(0, min(self.count - 1, index))
        if index in self._cache:
            return self._cache[index]
        image = Image.open(os.path.join(self.dir, f"f{index:05d}{self.ext}"))
        image = image.convert("RGBA" if self.ext == ".png" else "RGB")
        if image.size != (W, H):
            image = image.resize((W, H), Image.LANCZOS)
        if len(self._cache) > 4:
            self._cache.pop(next(iter(self._cache)))
        self._cache[index] = image
        return image

    def at(self, seconds):
        return self.at_index(int(round(seconds * FPS)))


def shot_at(t):
    """Which entry of the cut is on screen, and where in its footage."""
    bar = min(TOTAL_BARS - 1, int(t / BAR))
    for start, end, scene, offset, look in CUT:
        if start <= bar < end:
            return start, scene, offset + (t - bars(start)), look
    start, end, scene, offset, look = CUT[-1]
    return start, scene, offset + (t - bars(start)), look


VIG = {}


def vignette(strength):
    if strength not in VIG:
        yy, xx = np.mgrid[0:H, 0:W]
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / np.sqrt(2)
        VIG[strength] = (1 - strength * r ** 2.1)[..., None].astype(np.float32)
    return VIG[strength]


GRAIN = None


def grain(frame):
    global GRAIN
    if GRAIN is None:
        rng = np.random.default_rng(11)
        GRAIN = rng.normal(0, 1, (8, H, W, 1)).astype(np.float32)
    return GRAIN[frame % 8]


def grade(array, look):
    p = LOOKS[look]
    x = array.astype(np.float32) / 255.0

    x = p["lift"] + x * (1.0 - p["lift"] * 1.6)
    x = np.clip(x, 1e-4, 1)
    x = x ** p["gamma"]

    # A soft S, then pull the colour back towards the section's saturation.
    x = x * x * (3 - 2 * x) * 0.42 + x * 0.58
    grey = x.mean(axis=2, keepdims=True)
    x = grey + (x - grey) * p["sat"]

    x[..., 0] += (x[..., 0] ** 2) * p["warm"]
    x[..., 2] += ((1 - x[..., 2]) ** 2) * p["cool"]
    return x


def compose(frame, scenes, cards):
    t = frame / FPS
    start_bar, scene_name, offset, look = shot_at(t)
    picture = scenes[scene_name].at(offset)

    fade = DISSOLVE.get(start_bar)
    if fade and 0 <= t - bars(start_bar) < fade:
        for s, e, prev_scene, prev_offset, _ in CUT:
            if e == start_bar:
                behind = scenes[prev_scene].at(prev_offset + (t - bars(s)))
                picture = Image.blend(behind, picture, (t - bars(start_bar)) / fade)
                break

    x = grade(np.asarray(picture, dtype=np.uint8), look)
    x *= vignette(LOOKS[look]["vig"])
    x += grain(frame) * 0.005

    if FLASH_AT <= t < FLASH_AT + FLASH_LEN:
        k = 1 - (t - FLASH_AT) / FLASH_LEN
        x = x + (1.0 - x) * (k ** 2.2) * 0.8

    out = Image.fromarray((np.clip(x, 0, 1) * 255).astype(np.uint8))

    # Type goes on after the grade, so it stays the white it was set in.
    for card_id, start in CARDS:
        card = cards.get(card_id)
        if card is None or card.count == 0:
            continue
        if start <= t < start + card.count / FPS:
            out = Image.alpha_composite(
                out.convert("RGBA"), card.at_index(int((t - start) * FPS))
            ).convert("RGB")

    return np.asarray(out, dtype=np.uint8)


def load(scenes_wanted):
    scenes = {}
    for name in scenes_wanted:
        path = os.path.join(DEMO, name)
        if not os.path.isdir(path) or not os.listdir(path):
            sys.exit(f"missing footage: {path}")
        ext = ".jpg" if any(f.endswith(".jpg") for f in os.listdir(path)) else ".png"
        scenes[name] = Sequence(path, ext)
    return scenes


def build(audio_args):
    scenes = load({c[2] for c in CUT})
    cards = {}
    for card_id, _ in CARDS:
        path = os.path.join(TITLES, card_id)
        cards[card_id] = Sequence(path, ".png") if os.path.isdir(path) else None

    total_frames = int(TOTAL * FPS)
    print(f"cutting {TOTAL:.1f}s / {total_frames} frames")

    command = [
        FF, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        *audio_args,
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-shortest",
        MASTER,
    ]
    ff = subprocess.Popen(command, stdin=subprocess.PIPE)

    for frame in range(total_frames):
        ff.stdin.write(compose(frame, scenes, cards).tobytes())
        if frame % 150 == 0:
            print(f"  {frame / FPS:6.1f}s  {frame}/{total_frames}", flush=True)

    ff.stdin.close()
    if ff.wait() != 0:
        sys.exit("encode failed")
    print(f"-> {MASTER}")


if __name__ == "__main__":
    from reel.mix import audio_arguments

    build(audio_arguments(TOTAL))
