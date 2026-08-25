"""One look over the whole video, applied where it costs nothing.

A finished run cuts a Pexels clip against a generated still against a Commons
photograph, and each arrives with its own colour, contrast and grain. The
picture visibly changes character at every cut, and that - more than the cuts
themselves - is what makes an edit feel stuck together out of parts rather
than filmed. The fix is the one a colourist would use: grade everything to the
same look at the end, so the sources stop announcing themselves.

It has to reach *every* frame, stock footage included, which nothing in the
asset pipeline ever touches. So it belongs to the render, and the render
already goes out through ffmpeg.

Doing it in Python was tried and abandoned: a frame of 1080p is six million
values, and even in integer arithmetic the pass measured 75 milliseconds a
frame - four and a half minutes added to a two-minute video for something
nobody is meant to notice. The same operations exist as ffmpeg filters, in C,
inside the encoder that is running anyway, where they cost a few per cent of
an encode that has to happen regardless.

What the look does, and why each part is here:

* **curves** - blacks lifted off zero and a gentle S. Digital black at zero is
  most of what separates footage that looks rendered from footage that looks
  photographed, and it is the single biggest thing the sources disagree about.
* **eq** - saturation pulled back slightly. Saturated stock next to a neutral
  still is the other loud mismatch.
* **vignette** - a lens has one; four different sources have four different
  ones, or none.
* **noise** - a single grain over everything. Two clips with different grain
  read as two clips; one grain over both reads as one film.

Deliberately gentle. This is here to make sources agree with each other, not
to impose a style, and a viewer who notices the grade has been given the wrong
amount of it.
"""

from __future__ import annotations

# Lift the shadows and put a gentle S through the midtones. Written as control
# points on the standard curve: black is lifted to 4/255, and the two mid
# points bend the curve either side of centre.
CURVES = "0/0.03 0.25/0.245 0.5/0.5 0.75/0.755 1/1"

SATURATION = 0.95

VIGNETTE_ANGLE = "PI/5"     # gentle; PI/4 is a heavy 1970s falloff

# ffmpeg's noise strength runs 0-100. Anything past about 12 reads as a
# damaged tape rather than as film.
GRAIN = 6


def filter_chain() -> str:
    """The look, as an ffmpeg -vf filtergraph.

    Order matters more than it looks. The lift on the blacks has to come
    *last*, because everything else can undo it: `eq` round-trips through
    limited-range YUV where black is 16 rather than 0, so a lift of three
    levels applied before it comes back out as zero, and the vignette then
    multiplies whatever is left towards nothing at the corners. Measured on a
    black frame, the same chain in the obvious order delivered a mean of 0.2
    where the curve asked for 8.

    `eq` also has no contrast term any more, for the same reason: its contrast
    is computed about mid-grey, so on limited-range black it pushes below the
    floor and clips. The S it was providing is in the curve, where it belongs.
    """
    return ",".join((
        f"eq=saturation={SATURATION}",
        f"vignette=angle={VIGNETTE_ANGLE}",
        # `alls` keeps the grain the same in all three channels, which is what
        # luma grain looks like; `t` makes it move frame to frame, which is
        # what stops it reading as dirt on the lens.
        f"noise=alls={GRAIN}:allf=t",
        f"curves=all='{CURVES}'",
    ))


def ffmpeg_params() -> list[str]:
    """The arguments MoviePy should pass through to the encoder."""
    return ["-vf", filter_chain()]
