"""Extracts a viral 9:16 vertical YouTube Short from the finished long-form video."""

import os
from multiprocessing import cpu_count
from providers._ffmpeg_setup import ensure_ffmpeg_on_path

SHORT_WIDTH, SHORT_HEIGHT = 720, 1280
MAX_SHORT_DURATION = 50.0  # seconds


def run(input_data: dict, config: dict) -> dict:
    """Input: {video_path: str, script: dict, run_id: str}
    Output: {short_path: str, duration: float}
    """
    try:
        ensure_ffmpeg_on_path()
        from moviepy import VideoFileClip

        video_path = input_data.get("video_path")
        run_id = input_data.get("run_id") or "unknown"

        if not video_path or not os.path.exists(video_path):
            return {"success": False, "output": None, "error": f"Source video not found: {video_path}"}

        raw = VideoFileClip(video_path)
        total_dur = raw.duration

        # Extract the opening hook (first 30-50s)
        clip_dur = min(total_dur, MAX_SHORT_DURATION)
        sub = raw.subclipped(0, clip_dur)

        # Center-crop to 9:16 vertical ratio (405x720 from 1280x720) and resize to 720x1280
        src_w, src_h = sub.size
        crop_w = int(src_h * 9 / 16)
        x1 = max(0, (src_w - crop_w) // 2)

        short_clip = sub.cropped(x1=x1, y1=0, width=crop_w, height=src_h).resized((SHORT_WIDTH, SHORT_HEIGHT))

        os.makedirs("runs/shorts", exist_ok=True)
        out_path = f"runs/shorts/{run_id}_short.mp4"

        short_clip.write_videofile(
            out_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            threads=max(2, cpu_count() - 1),
            logger=None,
        )

        return {
            "success": True,
            "output": {"short_path": out_path, "duration": clip_dur},
            "error": None,
        }
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
