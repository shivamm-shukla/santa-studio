from providers.registry import get_provider


def run(input_data: dict, config: dict) -> dict:
    """Input: {script_text: str, voice_sample_path: str}
    Output: {audio_path: str, word_timestamps: list[dict]}
    """
    script_text = input_data.get("script_text", "")
    voice_sample_path = input_data.get("voice_sample_path", "")

    provider = get_provider("voice", config)
    result = provider.clone_and_generate(script_text, voice_sample_path)

    return {"success": True, "output": result, "error": None}
