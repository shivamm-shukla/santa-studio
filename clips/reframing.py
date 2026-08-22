"""Subject-aware vertical 9:16 reframing and rendering for short-form clips."""

from __future__ import annotations

import os
from multiprocessing import cpu_count
from typing import Optional

from providers._ffmpeg_setup import ensure_ffmpeg_on_path


TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920


def calculate_crop_window(
    src_width: int,
    src_height: int,
    crop_x_center_ratio: float = 0.5,
    target_aspect: float = 9.0 / 16.0,
) -> tuple[int, int, int, int]:
    """(x, y, width, height) of the largest `target_aspect` box in the source.

    Crops whichever axis has material to spare. Cropping width only - which
    is all this used to do - is right for a landscape source going vertical
    and wrong for everything else: a source already narrower than the target
    got its full width and full height back, and was then stretched onto the
    output frame.
    """
    src_aspect = src_width / max(1, src_height)

    if src_aspect > target_aspect:
        # Wider than we want: keep full height, take a slice of the width.
        crop_height = src_height
        crop_width = int(round(src_height * target_aspect))
    else:
        # Taller than we want: keep full width, take a slice of the height.
        crop_width = src_width
        crop_height = int(round(src_width / target_aspect))

    crop_width = max(2, min(crop_width - (crop_width % 2), src_width - (src_width % 2)))
    crop_height = max(2, min(crop_height - (crop_height % 2), src_height - (src_height % 2)))

    x = int(round(src_width * crop_x_center_ratio)) - crop_width // 2
    x = max(0, min(x, src_width - crop_width))
    x -= x % 2

    # Vertically, bias slightly above centre: heads sit in the upper half of
    # a frame far more often than not.
    y = max(0, min(int((src_height - crop_height) * 0.35), src_height - crop_height))
    y -= y % 2

    return x, y, crop_width, crop_height


def detect_subject_x(
    source_video_path: str,
    start_time: float,
    end_time: float,
    samples: int = 9,
) -> float:
    """Where the interesting part of the frame is, as a 0..1 horizontal ratio.

    Centre-cropping cuts the subject out whenever it is not dead centre,
    which on an interview or a presenter shot is most of the time. There is
    no face detector here and adding one would mean a new dependency, but a
    subject is reliably the part of the frame that has detail and that moves
    - so this scores columns by how much they vary, both within a frame and
    between frames, and returns the centre of mass of that score.

    Falls back to 0.5 on any failure: a centre crop is the old behaviour and
    a great deal better than not producing a clip.
    """
    try:
        import numpy as np

        ensure_ffmpeg_on_path()
        from moviepy import VideoFileClip

        with VideoFileClip(source_video_path) as clip:
            span_end = min(clip.duration, end_time)
            span_start = max(0.0, min(start_time, span_end - 0.1))
            if span_end <= span_start:
                return 0.5

            times = [
                span_start + (span_end - span_start) * i / max(1, samples - 1)
                for i in range(samples)
            ]

            columns = None
            previous = None
            for at in times:
                frame = clip.get_frame(at).astype("float32").mean(axis=2)
                # Detail: how much each column varies vertically.
                detail = frame.std(axis=0)
                score = detail
                if previous is not None:
                    # Movement: how much each column changed since last sample.
                    score = score + np.abs(frame - previous).mean(axis=0) * 2.0
                previous = frame
                columns = score if columns is None else columns + score

        if columns is None or not columns.size:
            return 0.5

        weights = columns - columns.min()
        total = float(weights.sum())
        if total <= 0:
            return 0.5

        positions = np.arange(weights.size, dtype="float32") / max(1, weights.size - 1)
        centre = float((positions * weights).sum() / total)
        # Keep it away from the extreme edges, where a crop would sit half
        # outside the frame anyway.
        return max(0.15, min(0.85, centre))
    except Exception:
        return 0.5


def render_vertical_clip(
    source_video_path: str,
    start_time: float,
    end_time: float,
    output_path: str,
    crop_x_center_ratio: float = 0.5,
    width: int = TARGET_WIDTH,
    height: int = TARGET_HEIGHT,
    fps: int = 30,
) -> str:
    """Extracts, vertically crops (9:16), resizes, and writes out a short-form clip."""
    ensure_ffmpeg_on_path()
    from moviepy import VideoFileClip

    if not os.path.exists(source_video_path):
        raise FileNotFoundError(f"Source video file not found at {source_video_path!r}")

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    with VideoFileClip(source_video_path) as raw:
        clip_duration = min(raw.duration, end_time) - start_time
        if clip_duration <= 0:
            raise ValueError(f"Invalid clip duration: {clip_duration}s (start: {start_time}, end: {end_time})")

        sub = raw.subclipped(start_time, min(raw.duration, end_time))
        src_w, src_h = sub.size

        # The crop follows the output's own shape, so a landscape preset gets
        # a landscape crop rather than a 9:16 one stretched back out.
        x1, y1, crop_w, crop_h = calculate_crop_window(
            src_w, src_h, crop_x_center_ratio, target_aspect=width / height
        )
        vertical_clip = sub.cropped(x1=x1, y1=y1, width=crop_w, height=crop_h).resized((width, height))

        threads = max(2, cpu_count() - 1)
        vertical_clip.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            threads=threads,
            logger=None,
        )

    return output_path
