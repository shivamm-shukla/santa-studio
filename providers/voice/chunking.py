"""Long-script chunking and audio stitching for voice synthesis.

Long voice generations suffer from repetition, drift, and memory exhaustion
when passed as one giant block of text to neural TTS models. Splitting on
natural sentence boundaries (respecting both English punctuation and Hindi
purna viram) keeps prosody natural and allows synthesizing arbitrary length
scripts reliably.
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import List, Tuple

from providers._ffmpeg_setup import ensure_ffmpeg_on_path

# Sentence terminators: English . ! ? \n and Hindi purna viram (।)
SENTENCE_SPLIT_REGEX = re.compile(r'([.!?।\n]+)')
CLAUSE_SPLIT_REGEX = re.compile(r'([,;:\-—]+|\s+(?:aur|lekin|par|ki|and|but|or|so)\s+)', re.IGNORECASE)


def chunk_script(text: str, max_chars: int = 200, max_words: int = 35) -> List[str]:
    """Splits text into coherent chunks suitable for TTS synthesis.

    1. Splits on sentence terminators (. ! ? । \n).
    2. If any single sentence is longer than `max_chars` or `max_words`,
       further splits on clause boundaries (commas, semicolons, conjunctions).
    3. Recombines short phrases so we don't synthesize tiny fragments in isolation.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    raw_tokens = SENTENCE_SPLIT_REGEX.split(cleaned)
    sentences: List[str] = []
    current_sentence = ""

    for token in raw_tokens:
        if not token:
            continue
        if SENTENCE_SPLIT_REGEX.match(token):
            current_sentence += token
            s_clean = current_sentence.strip()
            if s_clean:
                sentences.append(s_clean)
            current_sentence = ""
        else:
            current_sentence += token

    if current_sentence.strip():
        sentences.append(current_sentence.strip())

    chunks: List[str] = []
    for sentence in sentences:
        words = sentence.split()
        if len(sentence) <= max_chars and len(words) <= max_words:
            chunks.append(sentence)
        else:
            # Sentence is too long; split on clauses
            clause_tokens = CLAUSE_SPLIT_REGEX.split(sentence)
            accum = ""
            for ct in clause_tokens:
                if not ct:
                    continue
                if len(accum) + len(ct) <= max_chars and len((accum + " " + ct).split()) <= max_words:
                    accum += ct
                else:
                    if accum.strip():
                        chunks.append(accum.strip())
                    accum = ct
            if accum.strip():
                chunks.append(accum.strip())

    # Pack very short adjacent chunks together to avoid fragment overhead
    packed: List[str] = []
    buffer = ""
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        if not buffer:
            buffer = ch
        elif len(buffer) + len(ch) + 1 <= max_chars and (len(buffer.split()) + len(ch.split())) <= max_words:
            buffer = buffer + " " + ch
        else:
            packed.append(buffer)
            buffer = ch

    if buffer:
        packed.append(buffer)

    return packed


def stitch_audio_chunks(
    audio_paths: List[str],
    output_path: str = "",
    pause_ms: int = 250,
    sample_rate: int = 24000,
) -> Tuple[str, List[dict]]:
    """Concatenates multiple audio chunks with a natural micro-pause.

    Returns (output_audio_path, chunk_time_spans) where chunk_time_spans
    records the exact {"start": float, "end": float} offset for each chunk.
    """
    ensure_ffmpeg_on_path()
    from pydub import AudioSegment

    if not audio_paths:
        raise ValueError("No audio chunks provided to stitch.")

    if not output_path:
        handle, output_path = tempfile.mkstemp(suffix=".wav")
        os.close(handle)

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    pause = AudioSegment.silent(duration=pause_ms, frame_rate=sample_rate)
    combined = AudioSegment.silent(duration=0, frame_rate=sample_rate)
    time_spans = []

    current_ms = 0
    for idx, path in enumerate(audio_paths):
        segment = AudioSegment.from_file(path).set_frame_rate(sample_rate).set_channels(1)
        start_sec = current_ms / 1000.0
        dur_ms = len(segment)
        end_sec = (current_ms + dur_ms) / 1000.0

        time_spans.append({"start": round(start_sec, 3), "end": round(end_sec, 3), "duration": round(dur_ms / 1000.0, 3)})

        combined += segment
        current_ms += dur_ms

        if idx < len(audio_paths) - 1 and pause_ms > 0:
            combined += pause
            current_ms += pause_ms

    combined.export(output_path, format="wav")
    return output_path, time_spans
