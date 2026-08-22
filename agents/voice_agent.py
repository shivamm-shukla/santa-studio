from agents._llm_utils import speech_language
from providers.registry import get_provider
from providers.voice.alignment import align_words
from providers.voice.filters import apply_filter
from providers.voice.profiles import resolve_voice_path


def _duration_of(word_timestamps: list[dict]) -> float:
    return float(word_timestamps[-1]["end"]) if word_timestamps else 0.0


def _caption_provider(config: dict):
    """The configured aligner, or None if there isn't one.

    A missing or broken caption provider must not fail the voice stage -
    align_words degrades to even spreading on its own, and a video with
    approximate caption timings is a great deal better than no video.
    """
    if not (config.get("ACTIVE_PROVIDERS") or {}).get("caption"):
        return None
    try:
        return get_provider("caption", config)
    except Exception:
        return None


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

    Whatever route the audio took, the returned word_timestamps are measured
    against the finished file rather than estimated from the text.
    """
    # script_spoken is the Devanagari version of the same script, present
    # only for non-English videos; it exists so the voice pronounces Hindi
    # correctly while captions and titles stay in Latin script.
    visible_text = input_data.get("script_text", "")
    spoken_text = input_data.get("script_spoken")
    script_text = spoken_text or visible_text
    voice_profile_id = input_data.get("voice_profile_id")
    filter_preset = input_data.get("filter_preset")

    try:
        if voice_profile_id:
            voice_sample_path = resolve_voice_path(voice_profile_id)
            filter_preset = None
        else:
            voice_sample_path = input_data.get("voice_sample_path", "")

        provider = get_provider("voice", config)
        result = dict(provider.clone_and_generate(
            script_text, voice_sample_path, language=speech_language(config)
        ))

        # Filtering first, alignment second. Some presets change tempo
        # (`energetic` runs the audio 5% fast), so timings measured against
        # the unfiltered file drift further out of sync the longer the video
        # runs. Align against the file that actually ships.
        if filter_preset:
            result["audio_path"] = apply_filter(result["audio_path"], filter_preset)

        # Captions are locked to the audio for every language, not just the
        # ones where the spoken script differs from the visible one. A voice
        # provider's own timings are an estimate derived from the text -
        # gTTS divides the duration by the word count - so they drift on any
        # sentence read faster or slower than average.
        result["word_timestamps"] = align_words(
            result["audio_path"],
            visible_text,
            language=speech_language(config),
            provider=_caption_provider(config),
        )

        return {"success": True, "output": result, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
