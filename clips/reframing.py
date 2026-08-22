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
    """Calculates (x1, y1, width, height) bounding box for 9:16 crop."""
    crop_width = int(round(src_height * target_aspect))
    # Make sure width is even for video codec compatibility
    if crop_width % 2 != 0:
        crop_width += 1
    crop_width = min(crop_width, src_width)

    desired_center_x = int(round(src_width * crop_x_center_ratio))
    x1 = desired_center_x - (crop_width // 2)
    x1 = max(0, min(x1, src_width - crop_width))
    if x1 % 2 != 0:
        x1 -= 1
        x1 = max(0, x1)

    return x1, 0, crop_width, src_height


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

        x1, y1, crop_w, crop_h = calculate_crop_window(src_w, src_h, crop_x_center_ratio)
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
