"""Analyzes reference video metadata/transcripts and synthesizes a StyleProfile.

Converts structural observations (pacing, hook duration, music mood, graphics density)
into a concrete, serializable StyleProfile in the library for reuse across runs.
"""

from __future__ import annotations

import re
from typing import List, Optional

import paths
import style_profile as sp
from style_profile import (
    CaptionStyle,
    CutRhythm,
    GraphicsStyle,
    MotionStyle,
    MusicStyle,
    NarrationStyle,
    StyleProfile,
    TransitionStyle,
)


def analyze_and_synthesize(
    ingest_data: dict,
    llm_analysis: Optional[dict] = None,
    save_to_library: bool = True,
) -> StyleProfile:
    """Synthesizes a StyleProfile from reference video analysis."""
    channel_slug = ingest_data.get("channel_slug") or "custom_reference"
    duration = ingest_data.get("duration", 600.0)
    word_count = ingest_data.get("word_count", 1500)

    # Estimate words per minute
    if duration > 30 and word_count > 0:
        measured_wpm = max(110, min(220, int((word_count / duration) * 60)))
    else:
        measured_wpm = 150

    # Determine pacing parameters
    if measured_wpm > 165:
        target_cut = 2.5
        min_cut, max_cut = 1.5, 4.5
        variance = 0.4
        motion_intensity = 0.7
        graphics_density = 10.0
        mood_arc = ("energetic", "cinematic", "energetic")
    elif measured_wpm < 135:
        target_cut = 6.0
        min_cut, max_cut = 3.5, 10.0
        variance = 0.25
        motion_intensity = 0.35
        graphics_density = 3.0
        mood_arc = ("calm", "curious", "calm")
    else:
        target_cut = 4.0
        min_cut, max_cut = 2.5, 7.5
        variance = 0.3
        motion_intensity = 0.5
        graphics_density = 6.0
        mood_arc = ("curious", "cinematic", "mysterious", "cinematic")

    profile = StyleProfile(
        name=channel_slug,
        description=f"Style extracted from reference {ingest_data.get('url', channel_slug)}",
        source=f"analyzed:{ingest_data.get('channel', channel_slug)}",
        width=1920,
        height=1080,
        fps=30,
        cut=CutRhythm(target_seconds=target_cut, min_seconds=min_cut, max_seconds=max_cut, variance=variance),
        motion=MotionStyle(still_probability=1.0, video_probability=0.2, intensity=motion_intensity),
        captions=CaptionStyle(words_per_line=4, highlight_spoken_word=True, emphasize_keywords=True),
        graphics=GraphicsStyle(density=graphics_density, animate_in="slide_up"),
        music=MusicStyle(mood_arc=mood_arc),
        transitions=TransitionStyle(weights={"cut": 0.7, "crossfade": 0.2, "dip_to_black": 0.1}),
        narration=NarrationStyle(words_per_minute=measured_wpm, hook_seconds=15.0),
    )

    if save_to_library:
        try:
            profile.save()
        except Exception:
            pass

    return profile
