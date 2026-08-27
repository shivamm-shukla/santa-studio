"""Renders a Timeline with MoviePy.

Everything this file does is dictated by the Timeline it is handed. It makes no
editorial decisions of its own - no picking durations, no choosing what a scene
should show. That separation is the point: the same Timeline rendered twice
produces the same video, and the decisions live somewhere they can be inspected
and edited.

MoviePy is the first implementation rather than the final one. It is convenient
and it is slow, and on a long video the slowness will eventually matter enough
to justify an FFmpeg filtergraph renderer. When that happens this file is what
gets replaced, and nothing upstream of it changes.

Two structural choices worth knowing about:

* Shots are composited at their absolute start times rather than concatenated.
  Concatenation derives each shot's position from the lengths of the ones
  before it, so a rounding error anywhere shifts everything after it. The
  Timeline has already been validated to tile the video exactly, so honouring
  its start times directly keeps picture and audio locked together.

* A dissolve is done by letting the outgoing shot run past its own end
  underneath the incoming one, which fades in over it. That keeps every shot's
  declared start time intact - the alternative, overlapping the clips, would
  mean the rendered timing no longer matches the document that describes it.
"""

from __future__ import annotations

import os
from multiprocessing import cpu_count
from typing import Callable

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from render import audio_mix, fonts
from render.base import Renderer, register
from render import grade, parallax
from render.motion import crop_box

# Anything longer than this on a still is rendered frame by frame through
# Pillow. Below it, a plain static clip is far cheaper and looks identical.
_STATIC_IMAGE_FAST_PATH = True


def _load_image(path: str):
    from PIL import Image

    image = Image.open(path)
    # Some stock JPEGs carry an orientation tag; ignoring it renders them
    # rotated, which is the sort of thing nobody notices until export.
    try:
        from PIL import ImageOps

        image = ImageOps.exif_transpose(image)
    except Exception:
        pass
    return image.convert("RGB")


def _directional_blur(frame, pixels: int):
    """A horizontal smear, the way a camera whipped sideways records one.

    Done by averaging shifted copies rather than by convolving a kernel, with
    the number of copies following the width of the smear. A fixed count does
    not survive a hard whip: eight copies spread across sixty pixels of a
    detailed frame reads as eight ghosts of the picture rather than as one
    smear of it, which is worse than no effect at all. Sampling every couple of
    pixels costs nothing at the few frames per cut this runs on.
    """
    import numpy as np

    pixels = int(abs(pixels))
    if pixels < 2:
        return frame

    taps = max(4, min(32, pixels // 2))
    accumulated = np.zeros(frame.shape, dtype=np.float32)
    for step in range(taps):
        offset = round(-pixels / 2 + pixels * step / (taps - 1))
        accumulated += np.roll(frame, offset, axis=1).astype(np.float32)
    return (accumulated / taps).astype(frame.dtype)


def _whip_in(clip, length: float):
    """The incoming shot arriving as if the camera whipped onto it.

    A whip is two things at once and both are needed: the picture is smeared
    along the direction of travel, and it settles into place from off to one
    side. Blur alone reads as a focus pull; a slide alone reads as a slideshow.
    Both were previously a dissolve, which reads as neither.

    The smear is heaviest at the start of the transition and gone by its end,
    which is where the eye expects it - a whip decelerates onto its subject.
    """
    if length <= 0:
        return clip

    width = clip.size[0]
    travel = width * 0.18
    strength = width * 0.06

    def transform(get_frame, t):
        frame = get_frame(t)
        if t >= length:
            return frame
        remaining = 1.0 - (t / length)
        # Eased so the last third settles rather than sliding at constant speed.
        remaining *= remaining
        shifted = _shift(frame, round(travel * remaining))
        return _directional_blur(shifted, strength * remaining)

    return clip.transform(transform, apply_to=[])


def _shift(frame, pixels: int):
    """The frame moved sideways, the vacated edge holding its last column.

    Rolled pixels would wrap the opposite edge into view, which during a whip
    reads as a seam tearing across the picture.
    """
    import numpy as np

    pixels = int(pixels)
    if pixels == 0:
        return frame

    out = np.empty_like(frame)
    if pixels > 0:
        pixels = min(pixels, frame.shape[1] - 1)
        out[:, pixels:] = frame[:, : frame.shape[1] - pixels]
        out[:, :pixels] = frame[:, :1]
    else:
        pixels = min(-pixels, frame.shape[1] - 1)
        out[:, : frame.shape[1] - pixels] = frame[:, pixels:]
        out[:, frame.shape[1] - pixels:] = frame[:, -1:]
    return out


def _ramp_in(clip, length: float):
    """The incoming shot arriving fast and settling to its own speed.

    A speed ramp is retiming, not a fade: the shot opens playing quickly and
    decelerates into real time over the transition. Applied to the picture
    only, which is safe here because narration is a separate track laid at
    absolute times - nothing about a shot's internal timing can drift it.

    A still has no internal motion to retime, so it gets the whip's settle
    without the smear rather than nothing at all.
    """
    if length <= 0:
        return clip

    def time_map(t):
        import numpy as np

        t = np.asarray(t, dtype="float64")
        # Inside the window, play from further ahead in the source and ease
        # back to real time; outside it, one to one.
        eased = np.where(
            t < length,
            t + (length - t) * 0.6 * (1.0 - t / max(length, 1e-6)),
            t,
        )
        return np.minimum(eased, max(clip.duration - 1e-3, 0.0))

    return clip.time_transform(time_map, apply_to=[])


# How long a counter takes to reach its figure, and how many distinct values
# it shows getting there. Quantised because each step is a separate text
# render: a smooth thirty-frames-a-second count would draw thirty bitmaps for
# one overlay, and past about a dozen steps nobody can read the difference.
COUNT_SECONDS = 0.7
COUNT_STEPS = 12

_COUNTABLE = __import__("re").compile(r"^(\D*?)(\d[\d,]*)(.*)$", __import__("re").DOTALL)


def _counting_clip(draw, overlay):
    """A counter that counts, rather than one that states its answer.

    A figure heard once is forgotten, which is the whole reason the graphics
    layer puts numbers on screen; a number that arrives already finished is
    only a caption of what was just said. Counting to it is what makes the
    viewer read it.

    Returns None when there is nothing sensible to count - no digits, or a
    year, which counted from zero spins through four millennia of history to
    land on 1902 and looks absurd. `graphics.py` decides which is which and
    says so in the overlay's data; anything it did not mark is drawn as it is.
    """
    from moviepy import concatenate_videoclips

    target = str((overlay.data or {}).get("to") or "")
    start_value = (overlay.data or {}).get("from")
    if not target or start_value is None:
        return None

    match = _COUNTABLE.match(target)
    if not match:
        return None
    prefix, digits, suffix = match.groups()

    try:
        end_number = int(digits.replace(",", ""))
        begin_number = int(str(start_value).replace(",", ""))
    except ValueError:
        return None
    if end_number == begin_number:
        return None

    grouped = "," in digits
    span = min(COUNT_SECONDS, overlay.duration * 0.6)
    if span <= 0:
        return None

    steps = []
    for step in range(COUNT_STEPS):
        # Eased out, so the count decelerates onto its figure instead of
        # stopping dead on it.
        progress = (step + 1) / COUNT_STEPS
        progress = 1.0 - (1.0 - progress) ** 3
        value = round(begin_number + (end_number - begin_number) * progress)
        steps.append(f"{value:,}" if grouped else str(value))

    # The last step is the real figure, spelled exactly as it was written.
    steps[-1] = digits

    clips = []
    for index, shown in enumerate(steps):
        piece = draw(f"{prefix}{shown}{suffix}")
        if piece is None:
            return None
        held = (overlay.duration - span) if index == len(steps) - 1 else (span / COUNT_STEPS)
        clips.append(piece.with_duration(max(held, 1.0 / 60.0)))

    return concatenate_videoclips(clips, method="compose")


# How long a chart's bars take to reach their values, and in how many steps.
# Same quantisation as the counter and for the same reason: each step is a
# separate draw, and past a dozen nobody can see the difference.
CHART_BUILD_SECONDS = 1.1
CHART_BUILD_STEPS = 12


def _chart_clip(overlay, size):
    """A chart whose bars grow, drawn from the run's own researched figures.

    Built as a short sequence of stills rather than a per-frame draw: a bar
    chart is a dozen rounded rectangles and some text, and rendering that
    thirty times a second for five seconds to animate the first second of it
    is work nobody sees.
    """
    import numpy as np
    from moviepy import ImageClip, concatenate_videoclips

    import charts

    data = overlay.data or {}
    series = [
        (str(row[0]), float(row[1]), str(row[2]))
        for row in (data.get("series") or [])
        if isinstance(row, (list, tuple)) and len(row) >= 3
    ]
    if not series:
        return None

    accent = tuple((overlay.style or {}).get("color_rgb") or (232, 133, 60))
    title = str(data.get("title") or "")

    build = min(CHART_BUILD_SECONDS, overlay.duration * 0.5)
    step = build / CHART_BUILD_STEPS

    clips = []
    for index in range(CHART_BUILD_STEPS):
        progress = (index + 1) / CHART_BUILD_STEPS
        frame = charts.bar_chart(series, title, size, accent=accent, progress=progress)
        held = (overlay.duration - build) if index == CHART_BUILD_STEPS - 1 else step
        clips.append(
            ImageClip(np.asarray(frame), transparent=True)
            .with_duration(max(held, 1.0 / 60.0))
        )

    return concatenate_videoclips(clips, method="compose")


def _relief_for(source: str, size):
    """The depth map for a still, at the output's size, or None.

    None is the ordinary answer for anything that is not a photograph the
    depth model can read, and for every source when the model is not present.
    The caller then renders the flat move, which is what stills had before.
    """
    try:
        from providers.visual import depth

        return parallax.prepare(depth.for_image(source), size)
    except Exception:
        return None


def _move_as_camera(source_size, size, motion, progress: float, fit: str):
    """The same Ken Burns move expressed as a camera offset and a zoom.

    `crop_box` says which rectangle of the source to show. A warp needs the
    move the other way round - how far the camera has travelled and how far in
    it has pushed - so the box is converted rather than the move being invented
    twice and drifting apart.
    """
    box = crop_box(source_size, size, motion, progress, fit)
    still = crop_box(source_size, size, None, 0.0, fit)

    width = max(1.0, box[2] - box[0])
    zoom = (still[2] - still[0]) / width

    # Where the moving box sits relative to the resting one, in output pixels.
    offset_x = ((still[0] + still[2]) / 2 - (box[0] + box[2]) / 2) * (size[0] / max(1.0, still[2] - still[0]))
    offset_y = ((still[1] + still[3]) / 2 - (box[1] + box[3]) / 2) * (size[1] / max(1.0, still[3] - still[1]))
    return (offset_x, offset_y), max(1.0, zoom)


def _text_margin(font_size: int, stroke_width: int = 0) -> int:
    """Vertical padding to add around drawn text, in pixels.

    Scaled to the type size rather than fixed, because the same renderer
    draws a 30px caption and a 90px overlay, and the stroke is added because
    it grows the glyph outwards on every side.

    The ratio is measured, not guessed: at 0.25 the ink still reached the
    last row of the bitmap at every size tested - even a line of capitals
    with no descenders at all. 0.45 clears Latin descenders and Devanagari
    matras from 30px to 90px with room to spare, and the cost of being
    generous is transparent pixels.
    """
    return max(6, int(font_size * 0.45)) + max(0, stroke_width)


class MoviePyRenderer(Renderer):
    name = "moviepy"

    # ----------------------------------------------------------------------
    # Picture
    # ----------------------------------------------------------------------

    def _color_clip(self, shot, size, duration):
        from moviepy import ColorClip

        return ColorClip(size=size, color=tuple(shot.color)).with_duration(duration)

    def _image_clip(self, shot, size, duration):
        """A still, with its Ken Burns move if it has one."""
        import numpy as np
        from moviepy import ImageClip, VideoClip
        from PIL import Image

        image = _load_image(shot.source)
        source_size = image.size

        if shot.motion is None or shot.motion.is_static:
            if _STATIC_IMAGE_FAST_PATH:
                box = crop_box(source_size, size, None, 0.0, shot.fit)
                framed = image.resize(size, Image.LANCZOS, box=box)
                return ImageClip(np.asarray(framed)).with_duration(duration)

        motion = shot.motion

        # A still with a depth map behind it is moved as a scene rather than as
        # a card: near parts of the picture cross the frame faster than far
        # ones. Estimated once per source and cached, so this costs nothing at
        # render time; a source with no map falls back to the flat crop, which
        # is what every still did before.
        relief = _relief_for(shot.source, size)

        if relief is not None:
            fitted = image.resize(size, Image.LANCZOS, box=crop_box(source_size, size, None, 0.0, shot.fit))

            def parallax_at(t):
                progress = (t / duration) if duration else 0.0
                offset, zoom = _move_as_camera(source_size, size, motion, progress, shot.fit)
                return np.asarray(parallax.warp(fitted, relief, offset, zoom))

            return VideoClip(frame_function=parallax_at, duration=duration)

        def frame_at(t):
            progress = (t / duration) if duration else 0.0
            box = crop_box(source_size, size, motion, progress, shot.fit)
            # Pillow's box argument crops and scales in one pass, which is both
            # faster and cleaner than cropping to a new image first.
            return np.asarray(image.resize(size, Image.BILINEAR, box=box))

        return VideoClip(frame_function=frame_at, duration=duration)

    def _video_clip(self, shot, size, duration):
        from moviepy import VideoFileClip

        clip = VideoFileClip(shot.source)

        start = min(shot.in_point, max(0.0, clip.duration - 0.1))
        end = min(start + duration, clip.duration)
        if end > start:
            clip = clip.subclipped(start, end)

        left, upper, right, lower = crop_box(
            (clip.w, clip.h), size, None, 0.0, shot.fit
        )
        if (right - left, lower - upper) != (clip.w, clip.h):
            clip = clip.cropped(x1=left, y1=upper, x2=right, y2=lower)
        clip = clip.resized(size)

        # Stock footage carries its own audio, which is never wanted - the mix
        # has already been built from the Timeline's audio tracks.
        clip = clip.without_audio()

        # Source footage is routinely shorter than the slot the script gives
        # it. Holding the last frame is quieter than looping, which draws
        # attention to itself - but it has to be an actual frozen frame.
        # Simply extending the clip's duration leaves the reader seeking past
        # the end of the file, which warns once per frame and re-reads the
        # source for every one of them.
        if clip.duration < duration - 0.01:
            clip = self._hold_last_frame(clip, duration)

        return clip

    def _hold_last_frame(self, clip, duration: float):
        """Extends `clip` to `duration` by freezing on its final frame."""
        from moviepy import CompositeVideoClip, ImageClip

        # Step back slightly from the very end: the last frame index is often
        # unreadable in stock encodes, which is the failure this exists to
        # avoid in the first place.
        sample_at = max(0.0, clip.duration - 0.05)
        try:
            still = ImageClip(clip.get_frame(sample_at))
        except Exception:
            return clip.with_duration(duration)

        still = still.with_start(clip.duration).with_duration(duration - clip.duration)
        return CompositeVideoClip([clip, still], size=clip.size).with_duration(duration)

    def _shot_clip(self, shot, size, extra: float = 0.0):
        """One shot, `extra` seconds longer if a dissolve runs past its end."""
        duration = shot.duration + extra

        if shot.source_type == "color" or not shot.source:
            return self._color_clip(shot, size, duration)
        try:
            if shot.source_type == "image":
                return self._image_clip(shot, size, duration)
            return self._video_clip(shot, size, duration)
        except Exception:
            # A single unreadable download should cost one shot, not the whole
            # render. The gap it would otherwise leave reads as a black flash.
            return self._color_clip(shot, size, duration)

    # ----------------------------------------------------------------------
    # Transitions
    # ----------------------------------------------------------------------

    def _apply_transitions(self, clips, timeline):
        """Fades incoming shots in where the Timeline asks for a dissolve."""
        from moviepy.video.fx import CrossFadeIn, FadeIn

        by_time = {round(t.at, 3): t for t in timeline.transitions if t.kind != "cut"}
        if not by_time:
            return clips

        out = []
        for shot, clip in zip(timeline.shots, clips):
            transition = by_time.get(round(shot.start, 3))
            if transition is None or transition.duration <= 0:
                out.append(clip)
                continue

            length = min(transition.duration, clip.duration)
            if transition.kind == "dip_to_black":
                out.append(clip.with_effects([FadeIn(length)]))
            elif transition.kind == "whip":
                out.append(_whip_in(clip, length))
            elif transition.kind == "speed_ramp":
                out.append(_ramp_in(clip, length))
            else:
                out.append(clip.with_effects([CrossFadeIn(length)]))
        return out

    def _tail_extension(self, timeline) -> dict[int, float]:
        """How much longer each shot must run so a dissolve has something to
        dissolve from."""
        extensions: dict[int, float] = {}
        starts = {round(shot.start, 3): index for index, shot in enumerate(timeline.shots)}
        for transition in timeline.transitions:
            if transition.kind == "cut" or transition.duration <= 0:
                continue
            index = starts.get(round(transition.at, 3))
            if index is None or index == 0:
                continue
            extensions[index - 1] = max(extensions.get(index - 1, 0.0), transition.duration)
        return extensions

    # ----------------------------------------------------------------------
    # Text
    # ----------------------------------------------------------------------

    def _text_clip(self, text, size, font_size, color, stroke_color, stroke_width, width_ratio=0.9):
        from moviepy import TextClip

        font = fonts.resolve(text)
        kwargs = dict(
            text=text,
            font_size=font_size,
            color=color,
            stroke_color=stroke_color,
            stroke_width=stroke_width,
            size=(int(size[0] * width_ratio), None),
            method="caption",
            # Breathing room below the baseline. Asked for a height of None,
            # the drawing backend returns a bitmap that ends exactly on the
            # last inked row, so every descender - p, y, g, j - was sliced
            # off flush: "saump diya" rendered as "saumo diva".
            margin=(0, _text_margin(font_size, stroke_width)),
        )
        if font:
            kwargs["font"] = font
        try:
            return TextClip(**kwargs)
        except Exception:
            # A named font can be present in fontconfig but unreadable by the
            # drawing backend. Falling back beats losing the caption.
            kwargs.pop("font", None)
            try:
                return TextClip(**kwargs)
            except Exception:
                return None

    def _caption_clips(self, timeline, size, style):
        clips = []
        font_size = max(12, int(size[1] * style.get("font_size_ratio", 0.045)))
        for caption in timeline.captions:
            text = caption.text.strip()
            if not text:
                continue
            if style.get("uppercase"):
                text = text.upper()
            clip = self._text_clip(
                text, size, font_size,
                style.get("color", "#FFFFFF"),
                style.get("stroke_color", "black"),
                int(style.get("stroke_width", 3)),
            )
            if clip is None:
                continue
            # The margin sits above the text as well as below it, so the
            # caption would otherwise drift down the frame by that much.
            y = int(size[1] * style.get("position", 0.82)) - _text_margin(
                font_size, int(style.get("stroke_width", 3))
            )
            clips.append(
                clip.with_start(caption.start)
                .with_end(caption.end)
                .with_position(("center", y))
            )
        return clips

    def _overlay_clips(self, timeline, size):
        """Text, images and highlight boxes drawn over the picture."""
        from moviepy import ColorClip, ImageClip
        from moviepy.video.fx import CrossFadeIn, CrossFadeOut

        clips = []
        for overlay in timeline.overlays:
            style = overlay.style or {}
            clip = None

            if overlay.kind in ("text", "lower_third", "counter"):
                font_size = max(12, int(size[1] * style.get("font_size_ratio", 0.05)))
                draw = lambda text: self._text_clip(
                    text, size, font_size,
                    style.get("color", "#FFFFFF"),
                    style.get("stroke_color", "black"),
                    int(style.get("stroke_width", 2)),
                    width_ratio=float(style.get("width_ratio", 0.8)),
                )
                clip = None
                if overlay.kind == "counter":
                    clip = _counting_clip(draw, overlay)
                if clip is None:
                    clip = draw(overlay.text)
            elif overlay.kind == "chart":
                clip = _chart_clip(overlay, size)
            elif overlay.kind == "image" and os.path.exists(overlay.source):
                try:
                    import numpy as np

                    clip = ImageClip(np.asarray(_load_image(overlay.source)))
                except Exception:
                    clip = None
            elif overlay.kind == "highlight":
                box = style.get("size", (0.3, 0.2))
                clip = ColorClip(
                    size=(int(size[0] * box[0]), int(size[1] * box[1])),
                    color=tuple(style.get("color_rgb", (232, 133, 60))),
                ).with_opacity(float(style.get("opacity", 0.35)))

            if clip is None:
                continue

            clip = clip.with_start(overlay.start).with_duration(overlay.duration)

            if tuple(clip.size) == tuple(size):
                # Already the size of the frame, so it carries its own layout
                # and there is nothing to place. with_position sets the *top
                # left* corner, so asking for the middle of the frame put a
                # full-height chart's top edge halfway down it and cut the
                # bottom half off the screen.
                clip = clip.with_position((0, 0))
            else:
                position = (
                    int(size[0] * overlay.position[0]),
                    int(size[1] * overlay.position[1]),
                )
                clip = clip.with_position(
                    position if overlay.anchor != "center" else ("center", position[1])
                )

            effects = []
            if overlay.animate_in != "none":
                effects.append(CrossFadeIn(min(0.35, overlay.duration / 3)))
            if overlay.animate_out != "none":
                effects.append(CrossFadeOut(min(0.35, overlay.duration / 3)))
            if effects:
                clip = clip.with_effects(effects)
            clips.append(clip)
        return clips

    # ----------------------------------------------------------------------
    # Render
    # ----------------------------------------------------------------------

    def render(
        self,
        timeline,
        output_path: str,
        progress: Callable[[str, float], None] | None = None,
    ) -> str:
        ensure_ffmpeg_on_path()
        from moviepy import AudioFileClip, CompositeVideoClip

        def report(stage: str, fraction: float) -> None:
            if progress:
                progress(stage, fraction)

        timeline.validate()

        size = (timeline.width, timeline.height)
        parent = os.path.dirname(output_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        report("audio", 0.0)
        mixed_path = f"{os.path.splitext(output_path)[0]}.mix.wav"
        audio_mix.mix(timeline, mixed_path)
        audio_mix.normalize_to_lufs(mixed_path)

        report("shots", 0.1)
        extensions = self._tail_extension(timeline)
        clips = []
        for index, shot in enumerate(timeline.shots):
            clips.append(self._shot_clip(shot, size, extensions.get(index, 0.0)))
            report("shots", 0.1 + 0.5 * (index + 1) / max(1, len(timeline.shots)))

        clips = self._apply_transitions(clips, timeline)
        positioned = [
            clip.with_start(shot.start) for shot, clip in zip(timeline.shots, clips)
        ]

        report("overlays", 0.65)
        caption_style = (timeline.meta or {}).get("caption_style", {})
        layers = positioned
        if caption_style.get("enabled", True):
            layers = layers + self._caption_clips(timeline, size, caption_style)
        layers = layers + self._overlay_clips(timeline, size)

        # Last layer, over everything, unless this machine holds a commercial
        # grant. See licence.py - and note that it is the licence and the
        # trademark doing the work here, not this line.
        import watermark

        mark = watermark.clip(size[0], size[1], timeline.duration)
        if mark is not None:
            layers = layers + [mark]

        report("compositing", 0.7)
        video = CompositeVideoClip(layers, size=size).with_duration(timeline.duration)
        video = video.with_audio(AudioFileClip(mixed_path).with_duration(timeline.duration))

        report("encoding", 0.75)
        # One look over every shot, whatever it was cut from - see render/grade.
        # Applied here rather than per frame in Python because it has to reach
        # stock footage too, and because the encoder is already running.
        video.write_videofile(
            output_path,
            fps=timeline.fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            threads=max(2, cpu_count() - 1),
            ffmpeg_params=grade.ffmpeg_params(),
            logger=None,
        )

        try:
            video.close()
        except Exception:
            pass
        # The intermediate mix is regenerable and can be tens of megabytes on a
        # long video; there is no reason to leave it in the project directory.
        try:
            os.remove(mixed_path)
        except OSError:
            pass

        report("done", 1.0)
        return output_path


register("moviepy", MoviePyRenderer)
