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

        # Source footage is routinely shorter than the slot the script gives
        # it. Holding the last frame is quieter than looping, which draws
        # attention to itself.
        if clip.duration < duration:
            clip = clip.with_duration(duration)

        # Stock footage carries its own audio, which is never wanted - the mix
        # has already been built from the Timeline's audio tracks.
        return clip.without_audio()

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
            else:
                # crossfade, whip and speed_ramp all dissolve for now. A real
                # whip needs directional blur and a speed ramp needs retiming;
                # both are visual-craft work, not part of the renderer split.
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
            y = int(size[1] * style.get("position", 0.82))
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
                # A counter's animated number is visual-craft work; the static
                # label still renders so the layout is right.
                font_size = max(12, int(size[1] * style.get("font_size_ratio", 0.05)))
                clip = self._text_clip(
                    overlay.text, size, font_size,
                    style.get("color", "#FFFFFF"),
                    style.get("stroke_color", "black"),
                    int(style.get("stroke_width", 2)),
                    width_ratio=float(style.get("width_ratio", 0.8)),
                )
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
            position = (
                int(size[0] * overlay.position[0]),
                int(size[1] * overlay.position[1]),
            )
            clip = clip.with_position(position if overlay.anchor != "center" else ("center", position[1]))

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

        report("compositing", 0.7)
        video = CompositeVideoClip(layers, size=size).with_duration(timeline.duration)
        video = video.with_audio(AudioFileClip(mixed_path).with_duration(timeline.duration))

        report("encoding", 0.75)
        video.write_videofile(
            output_path,
            fps=timeline.fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            threads=max(2, cpu_count() - 1),
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
