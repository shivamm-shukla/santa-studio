from providers.registry import get_provider
from providers.voice.filters import apply_filter


def run(input_data: dict, config: dict) -> dict:
    """Input: {script_text: str, voice_sample_path: str, filter_preset: str | None}
    Output: {audio_path: str, word_timestamps: list[dict]}

    filter_preset, when set, runs the cloned voice through a named preset
    from providers.voice.filters (the "Instagram filter for your voice"
    concept) before returning the final audio_path.
    """
    script_text = input_data.get("script_text", "")
    voice_sample_path = input_data.get("voice_sample_path", "")
    filter_preset = input_data.get("filter_preset")

    try:
        provider = get_provider("voice", config)
        result = provider.clone_and_generate(script_text, voice_sample_path)

        if filter_preset:
            result = dict(result)
            result["audio_path"] = apply_filter(result["audio_path"], filter_preset)

        return {"success": True, "output": result, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
