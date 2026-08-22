"""Ken Burns geometry: which part of a source is on screen at a given moment.

Kept apart from the renderer because it is pure arithmetic, and because a
motion bug is otherwise only visible by watching the output. Everything here
takes numbers and returns numbers.

Two coordinate systems meet in this file. A Motion's rectangles are normalised
to 0..1 so a move survives a change of output resolution. Pillow wants pixel
boxes as (left, upper, right, lower). The translation happens in `crop_box`,
which is the function the renderer actually calls.

Fitting happens before motion. A 4:3 photograph in a 16:9 frame is first
reduced to the largest centred 16:9 region of that photograph - that is the
`cover` box - and the motion rectangle then moves around inside it. Doing it
the other way round lets a pan wander onto the letterbox bars.
"""

from __future__ import annotations

Rect = tuple[float, float, float, float]
Box = tuple[int, int, int, int]


# --------------------------------------------------------------------------
# Easing
# --------------------------------------------------------------------------

def ease(progress: float, kind: str = "ease_in_out") -> float:
    """Maps linear 0..1 progress onto an eased 0..1 curve.

    A Ken Burns move at a constant speed starts and stops abruptly, which reads
    as mechanical. Easing in and out is what makes the same move look like a
    camera rather than a slider, so it is the default.
    """
    progress = max(0.0, min(1.0, progress))
    if kind == "linear":
        return progress
    if kind == "ease_in":
        return progress * progress
    if kind == "ease_out":
        return 1 - (1 - progress) ** 2
    # ease_in_out
    if progress < 0.5:
        return 2 * progress * progress
    return 1 - ((-2 * progress + 2) ** 2) / 2


def lerp_rect(start: Rect, end: Rect, progress: float) -> Rect:
    """Interpolates between two normalised rectangles."""
    return tuple(a + (b - a) * progress for a, b in zip(start, end))  # type: ignore[return-value]


# --------------------------------------------------------------------------
# Fitting
# --------------------------------------------------------------------------

def cover_box(source: tuple[int, int], output: tuple[int, int]) -> Box:
    """The largest centred region of `source` matching `output`'s aspect ratio.

    This is what stops the stretched, squashed look: the source is cropped to
    the target shape rather than being scaled to it.
    """
    source_width, source_height = source
    output_width, output_height = output
    if source_width <= 0 or source_height <= 0:
        raise ValueError(f"Bad source size {source}")

    target_aspect = output_width / output_height
    source_aspect = source_width / source_height

    if source_aspect > target_aspect:
        # Source is wider than the frame; trim the sides.
        width = int(round(source_height * target_aspect))
        height = source_height
    else:
        width = source_width
        height = int(round(source_width / target_aspect))

    left = (source_width - width) // 2
    upper = (source_height - height) // 2
    return (left, upper, left + width, upper + height)


def contain_box(source: tuple[int, int], output: tuple[int, int]) -> Box:
    """The whole source. Letterboxing is the renderer's job, not this one's."""
    return (0, 0, source[0], source[1])


# --------------------------------------------------------------------------
# The one the renderer calls
# --------------------------------------------------------------------------

def crop_box(
    source: tuple[int, int],
    output: tuple[int, int],
    motion=None,
    progress: float = 0.0,
    fit: str = "cover",
) -> Box:
    """The pixel box of `source` that fills the frame at `progress` (0..1).

    With no motion this is simply the fit box, which is why a static shot and a
    moving one go down the same path.
    """
    base = cover_box(source, output) if fit == "cover" else contain_box(source, output)
    if motion is None or getattr(motion, "is_static", False):
        return base

    eased = ease(progress, getattr(motion, "easing", "ease_in_out"))
    x, y, width, height = lerp_rect(tuple(motion.start_rect), tuple(motion.end_rect), eased)

    base_left, base_upper, base_right, base_lower = base
    base_width = base_right - base_left
    base_height = base_lower - base_upper

    left = base_left + x * base_width
    upper = base_upper + y * base_height
    right = left + width * base_width
    lower = upper + height * base_height

    return _clamp(
        (int(round(left)), int(round(upper)), int(round(right)), int(round(lower))),
        source,
    )


def _clamp(box: Box, source: tuple[int, int]) -> Box:
    """Keeps a box inside the source and at least one pixel across.

    Rounding at the edges of a move can push a box a pixel past the boundary,
    and Pillow will happily produce a black border rather than complain.
    """
    source_width, source_height = source
    left, upper, right, lower = box

    left = max(0, min(left, source_width - 1))
    upper = max(0, min(upper, source_height - 1))
    right = max(left + 1, min(right, source_width))
    lower = max(upper + 1, min(lower, source_height))
    return (left, upper, right, lower)


# --------------------------------------------------------------------------
# Building moves from a style profile
# --------------------------------------------------------------------------

def build_motion(style, rng):
    """Invents a Ken Burns move within the limits a MotionStyle allows.

    The rectangle is a fraction of the *fit* box, which already has the
    output's shape, so using the same fraction for width and height keeps the
    aspect ratio correct without any special handling.

    Both the direction of travel and whether the shot pushes in or pulls out
    are randomised. A run of stills that all drift the same way is its own kind
    of obviously-generated.
    """
    from timeline import Motion

    zoom = rng.uniform(0.35, 1.0) * style.max_zoom * style.intensity
    pan = rng.uniform(0.0, 1.0) * style.max_pan * style.intensity

    wide: Rect = (0.0, 0.0, 1.0, 1.0)
    size = max(0.2, 1.0 - zoom)

    # How far a tight rectangle of this size can travel without leaving the box.
    room = 1.0 - size
    pan = min(pan, room)
    origin_x = rng.uniform(0, max(0.0, room - pan))
    origin_y = rng.uniform(0, max(0.0, room - pan))

    direction_x, direction_y = rng.choice(
        [(1, 0), (0, 1), (1, 1), (-1, 0), (0, -1), (-1, -1)]
    )
    end_x = min(max(origin_x + direction_x * pan, 0.0), room)
    end_y = min(max(origin_y + direction_y * pan, 0.0), room)

    if rng.random() < 0.5:
        # Push in: start on the whole box, end tight.
        return Motion(start_rect=wide, end_rect=(end_x, end_y, size, size), easing=style.easing)
    # Pull out: start tight, end on the whole box.
    return Motion(start_rect=(origin_x, origin_y, size, size), end_rect=wide, easing=style.easing)
