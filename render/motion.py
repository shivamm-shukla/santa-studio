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

# How far a move travels per second on screen, before the style's intensity
# scales it. Written as a rate rather than as a per-shot amount because that
# is what the eye reads: the same travel across two seconds and across seven
# is a whip and a drift, and the old code gave a two-second cut the same
# distance as a long one.
ZOOM_PER_SECOND = 0.035
PAN_PER_SECOND = 0.022

# Assumed length when the caller does not say. Roughly the default cut.
NOMINAL_SECONDS = 4.0

# How often a move neither starts nor ends on the whole frame - a slow drift
# inside a crop, with no zoom at all. Every move used to have (0, 0, 1, 1) at
# one end, which meant every still was shown whole at one end of its shot and
# every push-in ran the full distance available. A camera does not do that.
DRIFT_SHARE = 0.35

# The crop a drift lives inside. Tight enough to have somewhere to go.
DRIFT_INSET = 0.12

DIRECTIONS = ((1, 0), (0, 1), (1, 1), (-1, 0), (0, -1), (-1, -1), (1, -1), (-1, 1))


def travel_direction(motion) -> tuple[float, float]:
    """Which way a move travels, from the centres of its two rectangles."""
    if motion is None:
        return (0.0, 0.0)
    start_x, start_y, start_w, start_h = motion.start_rect
    end_x, end_y, end_w, end_h = motion.end_rect
    return (
        (end_x + end_w / 2) - (start_x + start_w / 2),
        (end_y + end_h / 2) - (start_y + start_h / 2),
    )


def _pick_direction(rng, previous):
    """A direction, preferring one that does not continue the last shot's.

    Consecutive stills drifting the same way is its own tell - it reads as one
    long move chopped up rather than as separate shots. Preferring rather than
    forbidding, because with a strong previous direction fewer than half the
    options are left and always taking one of those is its own pattern.
    """
    last_x, last_y = travel_direction(previous)
    if last_x or last_y:
        against = [d for d in DIRECTIONS if d[0] * last_x + d[1] * last_y <= 0]
        if against:
            return against[rng.randrange(len(against))]
    return DIRECTIONS[rng.randrange(len(DIRECTIONS))]


def _rect(centre_x: float, centre_y: float, size: float) -> Rect:
    """A square-fraction rectangle of `size` about a centre, kept inside the box."""
    half = size / 2.0
    centre_x = min(max(centre_x, half), 1.0 - half)
    centre_y = min(max(centre_y, half), 1.0 - half)
    return (centre_x - half, centre_y - half, size, size)


def build_motion(style, rng, duration: float | None = None, previous=None):
    """Invents a Ken Burns move within the limits a MotionStyle allows.

    Built from two centres and two sizes rather than from two rectangles. The
    rectangle form let a diagonal move apply the full pan to *both* axes, so
    the centre travelled about 1.41 times `max_pan` - a ceiling the style says
    it sets and did not. Going through the centre means the distance travelled
    is the distance asked for, whichever way it goes.

    How far it travels comes from how long the shot is on screen, capped by the
    style. Which way it travels avoids repeating the previous shot's direction.
    Both are optional so a caller with neither still gets a sane move.
    """
    from timeline import Motion

    seconds = NOMINAL_SECONDS if not duration or duration <= 0 else float(duration)

    zoom = min(style.max_zoom, ZOOM_PER_SECOND * seconds) * style.intensity
    zoom *= rng.uniform(0.6, 1.0)
    pan = min(style.max_pan, PAN_PER_SECOND * seconds) * style.intensity
    pan *= rng.uniform(0.4, 1.0)

    direction_x, direction_y = _pick_direction(rng, previous)
    length = (direction_x ** 2 + direction_y ** 2) ** 0.5 or 1.0
    direction_x, direction_y = direction_x / length, direction_y / length

    if rng.random() < DRIFT_SHARE:
        # A drift: one crop throughout, moved. No zoom, and the whole frame is
        # never shown - which is what stops a run of stills reading as a
        # slideshow with an effect on it.
        start_size = end_size = 1.0 - DRIFT_INSET
    elif rng.random() < 0.5:
        start_size, end_size = 1.0, max(0.2, 1.0 - zoom)   # push in
    else:
        start_size, end_size = max(0.2, 1.0 - zoom), 1.0   # pull out

    # A rectangle can only travel half of what its size leaves spare, since it
    # is clamped inside the box at both ends. The tighter of the two decides.
    room = min(1.0 - start_size, 1.0 - end_size) / 2.0
    pan = min(pan, room)

    start_x = 0.5 - direction_x * pan / 2.0
    start_y = 0.5 - direction_y * pan / 2.0
    end_x = start_x + direction_x * pan
    end_y = start_y + direction_y * pan

    return Motion(
        start_rect=_rect(start_x, start_y, start_size),
        end_rect=_rect(end_x, end_y, end_size),
        easing=style.easing,
    )
