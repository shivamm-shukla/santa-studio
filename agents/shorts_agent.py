"""Extracts a vertical YouTube Short from the finished long-form video.

This used to centre-crop at 720x1280 and 24fps, while the master it cuts
from is 1080p30 - so the short was both softer and choppier than the video
it came out of, for no reason. It also cropped dead centre, which removes
whatever the shot was actually framed on.

The Clips track had already solved both: clips/reframing.py crops to the
output's own aspect and detect_subject_x finds where the content is. This
uses them rather than keeping a second, worse implementation of the same
thing.
"""

import os

import runlog
import paths
from providers._ffmpeg_setup import ensure_ffmpeg_on_path

# Matched to the master rather than to nothing in particular.
SHORT_WIDTH, SHORT_HEIGHT = 1080, 1920
SHORT_FPS = 30
MAX_SHORT_DURATION = 50.0  # seconds


def run(input_data: dict, config: dict) -> dict:
    """Input: {video_path: str, script: dict, run_id: str}
    Output: {short_path: str, duration: float}
    """
    try:
        ensure_ffmpeg_on_path()
        from clips.reframing import detect_subject_x, render_vertical_clip
        from moviepy import VideoFileClip

        video_path = input_data.get("video_path")
        run_id = input_data.get("run_id") or "unknown"

        if not video_path or not os.path.exists(video_path):
            return {"success": False, "output": None, "error": f"Source video not found: {video_path}"}

        runlog.report(f"Opening {os.path.basename(video_path)}", progress=0.15)
        with VideoFileClip(video_path) as raw:
            total_dur = float(raw.duration)

        # The opening hook is the part written to stop a scroll, so that is
        # what the short is cut from.
        clip_dur = min(total_dur, MAX_SHORT_DURATION)
        if clip_dur <= 0:
            return {"success": False, "output": None, "error": "Source video has no duration"}

        out_path = str(paths.output_dir(run_id, input_data.get("topic") or "") / "short.mp4")

        runlog.report(f"Cutting the first {clip_dur:.0f}s to 9:16", progress=0.4)
        render_vertical_clip(
            source_video_path=video_path,
            start_time=0.0,
            end_time=clip_dur,
            output_path=out_path,
            crop_x_center_ratio=detect_subject_x(video_path, 0.0, clip_dur),
            width=SHORT_WIDTH,
            height=SHORT_HEIGHT,
            fps=SHORT_FPS,
        )

        runlog.report(f"Short written to {os.path.basename(out_path)}", progress=1.0)
        return {
            "success": True,
            "output": {"short_path": out_path, "duration": clip_dur},
            "error": None,
        }
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
