import os

import paths
import style_profile as sp
import timeline_builder
from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.registry import get_provider
from render.base import get_renderer


def _normalize_state(input_data: dict) -> dict:
    """Extracts a normalized state dict suitable for timeline_builder."""
    state_data = {
        "run_id": input_data.get("run_id", "unknown"),
        "topic": input_data.get("topic") or input_data.get("user_topic") or "",
        "script": input_data.get("script") or {
            "script_text": input_data.get("script_text", ""),
            "scenes": input_data.get("scenes") or [{"text": input_data.get("script_text", "")}],
        },
        "visual_output": input_data.get("visual_output") or {
            "scene_assets": input_data.get("scene_assets") or []
        },
        "voice_output": input_data.get("voice_output") or {
            "audio_path": input_data.get("audio_path", ""),
            "word_timestamps": input_data.get("word_timestamps") or [],
        },
        # Only the source list is read, for the citation card the graphics
        # layer draws at the end. Absent research simply means no card.
        "research": input_data.get("research") or {},
    }
    if not state_data["voice_output"].get("audio_path") and input_data.get("audio_path"):
        state_data["voice_output"]["audio_path"] = input_data.get("audio_path")
    if not state_data["visual_output"].get("scene_assets") and input_data.get("scene_assets"):
        state_data["visual_output"]["scene_assets"] = input_data.get("scene_assets")
    return state_data


def run(input_data: dict, config: dict) -> dict:
    """Input: {audio_path: str, scene_assets: list[dict], script_text: str, run_id: str, ...}
    Output: {video_path: str, timeline_path: str}

    Constructs a Timeline honoring script scene timing and style profile motion/captions,
    then renders the video via the registered modular renderer (MoviePyRenderer).
    """
    try:
        ensure_ffmpeg_on_path()

        audio_path = input_data.get("audio_path") or (input_data.get("voice_output") or {}).get("audio_path")
        run_id = input_data.get("run_id", "unknown")

        if not audio_path:
            raise RuntimeError("No audio_path from the voice stage - cannot assemble a video with no voice.")
        if not os.path.exists(audio_path):
            raise RuntimeError(
                f"Voice track {audio_path!r} is missing at assembly time. It was "
                "produced but has since been deleted - check nothing is clearing "
                "the project's voice/ folder while a run is in flight."
            )

        music_path = ""
        if config.get("ACTIVE_PROVIDERS", {}).get("music"):
            try:
                music_provider = get_provider("music", config)
                mood = input_data.get("mood") or "curious"
                music_res = music_provider.search(mood)
                bg_path = music_res.get("track_path")
                if bg_path and os.path.exists(bg_path):
                    music_path = bg_path
            except Exception:
                music_path = ""

        profile_name = config.get("STYLE_PROFILE", "documentary")
        profile = sp.load(profile_name)

        state_data = _normalize_state(input_data)
        timeline = timeline_builder.build(state_data, profile=profile, music_path=music_path)

        topic = input_data.get("topic") or ""
        timeline_path = str(paths.timeline_file(run_id, topic))
        timeline.save(timeline_path)

        output_path = input_data.get("output_path") or str(
            paths.output_dir(run_id, topic) / "master.mp4"
        )
        renderer = get_renderer("moviepy")
        rendered_path = renderer.render(timeline, output_path)

        return {
            "success": True,
            "output": {"video_path": rendered_path, "timeline_path": timeline_path},
            "error": None,
        }
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}

