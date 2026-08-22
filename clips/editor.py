"""Clip editor: manual two-pointer trimming, impact effects, color grades, and vertical caption styling."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from clips.models import CandidateClip, ClipProject
from clips.transcript import snap_to_sentence_boundaries
from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.music.sfx import generate_sfx
from timeline import Caption, Overlay, Timeline, Word


COLOR_GRADES = {
    "natural": {"contrast": 1.0, "saturation": 1.0, "brightness": 0.0},
    "cinematic_teal_orange": {"contrast": 1.2, "saturation": 1.25, "brightness": -0.02},
    "warm_punch": {"contrast": 1.15, "saturation": 1.35, "brightness": 0.03},
    "noir_bw": {"contrast": 1.3, "saturation": 0.0, "brightness": -0.05},
    "vintage_film": {"contrast": 1.1, "saturation": 0.85, "brightness": 0.05},
}

IMPACT_TYPES = ("punch_in", "camera_shake", "flash", "bass_drop", "whoosh")


def adjust_clip_range(
    project: ClipProject,
    clip_id: str,
    new_start: float,
    new_end: float,
    snap_to_sentences: bool = True,
) -> CandidateClip:
    """Manual two-pointer override: adjusts the clip's start/end points with sentence snapping."""
    target_clip = next((c for c in project.candidates if c.clip_id == clip_id), None)
    if not target_clip:
        raise ValueError(f"Clip {clip_id!r} not found in project {project.project_id!r}")

    if snap_to_sentences and project.source.sentences:
        final_start, final_end, matched = snap_to_sentence_boundaries(
            new_start, new_end, project.source.sentences, min_duration=5.0, max_duration=90.0
        )
        full_text = " ".join(s.text for s in matched)
        hook_text = matched[0].text if matched else target_clip.hook_text
    else:
        final_start = max(0.0, new_start)
        final_end = min(project.source.duration or new_end, new_end)
        full_text = target_clip.full_text
        hook_text = target_clip.hook_text

    target_clip.start_time = round(final_start, 2)
    target_clip.end_time = round(final_end, 2)
    target_clip.duration = round(final_end - final_start, 2)
    target_clip.full_text = full_text
    target_clip.hook_text = hook_text
    target_clip.reasons.append("Manually adjusted via two-pointer editor")

    return target_clip


def build_vertical_captions(
    words: List[dict],
    start_time: float,
    end_time: float,
    style_preset: str = "hormozi",
    words_per_card: int = 3,
) -> List[Caption]:
    """Generates vertical short-form animated captions (Hormozi / MrBeast style)."""
    # Filter words within the clip range
    clip_words = [
        w for w in words
        if w.get("start", 0.0) >= start_time - 0.2 and w.get("end", 0.0) <= end_time + 0.2
    ]

    captions: List[Caption] = []
    for i in range(0, len(clip_words), words_per_card):
        chunk = clip_words[i : i + words_per_card]
        if not chunk:
            continue

        c_start = max(0.0, chunk[0]["start"] - start_time)
        c_end = max(c_start + 0.2, chunk[-1]["end"] - start_time)

        card_words = [
            Word(
                word=w["word"].upper(),
                start=max(0.0, w["start"] - start_time),
                end=max(0.0, w["end"] - start_time),
            )
            for w in chunk
        ]

        text_str = " ".join(w.word for w in card_words)
        captions.append(
            Caption(
                start=c_start,
                end=c_end,
                text=text_str,
                words=card_words,
            )
        )

    return captions


def build_impact_overlays(
    impact_events: List[dict],
) -> List[Overlay]:
    """Builds visual impact effect overlays (punch-in, flash, shake)."""
    overlays: List[Overlay] = []
    for ev in impact_events:
        kind = ev.get("kind", "flash")
        at = float(ev.get("at", 0.0))
        duration = float(ev.get("duration", 0.15))

        if kind == "flash":
            overlays.append(
                Overlay(
                    start=at,
                    duration=duration,
                    kind="color",
                    style={"color": "#FFFFFF", "opacity": 0.8},
                    anchor="center",
                )
            )
        elif kind == "punch_in":
            overlays.append(
                Overlay(
                    start=at,
                    duration=duration,
                    kind="zoom",
                    style={"scale": 1.25},
                    anchor="center",
                )
            )

    return overlays
