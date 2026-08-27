"""The corner mark a video carries when there is no commercial grant.

Deliberately light. A mark that ruins the video it is on teaches people to
strip it; one that sits quietly in the corner is a credit, which is what this
is meant to be. The size is a fraction of the frame rather than a pixel count,
so it reads the same on a 1080p master and on a vertical short.

Drawn here rather than handed to ffmpeg as a filter because the logo is a
shape, not a font, and because a PIL image composites the same way every other
overlay in this renderer does.

See licence.py for what turns it off, and for an honest account of what that
check can and cannot enforce.
"""

from __future__ import annotations

import os

ACCENT = (255, 107, 53)          # the brand orange, as in room/src/theme.js

# The logo's S, straight out of assets/logo/santa-studio-logo.svg: the chain of
# cubic beziers from that file's path, in its 100x100 coordinate space. Sampled
# into a polyline here rather than pulling in an SVG renderer for one shape.
# Drawn from primitives instead, it came out reading as a C in a circle, which
# is a different logo.
LOGO_BOX = 100.0
LOGO_RING = (4, 4, 96, 96)       # cx 50, cy 50, r 46
LOGO_S = [
    ((71, 32), (71, 22.5), (59, 19.5), (49.5, 21)),
    ((49.5, 21), (38, 22.8), (31.5, 29), (33.3, 35.2)),
    ((33.3, 35.2), (35.1, 41.4), (44.5, 43.3), (53, 46.6)),
    ((53, 46.6), (62.5, 50), (74, 53.3), (72.3, 61.5)),
    ((72.3, 61.5), (70.5, 71), (59, 75.7), (47.5, 74.3)),
    ((47.5, 74.3), (39.5, 73.3), (33, 68.7), (31, 61.8)),
]


def _bezier(p0, p1, p2, p3, steps=18):
    """A cubic segment as points."""
    out = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        out.append((
            u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
            u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
        ))
    return out


def _logo_points(left: float, top: float, size: float) -> list[tuple[float, float]]:
    """The S, scaled into a `size` box with its corner at (left, top)."""
    scale = size / LOGO_BOX
    points = []
    for segment in LOGO_S:
        for x, y in _bezier(*segment):
            point = (left + x * scale, top + y * scale)
            if not points or point != points[-1]:
                points.append(point)
    return points
WORDMARK = "made with Santa Studio"

# Fractions of the frame height, so a short and a master carry the same mark.
MARK_HEIGHT = 0.034
MARGIN = 0.022
OPACITY = 0.72


def _font(size: int):
    from PIL import ImageFont

    try:
        import render.fonts as fonts

        path = fonts.resolve("Made with Santa Studio")
        if path:
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    try:
        return ImageFont.load_default(size)
    except TypeError:
        # Pillow before 10.1 has no size argument on the default font.
        return ImageFont.load_default()


def image(width: int, height: int):
    """The mark for a frame of this size, as an RGBA PIL image."""
    from PIL import Image, ImageDraw

    mark = max(18, int(height * MARK_HEIGHT))
    pad = max(10, int(height * MARGIN))
    size = int(mark * 1.15)
    text_size = int(mark * 0.62)

    font = _font(text_size)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    text_width = int(draw.textlength(WORDMARK, font=font))
    total = size + int(mark * 0.42) + text_width
    left = width - pad - total
    top = height - pad - size

    ink = ACCENT + (int(255 * OPACITY),)
    scale = size / LOGO_BOX

    # The ring, at the SVG's own radius and stroke weight.
    ring = max(2, round(5 * scale))
    draw.ellipse(
        [left + LOGO_RING[0] * scale, top + LOGO_RING[1] * scale,
         left + LOGO_RING[2] * scale, top + LOGO_RING[3] * scale],
        outline=ink,
        width=ring,
    )

    # The S. joint="curve" is what keeps a thick polyline from showing its
    # corners at this size.
    stroke = max(2, round(10 * scale))
    draw.line(_logo_points(left, top, size), fill=ink, width=stroke, joint="curve")
    # PIL squares off the ends of a line; the logo's are round.
    points = _logo_points(left, top, size)
    for x, y in (points[0], points[-1]):
        r = stroke / 2
        draw.ellipse([x - r, y - r, x + r, y + r], fill=ink)

    # White words carried on a dark outline rather than a drop shadow. A shadow
    # holds them over a dark shot and loses them over a bright one, and a mark
    # that disappears against the sky is not a mark. An outline works on both
    # without needing a plate behind it.
    tx = left + size + int(mark * 0.42)
    ty = top + (size - text_size) / 2 - text_size * 0.08
    draw.text(
        (tx, ty),
        WORDMARK,
        font=font,
        fill=(255, 255, 255, int(245 * OPACITY)),
        stroke_width=max(1, round(text_size * 0.09)),
        stroke_fill=(0, 0, 0, int(190 * OPACITY)),
    )

    return canvas


def clip(width: int, height: int, duration: float):
    """The mark as a MoviePy clip covering the whole video, or None.

    None when there is a commercial grant, which is the only thing that turns
    this off.
    """
    import licence

    if not licence.marks_output():
        return None

    import numpy as np
    from moviepy import ImageClip

    return ImageClip(np.array(image(width, height)), is_mask=False).with_duration(duration)


def burn_into(video_path: str) -> str:
    """Stamps an already-rendered file in place, for output the timeline
    renderer never saw - a short cut straight out of a master, for instance.

    Returns the path either way, so a caller can use it unconditionally.
    """
    import licence

    if not licence.marks_output():
        return video_path

    from PIL import Image

    from render.base import ensure_ffmpeg_on_path

    ensure_ffmpeg_on_path()
    import subprocess

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video_path],
        capture_output=True, text=True,
    )
    try:
        width, height = (int(v) for v in probe.stdout.strip().split("x")[:2])
    except ValueError:
        return video_path

    stamp = f"{os.path.splitext(video_path)[0]}.mark.png"
    Image.fromarray(__import__("numpy").array(image(width, height))).save(stamp)

    marked = f"{os.path.splitext(video_path)[0]}.marked.mp4"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-i", stamp,
         "-filter_complex", "[0:v][1:v]overlay=0:0",
         "-c:a", "copy", "-preset", "veryfast", marked],
        capture_output=True, text=True,
    )
    try:
        os.remove(stamp)
    except OSError:
        pass

    if result.returncode != 0 or not os.path.exists(marked):
        return video_path
    os.replace(marked, video_path)
    return video_path
