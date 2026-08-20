from providers.registry import get_provider
from providers.voice.filters import apply_filter
from providers.voice.profiles import resolve_voice_path


def run(input_data: dict, config: dict) -> dict:
    """Input: {script_text: str, voice_profile_id: str | None,
               voice_sample_path: str | None, filter_preset: str | None}
    Output: {audio_path: str, word_timestamps: list[dict]}

    When voice_profile_id is given, its (already-filtered, if a filter was
    applied when the profile was created) sample is used as the clone
    reference - filter_preset is ignored in that case, since the profile's
    filter is baked in once rather than reapplied per run. Without a
    profile, voice_sample_path is used directly and filter_preset (if set)
    is applied to the freshly generated output - the original per-run flow,
    kept for CLI/Streamlit callers that don't use profiles.
    """
    script_text = input_data.get("script_text", "")
    voice_profile_id = input_data.get("voice_profile_id")
    filter_preset = input_data.get("filter_preset")

    try:
        if voice_profile_id:
            voice_sample_path = resolve_voice_path(voice_profile_id)
            filter_preset = None
        else:
            voice_sample_path = input_data.get("voice_sample_path", "")

        provider = get_provider("voice", config)
        result = provider.clone_and_generate(script_text, voice_sample_path)

        if filter_preset:
            result = dict(result)
            result["audio_path"] = apply_filter(result["audio_path"], filter_preset)

        return {"success": True, "output": result, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
