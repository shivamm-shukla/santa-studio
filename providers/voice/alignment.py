"""Forced alignment: locking word-level caption timestamps to actual speech.

Replaces uniform word spreading (_spread_words) with acoustic alignment.
When Whisper is present, it measures the exact start and end of every spoken
word from the audio waveform. For Hinglish / multilingual scripts, segment-level
speech boundaries anchor the visible text so captions stay in sync even when
the spoken script is in Devanagari and captions are Latin.
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


def align_words(
    audio_path: str,
    script_text: str,
    language: Optional[str] = None,
    chunk_spans: Optional[List[dict]] = None,
) -> List[dict]:
    """Extracts word-level timestamps aligned with the audio file.

    Parameters:
      audio_path: Path to the generated narration audio.
      script_text: The visible text for captions.
      language: Language code ("en", "hi", etc.) or None for auto.
      chunk_spans: Optional list of {"start": float, "end": float, "duration": float}
                   if audio was synthesized in chunks.
    """
    if not os.path.exists(audio_path):
        return []

    ensure_ffmpeg_on_path()

    # Try Whisper-based acoustic alignment first
    try:
        import whisper
        model = whisper.load_model("base")
        whisper_lang = "en" if language == "en" else ("hi" if language == "hi" else None)
        result = model.transcribe(audio_path, word_timestamps=True, language=whisper_lang)
        
        segments = result.get("segments", [])
        words_found = []
        for segment in segments:
            for w in segment.get("words", []):
                cleaned_w = w.get("word", "").strip()
                if cleaned_w:
                    words_found.append({
                        "word": cleaned_w,
                        "start": round(float(w["start"]), 2),
                        "end": round(float(w["end"]), 2),
                    })

        # If Whisper returned words and we don't have a script script-discrepancy (e.g. English), use directly
        if words_found and language == "en":
            return words_found

        # If language is Hindi/Hinglish or script words differ in script (Devanagari vs Latin),
        # use Whisper segment boundaries to accurately anchor the script's words
        if segments and script_text.strip():
            visible_words = script_text.split()
            if not visible_words:
                return []

            # Map visible words across the segments proportionally by speech duration
            aligned: List[dict] = []
            total_speech_dur = sum(max(0.1, float(s["end"]) - float(s["start"])) for s in segments)
            
            w_idx = 0
            for seg in segments:
                s_start = float(seg["start"])
                s_end = float(seg["end"])
                s_dur = max(0.1, s_end - s_start)
                
                # Number of words for this segment proportional to duration
                share = s_dur / max(0.1, total_speech_dur)
                seg_word_count = max(1, int(round(share * len(visible_words))))
                seg_words = visible_words[w_idx : min(len(visible_words), w_idx + seg_word_count)]
                w_idx += len(seg_words)

                if seg_words:
                    per_w = s_dur / len(seg_words)
                    for i, sw in enumerate(seg_words):
                        aligned.append({
                            "word": sw,
                            "start": round(s_start + i * per_w, 2),
                            "end": round(s_start + (i + 1) * per_w, 2),
                        })

            # Any remaining words land on the last segment
            if w_idx < len(visible_words):
                last_end = float(segments[-1]["end"])
                rem_words = visible_words[w_idx:]
                per_w = 0.3
                for i, sw in enumerate(rem_words):
                    aligned.append({
                        "word": sw,
                        "start": round(last_end + i * per_w, 2),
                        "end": round(last_end + (i + 1) * per_w, 2),
                    })
            return aligned

    except Exception:
        pass

    # Fallback if Whisper is absent or fails
    from pydub import AudioSegment
    try:
        duration = len(AudioSegment.from_file(audio_path)) / 1000.0
    except Exception:
        duration = 0.0

    return _fallback_spread_words(script_text, duration)
