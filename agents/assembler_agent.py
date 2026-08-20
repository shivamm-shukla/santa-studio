import os

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.registry import get_provider

WIDTH, HEIGHT = 1280, 720
CAPTION_CHUNK_SIZE = 5  # words per on-screen caption line


def _load_scene_clip(asset: dict, duration: float):
    from moviepy import ColorClip, ImageClip, VideoFileClip

    path = asset.get("asset_path")
    asset_type = asset.get("asset_type", "video")

    if path and os.path.exists(path):
        try:
            if asset_type == "video":
                raw = VideoFileClip(path)
                clip = raw.subclipped(0, min(duration, raw.duration)).resized((WIDTH, HEIGHT))
                if clip.duration < duration:
                    clip = clip.with_duration(duration)
                return clip
            else:
                return ImageClip(path).resized((WIDTH, HEIGHT)).with_duration(duration)
        except Exception:
            pass  # fall through to placeholder

    # No usable asset (missing API key, download failure, etc.) - a plain
    # placeholder frame keeps assembly working end-to-end regardless.
    return ColorClip(size=(WIDTH, HEIGHT), color=(20, 20, 20)).with_duration(duration)


def _build_captions(word_timestamps: list[dict]):
    from moviepy import TextClip

    clips = []
    for i in range(0, len(word_timestamps), CAPTION_CHUNK_SIZE):
        chunk = word_timestamps[i : i + CAPTION_CHUNK_SIZE]
        if not chunk:
            continue
        text = " ".join(w["word"] for w in chunk)
        start, end = chunk[0]["start"], chunk[-1]["end"]
        if end <= start:
            continue
        try:
            txt_clip = (
                TextClip(
                    text=text,
                    font_size=40,
                    color="white",
                    stroke_color="black",
                    stroke_width=2,
                    size=(int(WIDTH * 0.9), None),
                    method="caption",
                )
                .with_start(start)
                .with_end(end)
                .with_position(("center", HEIGHT - 120))
            )
            clips.append(txt_clip)
        except Exception:
            continue
    return clips


def run(input_data: dict, config: dict) -> dict:
    """Input: {audio_path: str, scene_assets: list[dict], script_text: str, run_id: str}
    Output: {video_path: str}

    Stitches scene_assets in order, syncs to audio_path, and burns in
    captions generated from the caption provider's word timestamps.
    """
    ensure_ffmpeg_on_path()
    from moviepy import AudioFileClip, CompositeVideoClip, concatenate_videoclips

    audio_path = input_data.get("audio_path")
    scene_assets = input_data.get("scene_assets") or [{}]
    run_id = input_data.get("run_id", "unknown")

    try:
        audio_clip = AudioFileClip(audio_path) if audio_path and os.path.exists(audio_path) else None
    except Exception:
        audio_clip = None

    total_duration = audio_clip.duration if audio_clip else max(len(scene_assets) * 4, 4)
    per_scene_duration = total_duration / len(scene_assets)

    scene_clips = [_load_scene_clip(asset, per_scene_duration) for asset in scene_assets]
    video = concatenate_videoclips(scene_clips, method="compose")

    if audio_clip:
        final_duration = min(video.duration, audio_clip.duration)
        video = video.with_duration(final_duration).with_audio(audio_clip.with_duration(final_duration))

    word_timestamps = []
    if audio_clip:
        try:
            caption_provider = get_provider("caption", config)
            word_timestamps = caption_provider.transcribe(audio_path).get("word_timestamps", [])
        except Exception:
            word_timestamps = []  # captions are best-effort, never block assembly

    caption_clips = _build_captions(word_timestamps)
    final = CompositeVideoClip([video] + caption_clips) if caption_clips else video

    os.makedirs("runs", exist_ok=True)
    output_path = f"runs/{run_id}_final.mp4"
    final.write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac", logger=None)

    return {"success": True, "output": {"video_path": output_path}, "error": None}
