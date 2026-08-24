"""Whether a generated frame is worth putting in the cut, and which one is best.

A free image service is not consistent. Asked the same thing twice it returns
a usable photograph and a soft brown smear, and the difference is the seed, not
the prompt - measured across seeds on one brief, edge detail moved by half
again. That makes generating a handful and keeping the best one the cheapest
quality improvement available, but only if "best" can be decided without a
human looking.

So this measures three things that separate the two, all of them cheap:

* **Detail** - the RMS gradient of the luma. A photograph of a rusted steel
  frame has texture everywhere; the failure mode of these models is a soft
  painterly blur, and it shows up here as a number roughly half the good one.
* **Exposure** - how much of the frame is clipped to pure black or pure white.
  A frame that is a third crushed has no shadow detail for the grade to work
  with and no room for the motion pass to push into.
* **Bars** - a return can arrive letterboxed, with black bands baked into the
  pixels, which the renderer would then scale as if they were picture. Cropped
  rather than rejected, because what is between the bands is usually fine. The
  test is deliberately strict - a band counts only if no pixel in it is above
  black - so that a dark sky or a shadowed foreground is never mistaken for
  one and cropped away.

Measured on a fixed-width copy so the numbers mean the same thing whatever the
backend returned, and so the thresholds do not have to move when a better
backend arrives.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

# Everything is measured at this width, so a 1024-wide return and a 1536-wide
# one score on the same scale.
MEASURE_WIDTH = 512

# A bar is a row that is near-black across its whole width. Above pure zero
# because JPEG puts noise in the bands.
BAR_LUMA = 14.0

# Calibrated against real returns: art-directed frames measure 9-20 here and
# the soft failures 5-7. Set under the gap rather than in the middle of it,
# because a wrongly rejected frame costs a round trip and a slightly soft one
# that survives is still better than the blank the chain falls back to.
MIN_DETAIL = 6.5

# Past this the frame has no shadow or highlight left to grade.
MAX_CLIPPED = 0.35

# A frame with less range than this is a flat wash, not a photograph.
MIN_SPREAD = 24.0

# Below this the bars have eaten the picture and there is nothing to keep.
MIN_KEPT_AREA = 0.55

# A print border is a run of near-uniform lines around the whole picture.
BORDER_STD = 9.0        # how flat a line has to be to count as border
BORDER_STEP = 3.0       # how many times more texture the picture has than it
BORDER_MAX = 0.18       # never eat more than this fraction of a side


def _luma(image: Image.Image) -> np.ndarray:
    """Greyscale, at the fixed measuring width."""
    if image.width > MEASURE_WIDTH:
        height = max(1, round(image.height * MEASURE_WIDTH / image.width))
        image = image.resize((MEASURE_WIDTH, height), Image.BILINEAR)
    return np.asarray(image.convert("L"), dtype=np.float32)


def detail(image: Image.Image) -> float:
    """RMS gradient magnitude: how much texture the frame actually carries."""
    luma = _luma(image)
    if luma.size < 4:
        return 0.0
    horizontal = np.diff(luma, axis=1)
    vertical = np.diff(luma, axis=0)
    return float(np.sqrt((horizontal ** 2).mean() + (vertical ** 2).mean()))


def clipped(image: Image.Image) -> float:
    """Fraction of the frame crushed to black or blown to white."""
    luma = _luma(image)
    return float(((luma <= 2.0) | (luma >= 253.0)).mean())


def spread(image: Image.Image) -> float:
    """Tonal range between the 5th and 95th percentile."""
    luma = _luma(image)
    low, high = np.percentile(luma, (5, 95))
    return float(high - low)


def bars(image: Image.Image) -> tuple[int, int, int, int]:
    """Baked-in black bands, as (top, bottom, left, right) in real pixels.

    Measured at full resolution rather than at the width everything else uses.
    Scaling a bar edge back up from a 512-wide map lands it a pixel or two
    short, and the few rows of black that survive are then stretched across
    the finished frame - which is the whole thing this is here to prevent. One
    pass over the array is cheap enough not to trade for that.
    """
    if image.width < 2 or image.height < 2:
        return (0, 0, 0, 0)

    luma = np.asarray(image.convert("L"), dtype=np.float32)
    rows = luma.max(axis=1) > BAR_LUMA
    columns = luma.max(axis=0) > BAR_LUMA
    if not rows.any() or not columns.any():
        return (0, 0, 0, 0)

    def edge(mask: np.ndarray, reverse: bool = False) -> int:
        found = int(np.argmax(mask[::-1] if reverse else mask))
        # A pixel of margin, because JPEG smears the boundary row into
        # something just light enough to read as picture.
        return found + 1 if found else 0

    return (
        edge(rows),
        edge(rows, reverse=True),
        edge(columns),
        edge(columns, reverse=True),
    )


def _uniform_run(lines: np.ndarray, limit: int) -> int:
    """How many lines in from this edge are flat enough to be border."""
    run = 0
    while run < limit and float(lines[run].std()) < BORDER_STD:
        run += 1
    return 0 if run >= limit else run


def border(image: Image.Image) -> tuple[int, int, int, int]:
    """A print or film border around the picture, as (top, bottom, left, right).

    Naming a film stock in the brief can get a photograph *of a print* back,
    paper margin and all, and that margin would otherwise be scaled up and cut
    into the video as if it were part of the shot. It survives being asked not
    to, so it is detected and removed instead of argued with.

    Two conditions, and both are needed. **Every side** has to have a flat run:
    a blown white sky is flat enough to read as border along the top and is
    not one, and a border goes all the way round by definition. And what is
    left inside has to be *much* less flat than the margin - which is one
    check on the picture as a whole rather than four on its edges, because a
    real paper margin does not meet the photograph at the same sharpness on
    every side, and demanding that it does missed the borders that prompted
    this.
    """
    if image.width < 64 or image.height < 64:
        return (0, 0, 0, 0)

    luma = np.asarray(image.convert("L"), dtype=np.float32)
    vertical = int(image.height * BORDER_MAX)
    horizontal = int(image.width * BORDER_MAX)

    top = _uniform_run(luma, vertical)
    bottom = _uniform_run(luma[::-1], vertical)
    left = _uniform_run(luma.T, horizontal)
    right = _uniform_run(luma.T[::-1], horizontal)
    if not all((top >= 2, bottom >= 2, left >= 2, right >= 2)):
        return (0, 0, 0, 0)

    inside = luma[top:luma.shape[0] - bottom, left:luma.shape[1] - right]
    if inside.size < 256 or float(inside.std()) < BORDER_STD * BORDER_STEP:
        return (0, 0, 0, 0)
    return (top, bottom, left, right)


def trim(image: Image.Image) -> Image.Image:
    """The picture with any baked-in bars or print border cropped off.

    Returned unchanged when the bars would take more of the frame than they
    leave: that is not a letterboxed photograph, it is a mostly black one, and
    `usable` should get the chance to say so about the whole frame.
    """
    top, bottom, left, right = bars(image)
    if not (top or bottom or left or right):
        top, bottom, left, right = border(image)
    if not (top or bottom or left or right):
        return image

    box = (left, top, image.width - right, image.height - bottom)
    width, height = box[2] - box[0], box[3] - box[1]
    if width < 16 or height < 16:
        return image
    if (width * height) / float(image.width * image.height) < MIN_KEPT_AREA:
        return image
    return image.crop(box)


def usable(image: Image.Image) -> tuple[bool, str]:
    """Whether this frame can go in the cut at all, and why not if it cannot."""
    if image.width < 256 or image.height < 144:
        return False, "too small to fill a frame"
    if spread(image) < MIN_SPREAD:
        return False, "flat wash, no tonal range"
    if clipped(image) > MAX_CLIPPED:
        return False, "exposure clipped past recovery"
    if detail(image) < MIN_DETAIL:
        return False, "soft, no real texture"
    return True, ""


def score(image: Image.Image) -> float:
    """How good this frame is, for ranking candidates against each other.

    Detail carries the ranking because it is what separates the good returns
    from the bad ones. Clipping only discounts it - a sharp frame with crushed
    shadows still beats a soft one that is perfectly exposed, because the grade
    can lift a little and cannot invent texture.
    """
    return detail(image) * (1.0 - clipped(image)) * min(1.0, spread(image) / 128.0)
