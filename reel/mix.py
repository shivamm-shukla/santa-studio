"""The demo film's sound: a music bed with the real thing on top of it.

The film has no narrator, so three sounds are carrying the entire argument -
the voice sample that went in, the same voice reading a script it has never
seen, and the audio of the film the pipeline actually produced. Those three are
the evidence. The score is there to hold the shape between them, and it has to
get out of the way while any of them is playing, which is what the ducking
below is for.

Expressed as ffmpeg arguments rather than mixed here in numpy, because ffmpeg
is already in the encode and resampling three sources by hand to avoid one
filtergraph would be work for its own sake.

Any element whose file is missing is skipped with a warning rather than being
fatal: the film is worth cutting on a day when the pipeline has not finished,
and a stretch of music is a more honest gap than a crash.
"""

import os

BAR = 1.875

DEMO = "build/demo"
SCORE = os.path.join(DEMO, "score.wav")

# Where each real sound sits, and how long it gets. These line up with the
# cards in reel/demo_edit.py: "sample", then "clone", then the film itself in
# act seven.
PLACEMENT = [
    ("sample", os.path.join(DEMO, "voice", "sample.wav"), BAR * 51 + 0.35, 6.4, 1.5),
    ("clone",  os.path.join(DEMO, "voice", "clone.wav"),  BAR * 55 + 0.35, 7.0, 1.2),
    ("film",   os.path.join(DEMO, "film.mp4"),            BAR * 60 + 0.45, BAR * 12 - 1.2, 1.1),
]

# What the music drops to while something real is playing, and how long it
# takes to get there and back. A hard step in level is more noticeable than
# the thing it is making room for.
DUCK = 0.16
DUCK_EDGE = 0.45


def duck_expression(windows):
    """A volume curve for the music: 1 over the film, DUCK inside each window.

    One expression rather than a chain of enable= filters, because the edges
    have to ramp and an enabled filter switches.
    """
    if not windows:
        return "1"
    ramps = [
        f"min(1,max(0,min((t-{at:.3f})/{DUCK_EDGE},({at + length:.3f}-t)/{DUCK_EDGE})))"
        for at, length in windows
    ]
    deepest = ramps[0]
    for ramp in ramps[1:]:
        deepest = f"max({deepest},{ramp})"
    return f"(1-{1 - DUCK:.3f}*{deepest})"


def audio_arguments(total_seconds, video_inputs=1):
    """ffmpeg arguments for the finished mix.

    `video_inputs` is how many inputs the caller has already added - the demo
    editor pipes raw video in as input 0, so the score lands at input 1 and
    every index here is offset by that. Getting this wrong maps the music to
    the video stream and ffmpeg says something unhelpful about it.
    """
    if not os.path.exists(SCORE):
        print(f"mix: no score at {SCORE} - the film will be silent")
        return []

    inputs = ["-i", SCORE]
    filters = []
    windows = []
    labels = []
    index = video_inputs + 1

    for label, path, at, length, gain in PLACEMENT:
        if not os.path.exists(path):
            print(f"mix: no {label} at {path} - leaving that stretch to the music")
            continue
        inputs.extend(["-i", path])
        delay = int(at * 1000)
        filters.append(
            f"[{index}:a]atrim=0:{length:.3f},asetpts=PTS-STARTPTS,"
            f"adelay={delay}|{delay},volume={gain}[{label}]"
        )
        windows.append((at, length))
        labels.append(label)
        index += 1

    filters.append(
        f"[{video_inputs}:a]atrim=0:{total_seconds:.3f},"
        f"volume='{duck_expression(windows)}':eval=frame[bed]"
    )

    streams = "[bed]" + "".join(f"[{name}]" for name in labels)
    filters.append(
        f"{streams}amix=inputs={1 + len(labels)}:duration=first:normalize=0,"
        f"alimiter=limit=0.95,aresample=44100[mix]"
    )

    return [
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "0:v",
        "-map", "[mix]",
        "-c:a", "aac", "-b:a", "192k",
    ]
