def run(input_data: dict, config: dict) -> dict:
    """Input: {audio_path: str, scene_assets: list[dict], script_text: str}
    Output: {video_path: str}
    """
    # TODO: integrate MoviePy/FFmpeg assembly logic here - stitch scene_assets
    # in order, sync to audio_path, burn in captions from the caption provider.
    run_id = input_data.get("run_id", "unknown")
    video_path = f"runs/{run_id}_final.mp4"
    return {"success": True, "output": {"video_path": video_path}, "error": None}
