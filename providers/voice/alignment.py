"""Forced alignment: locking word-level caption timestamps to actual speech.

Replaces uniform word spreading with acoustic alignment. The transcriber
measures the exact start and end of every spoken word from the audio
waveform. For Hinglish / multilingual scripts, segment-level speech
boundaries anchor the visible text so captions stay in sync even when the
spoken script is in Devanagari and the captions are Latin.

Transcription goes through a CaptionProvider when the caller has one, which
is what makes ACTIVE_PROVIDERS["caption"] mean something - swapping Whisper
for another aligner is then a config change, and the model is loaded once
per run instead of once per call. Callers without a provider (and any
environment where the provider raises) fall back to loading Whisper
directly, and to even spreading if that is unavailable too.
"""

from __future__ import annotations

import os
from typing import List, Optional

from providers._ffmpeg_setup import ensure_ffmpeg_on_path


def _fallback_spread_words(text: str, duration: float, start_offset: float = 0.0) -> List[dict]:
    """Uniformly distributes words over duration as an offline fallback."""
    words = text.split()
    if not words or duration <= 0:
        return []
    per_word = duration / len(words)
    return [
        {
            "word": w,
            "start": round(start_offset + i * per_word, 2),
            "end": round(start_offset + (i + 1) * per_word, 2),
        }
        for i, w in enumerate(words)
    ]


def _transcribe(audio_path: str, language: Optional[str], provider) -> dict:
    """Word timings and speech segments for `audio_path`.

    Returns {"word_timestamps": [...], "segments": [...]}; either list may be
    empty. Raises only if there is no way to transcribe at all - the caller
    treats that as "fall back to spreading".
    """
    whisper_lang = language if language in ("en", "hi") else None

    if provider is not None:
        result = provider.transcribe(audio_path, language=whisper_lang)
        return {
            "word_timestamps": result.get("word_timestamps") or [],
            "segments": result.get("segments") or [],
        }

    import whisper

    model = whisper.load_model("base")
    result = model.transcribe(audio_path, word_timestamps=True, language=whisper_lang)
    segments = result.get("segments", [])
    return {
        "word_timestamps": [
            {
                "word": w.get("word", "").strip(),
                "start": round(float(w["start"]), 2),
                "end": round(float(w["end"]), 2),
            }
            for seg in segments
            for w in seg.get("words", [])
            if w.get("word", "").strip()
        ],
        "segments": [
            {"start": float(seg["start"]), "end": float(seg["end"])} for seg in segments
        ],
    }


def _anchor_to_segments(visible_words: List[str], segments: List[dict]) -> List[dict]:
    """Spreads the visible text across measured speech segments.

    Used when the transcript cannot be matched to the caption text word for
    word - Hinglish captions are Latin while the audio is Devanagari, so the
    strings never line up. Segment boundaries are still real measurements of
    when speech starts and stops, which is a great deal better than spreading
    across the whole file: a pause between sentences stays a pause.
    """
    aligned: List[dict] = []
    total = sum(max(0.1, float(s["end"]) - float(s["start"])) for s in segments)

    index = 0
    for position, segment in enumerate(segments):
        seg_start = float(segment["start"])
        seg_duration = max(0.1, float(segment["end"]) - seg_start)

        remaining_words = len(visible_words) - index
        if remaining_words <= 0:
            break
        if position == len(segments) - 1:
            count = remaining_words
        else:
            share = seg_duration / max(0.1, total)
            count = max(1, int(round(share * len(visible_words))))
            count = min(count, remaining_words)

        chunk = visible_words[index : index + count]
        index += len(chunk)

        per_word = seg_duration / len(chunk)
        for offset, word in enumerate(chunk):
            aligned.append(
                {
                    "word": word,
                    "start": round(seg_start + offset * per_word, 2),
                    "end": round(seg_start + (offset + 1) * per_word, 2),
                }
            )

    return aligned


def align_words(
    audio_path: str,
    script_text: str,
    language: Optional[str] = None,
    chunk_spans: Optional[List[dict]] = None,
    provider=None,
) -> List[dict]:
    """Word-level caption timestamps measured against the audio.

    Parameters:
      audio_path: the narration that actually ships - align against the
                  filtered file, not the raw one, or a preset that changes
                  tempo silently desyncs every caption.
      script_text: the visible caption text.
      language:    "en", "hi", or None to auto-detect.
      chunk_spans: optional {"start", "end", "duration"} per synthesis chunk.
      provider:    a CaptionProvider. None loads Whisper directly.
    """
    if not os.path.exists(audio_path):
        return []

    ensure_ffmpeg_on_path()

    try:
        heard = _transcribe(audio_path, language, provider)
        words_found = heard["word_timestamps"]
        segments = heard["segments"]

        # When the audio and the captions are the same script, the words the
        # transcriber measured *are* the captions, timed exactly.
        if words_found and language == "en":
            return words_found

        if segments and script_text.strip():
            visible_words = script_text.split()
            if visible_words:
                return _anchor_to_segments(visible_words, segments)

        if words_found:
            return words_found
    except Exception:
        pass

    from pydub import AudioSegment

    try:
        duration = len(AudioSegment.from_file(audio_path)) / 1000.0
    except Exception:
        duration = 0.0

    return _fallback_spread_words(script_text, duration)
