import os
from agents._llm_utils import speech_language
import runlog
from providers.registry import get_provider
from providers.voice.alignment import align_words
from providers.voice.filters import apply_filter
from providers.voice.profiles import resolve_voice_path


def _duration_of(word_timestamps: list[dict]) -> float:
    return float(word_timestamps[-1]["end"]) if word_timestamps else 0.0


def _rescale_spans(spans, before_path: str, after_path: str):
    """The chunk spans, moved onto the filtered file's clock.

    Every voice preset is a uniform time transform - `energetic` plays the
    take 5% fast, `deep` resamples it slower - so the filtered file is the
    original stretched by one constant factor. Measuring both durations
    recovers that factor without each preset having to declare it. Anything
    unmeasurable returns None: falling back to transcription is better than
    aligning against spans that no longer describe the audio.
    """
    if not spans:
        return None

    from pydub import AudioSegment

    try:
        before = len(AudioSegment.from_file(before_path))
        after = len(AudioSegment.from_file(after_path))
    except Exception:
        return None

    if before <= 0 or after <= 0:
        return None

    factor = after / before
    if abs(factor - 1.0) < 1e-3:
        return spans

    return [
        {
            "start": round(float(s["start"]) * factor, 3),
            "end": round(float(s["end"]) * factor, 3),
            "duration": round(
                float(s.get("duration", float(s["end"]) - float(s["start"]))) * factor, 3
            ),
        }
        for s in spans
    ]


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

        runlog.report(
            f"Narrating {len(script_text.split())} words"
            + (f" with profile {voice_profile_id}" if voice_profile_id else ""),
            progress=0.15,
        )
        provider = get_provider("voice", config)
        result = dict(provider.clone_and_generate(
            script_text, voice_sample_path, language=speech_language(config)
        ))
        # Where the synthesis chunks landed in the stitched file, if the
        # provider measured them. This is the one piece of timing information
        # that does not depend on transcribing the audio back, so it carries
        # through to alignment rather than being recomputed from the waveform.
        chunk_spans = result.pop("chunk_spans", None)

        # Filtering first, alignment second. Some presets change tempo
        # (`energetic` runs the audio 5% fast), so timings measured against
        # the unfiltered file drift further out of sync the longer the video
        # runs. Align against the file that actually ships.
        runlog.report(f"Voice track written to {os.path.basename(result.get('audio_path', ''))}", progress=0.6)
        if filter_preset:
            runlog.report(f"Applying the {filter_preset!r} filter", progress=0.7)
            unfiltered = result["audio_path"]
            result["audio_path"] = apply_filter(unfiltered, filter_preset)
            chunk_spans = _rescale_spans(chunk_spans, unfiltered, result["audio_path"])

        # Captions are locked to the audio for every language, not just the
        # ones where the spoken script differs from the visible one. A voice
        # provider's own timings are an estimate derived from the text -
        # gTTS divides the duration by the word count - so they drift on any
        # sentence read faster or slower than average.
        runlog.report("Aligning captions against the finished audio", progress=0.8)
        result["word_timestamps"] = align_words(
            result["audio_path"],
            visible_text,
            language=speech_language(config),
            chunk_spans=chunk_spans,
            provider=_caption_provider(config),
        )

        runlog.report(
            f"{len(result.get('word_timestamps') or [])} words timed", progress=1.0
        )
        return {"success": True, "output": result, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
