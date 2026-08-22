"""Transcript processing and sentence boundary segmentation for clips."""

from __future__ import annotations

import re
from typing import List, Tuple

from clips.models import SentenceSpan, TranscriptWord


def words_to_sentences(words: List[TranscriptWord]) -> List[SentenceSpan]:
    """Groups word-level timestamps into complete, timed SentenceSpan objects."""
    if not words:
        return []

    sentences: List[SentenceSpan] = []
    current_words: List[TranscriptWord] = []

    for i, w in enumerate(words):
        current_words.append(w)
        word_clean = w.word.strip()

        # Check for sentence terminators (. ! ? or Hindi ।) or long silence break before next word
        is_terminator = bool(re.search(r'[.!?।]$', word_clean))
        has_long_pause = False
        if i + 1 < len(words):
            gap = words[i + 1].start - w.end
            if gap >= 0.75:  # natural pause boundary
                has_long_pause = True

        if is_terminator or has_long_pause or i == len(words) - 1:
            text = " ".join(item.word for item in current_words).strip()
            if text:
                span = SentenceSpan(
                    text=text,
                    start=current_words[0].start,
                    end=current_words[-1].end,
                    words=list(current_words),
                )
                sentences.append(span)
            current_words = []

    return sentences


def snap_to_sentence_boundaries(
    start_time: float,
    end_time: float,
    sentences: List[SentenceSpan],
    max_duration: float = 60.0,
    min_duration: float = 20.0,
) -> Tuple[float, float, List[SentenceSpan]]:
    """Snaps arbitrary start/end timestamps to the closest enclosing sentence boundaries."""
    if not sentences:
        return (start_time, end_time, [])

    # Find starting sentence (first sentence ending >= start_time)
    start_idx = 0
    for i, s in enumerate(sentences):
        if s.end >= start_time:
            start_idx = i
            break

    # Find ending sentence
    end_idx = start_idx
    for i in range(start_idx, len(sentences)):
        s = sentences[i]
        dur = s.end - sentences[start_idx].start
        if s.end <= end_time + 1.5 or dur < min_duration:
            end_idx = i
        if dur >= max_duration:
            break

    matched_sentences = sentences[start_idx : end_idx + 1]
    if not matched_sentences:
        return (start_time, end_time, [])

    final_start = matched_sentences[0].start
    final_end = matched_sentences[-1].end
    return (final_start, final_end, matched_sentences)
