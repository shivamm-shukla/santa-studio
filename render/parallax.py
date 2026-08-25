"""Moving a still as a scene with depth in it, rather than as a flat card.

A Ken Burns move slides every pixel at one rate, which is what a photograph of
a photograph looks like. With a depth map the near parts of the picture can be
made to cross the frame faster than the far parts, and the still starts to
read as a space the camera is moving through.

This is done as a continuous warp - every pixel displaced in proportion to its
own depth - and not by cutting the picture into planes. Planes were tried
first and are wrong for this material: a mine headframe is a steel lattice
spanning most of the depth range, so any threshold runs straight through the
middle of it, and the halves then slide apart. What that looks like is a
photograph of a tower with a ghost of itself beside it. A warp has no
thresholds and so has nothing to tear along.

The displacement is applied backwards - for each output pixel, work out where
to read from - which is what keeps the frame full. A forward displacement
leaves gaps wherever the near parts move away from what was behind them;
reading backwards, every output pixel is always given something, and the worst
that happens at a strong depth edge is that a couple of columns are repeated,
which at these strengths is a pixel or two.

Strength is deliberately small. Parallax is a thing that should be felt and
not noticed: past a certain point the picture stops looking like a scene and
starts looking like a rubber sheet, and the tell is worse than the flat move
it replaced.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

# How much further the nearest pixels travel than the farthest, as a fraction
# of the move itself. A multiplier and not a distance, so that no move means no
# displacement: the first version added a fixed amount in the move's direction,
# which quietly warped a shot that was holding still.
#
# Set by looking. Too much and an estimated depth map - which is not smooth
# along a straight edge - visibly bows a mine headframe's steel. Architecture
# is the hard case, and this is where it stops.
RELIEF = 0.35

# The depth map is smoothed hard before it displaces anything, for the same
# reason: it only has to say roughly how far away things are, and every bit of
# local detail left in it becomes a ripple in a straight line.
SMOOTH = 0.022


def prepare(depth: np.ndarray, size: tuple[int, int]) -> np.ndarray | None:
    """A depth map ready to warp with: smoothed, and 0 far to 1 near."""
    if depth is None:
        return None

    width, height = size
    if depth.shape[:2] != (height, width):
        resized = Image.fromarray((np.clip(depth, 0, 1) * 255).astype(np.uint8)).resize(
            (width, height), Image.BILINEAR
        )
        depth = np.asarray(resized, dtype=np.float32) / 255.0

    radius = max(1.0, min(width, height) * SMOOTH)
    smoothed = Image.fromarray((np.clip(depth, 0, 1) * 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(radius)
    )
    prepared = np.asarray(smoothed, dtype=np.float32) / 255.0

    span = float(prepared.max() - prepared.min())
    if span <= 1e-6:
        return None
    return (prepared - prepared.min()) / span


def warp(image: Image.Image, depth: np.ndarray, offset, zoom: float = 1.0) -> Image.Image:
    """`image` seen from a camera moved by `offset`, with `depth` giving relief.

    `offset` is in pixels and is what the *far* distance does; nearer pixels
    move further than that, and push in harder, both in proportion to RELIEF.
    """
    source = np.asarray(image.convert("RGB"), dtype=np.float32)
    height, width = source.shape[:2]
    if depth is None or depth.shape[:2] != (height, width):
        return image

    offset_x, offset_y = offset
    ys, xs = np.mgrid[0:height, 0:width].astype(np.float32)

    # Everything is expressed as where to *read from*, so the output is always
    # fully covered whatever the move.
    centre_x, centre_y = (width - 1) / 2.0, (height - 1) / 2.0

    # Near pixels are pushed in harder than far ones, which is what moving
    # through a real scene does - and on the moves this pipeline actually
    # makes, most of which are push-ins, it is the larger half of the effect.
    relief = 1.0 + depth * RELIEF
    local_zoom = np.maximum(1.0 + (zoom - 1.0) * relief, 1e-6)
    xs = centre_x + (xs - centre_x) / local_zoom
    ys = centre_y + (ys - centre_y) / local_zoom

    # And they travel further across the frame, in proportion to the move.
    xs = xs - offset_x * relief
    ys = ys - offset_y * relief

    np.clip(xs, 0, width - 1, out=xs)
    np.clip(ys, 0, height - 1, out=ys)

    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    fx = (xs - x0)[:, :, None]
    fy = (ys - y0)[:, :, None]

    # Bilinear, because nearest-neighbour on a slow move shows the picture
    # stepping a pixel at a time, which is its own kind of tell.
    top = source[y0, x0] * (1 - fx) + source[y0, x1] * fx
    bottom = source[y1, x0] * (1 - fx) + source[y1, x1] * fx
    blended = top * (1 - fy) + bottom * fy

    return Image.fromarray(np.clip(blended, 0, 255).astype(np.uint8))
