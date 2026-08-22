"""Candidate window generation, audio/text signal analysis, and viral ranking for clips."""

from __future__ import annotations

import math
import re
from typing import List

from clips.models import CandidateClip, ClipSource, SentenceSpan
from clips.transcript import snap_to_sentence_boundaries

HOOK_KEYWORDS = {
    "why", "how", "secret", "never", "always", "truth", "shocking", "insane",
    "money", "kill", "million", "billion", "first", "realized", "mistake",
    "stop", "actually", "danger", "warning", "kya", "kaise", "kyun", "dekho",
    "sach", "raaz", "galti", "dhyan", "sabse",
}


def _score_hook(first_sentence_text: str) -> tuple[float, list[str]]:
    score = 5.0
    reasons = []
    text_lower = first_sentence_text.lower()

    # Question hook
    if "?" in first_sentence_text or any(text_lower.startswith(w) for w in ("why", "how", "what", "kya", "kaise", "kyun")):
        score += 2.5
        reasons.append("Opens with a strong question hook")

    # High-curiosity keyword count
    words = set(re.findall(r'\w+', text_lower))
    matched_keywords = words.intersection(HOOK_KEYWORDS)
    if matched_keywords:
        bonus = min(2.5, len(matched_keywords) * 0.8)
        score += bonus
        reasons.append(f"Contains high-retention trigger words ({', '.join(list(matched_keywords)[:3])})")

    # Length check: short punchy hooks are better than run-on sentences
    word_count = len(first_sentence_text.split())
    if 4 <= word_count <= 14:
        score += 1.0
        reasons.append("Punchy opening sentence length")
    elif word_count > 25:
        score -= 1.5

    return min(10.0, score), reasons


def _score_window(sentences: List[SentenceSpan]) -> tuple[float, list[str]]:
    if not sentences:
        return 0.0, []

    hook_score, hook_reasons = _score_hook(sentences[0].text)

    # Word pace / density
    total_words = sum(len(s.text.split()) for s in sentences)
    duration = sentences[-1].end - sentences[0].start
    wpm = (total_words / max(duration, 1.0)) * 60.0

    pace_score = 5.0
    pace_reasons = []
    if 130 <= wpm <= 185:
        pace_score += 2.0
        pace_reasons.append(f"Ideal speaking pace ({int(wpm)} WPM)")
    elif wpm < 100:
        pace_score -= 2.0
    elif wpm > 210:
        pace_score -= 1.0

    # Self-containedness
    last_text = sentences[-1].text.strip()
    payoff_score = 5.0
    if re.search(r'[.!?।]$', last_text):
        payoff_score += 1.5

    final_score = (hook_score * 0.45) + (pace_score * 0.30) + (payoff_score * 0.25)
    all_reasons = hook_reasons + pace_reasons

    return round(final_score, 2), all_reasons


def rank_candidate_clips(
    source: ClipSource,
    target_count: int = 3,
    min_duration: float = 20.0,
    max_duration: float = 55.0,
) -> List[CandidateClip]:
    """Scans the source transcript with a sliding sentence window, scoring and selecting the best clips."""
    sentences = source.sentences
    if not sentences:
        # Fallback if no sentences: slice the first 45s of the video
        dur = min(source.duration or 45.0, max_duration)
        return [
            CandidateClip(
                clip_id="clip_1",
                start_time=0.0,
                end_time=dur,
                duration=dur,
                hook_text=source.title or "Opening Hook",
                full_text="",
                score=7.0,
                reasons=["Opening segment default selection"],
                suggested_title=f"{source.title} - Clip 1",
            )
        ]

    candidates: List[CandidateClip] = []

    # Slide start sentence index
    for start_i in range(len(sentences)):
        for end_i in range(start_i, len(sentences)):
            dur = sentences[end_i].end - sentences[start_i].start
            if dur < min_duration:
                continue
            if dur > max_duration:
                break

            window_sentences = sentences[start_i : end_i + 1]
            score, reasons = _score_window(window_sentences)

            full_text = " ".join(s.text for s in window_sentences)
            hook_text = window_sentences[0].text
            suggested_title = hook_text[:50].strip()
            if len(hook_text) > 50:
                suggested_title += "..."

            candidates.append(
                CandidateClip(
                    clip_id=f"clip_{len(candidates) + 1}",
                    start_time=round(sentences[start_i].start, 2),
                    end_time=round(sentences[end_i].end, 2),
                    duration=round(dur, 2),
                    hook_text=hook_text,
                    full_text=full_text,
                    score=score,
                    reasons=reasons,
                    suggested_title=suggested_title,
                )
            )

    # Sort by score descending
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Non-maximum suppression (deduplicate overlapping windows)
    selected: List[CandidateClip] = []
    for cand in candidates:
        overlap = False
        for chosen in selected:
            # Check overlap between [cand.start_time, cand.end_time] and [chosen.start_time, chosen.end_time]
            inter_start = max(cand.start_time, chosen.start_time)
            inter_end = min(cand.end_time, chosen.end_time)
            if inter_end > inter_start:
                inter_dur = inter_end - inter_start
                # If overlap > 35% of either clip, suppress
                if (inter_dur / cand.duration) > 0.35 or (inter_dur / chosen.duration) > 0.35:
                    overlap = True
                    break
        if not overlap:
            cand.clip_id = f"clip_{len(selected) + 1}"
            selected.append(cand)
            if len(selected) >= target_count:
                break

    return selected
