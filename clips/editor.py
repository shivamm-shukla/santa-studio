"""Clip editor: manual two-pointer trimming, impact effects, color grades, and vertical caption styling."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from clips.models import CandidateClip, ClipProject
from clips.transcript import snap_to_sentence_boundaries
from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.music.sfx import generate_sfx
from timeline import AudioTrack, Caption, GainPoint, Motion, Overlay, Shot, Timeline, Word


COLOR_GRADES = {
    "natural": {"contrast": 1.0, "saturation": 1.0, "brightness": 0.0},
    "cinematic_teal_orange": {"contrast": 1.2, "saturation": 1.25, "brightness": -0.02},
    "warm_punch": {"contrast": 1.15, "saturation": 1.35, "brightness": 0.03},
    "noir_bw": {"contrast": 1.3, "saturation": 0.0, "brightness": -0.05},
    "vintage_film": {"contrast": 1.1, "saturation": 0.85, "brightness": 0.05},
}

# Split by what each one actually is, because they are not the same kind of
# thing: two are drawn over the picture, two move the camera on it, and two
# are sounds. Treating all five as overlays is what left three of them
# producing nothing.
VISUAL_IMPACTS = ("flash", "color_hit")
MOTION_IMPACTS = ("punch_in", "camera_shake")
SFX_IMPACTS = ("whoosh", "bass_drop")
IMPACT_TYPES = VISUAL_IMPACTS + MOTION_IMPACTS + SFX_IMPACTS


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


def _hex_to_rgb(colour: str, fallback=(255, 255, 255)) -> tuple:
    value = (colour or "").lstrip("#")
    if len(value) != 6:
        return fallback
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return fallback


def build_impact_overlays(impact_events: List[dict]) -> List[Overlay]:
    """The *drawn* half of an impact: full-frame flashes and colour hits.

    This used to emit kind="color" and kind="zoom", neither of which is in
    Overlay.KINDS, so anything it produced failed Timeline.validate() and
    could never be rendered - and `camera_shake`, `bass_drop` and `whoosh`
    fell through the if/elif and returned nothing at all, silently.

    A flash is a white box over the whole frame, which the renderer already
    knows how to draw as a `highlight`. The moves (punch_in, camera_shake)
    are not overlays at all - they are camera on the picture underneath, so
    they belong on the shot's Motion; see apply_impact_motion. The audio ones
    (whoosh, bass_drop) are SFX tracks; see build_impact_sfx.
    """
    overlays: List[Overlay] = []
    for event in impact_events:
        kind = event.get("kind", "flash")
        if kind not in VISUAL_IMPACTS:
            continue

        at = max(0.0, float(event.get("at", 0.0)))
        duration = max(0.05, float(event.get("duration", 0.15)))
        colour = event.get("color") or ("#FFFFFF" if kind == "flash" else "#000000")

        overlays.append(Overlay(
            start=at,
            duration=duration,
            kind="highlight",
            position=(0.5, 0.5),
            anchor="center",
            style={
                "size": (1.0, 1.0),
                "color_rgb": _hex_to_rgb(colour),
                "opacity": float(event.get("opacity", 0.8 if kind == "flash" else 0.55)),
            },
            animate_in="fade",
            animate_out="fade",
        ))

    return overlays


def apply_impact_motion(shots: List[Shot], impact_events: List[dict]) -> List[Shot]:
    """The *camera* half: a punch-in or a shake on whichever shot is running.

    Returns the shots with Motion attached. A punch-in pushes the frame in
    towards the centre over the shot; a shake offsets it slightly off-axis so
    the picture kicks. Both are expressed as the Motion the renderer already
    animates, so nothing new is needed downstream.
    """
    if not shots:
        return shots

    for event in impact_events:
        kind = event.get("kind")
        if kind not in MOTION_IMPACTS:
            continue
        at = float(event.get("at", 0.0))

        target = next(
            (s for s in shots if s.start <= at < s.start + s.duration),
            None,
        )
        if target is None:
            continue

        if kind == "punch_in":
            scale = max(0.05, min(0.45, float(event.get("scale", 1.25)) - 1.0))
            inset = scale / 2
            target.motion = Motion(
                start_rect=(0.0, 0.0, 1.0, 1.0),
                end_rect=(inset, inset, 1.0 - scale, 1.0 - scale),
                easing="ease_out",
            )
        else:  # camera_shake
            offset = max(0.01, min(0.08, float(event.get("amount", 0.03))))
            size = 1.0 - offset * 2
            target.motion = Motion(
                start_rect=(0.0, offset, size, size),
                end_rect=(offset * 2, 0.0, size, size),
                easing="linear",
            )

    return shots


def build_impact_sfx(impact_events: List[dict], sfx_db: float = -14.0) -> List[AudioTrack]:
    """The *heard* half: whooshes and bass drops.

    generate_sfx has been imported by this module since it was written and
    was never called - these two impact types produced silence.
    """
    tracks: List[AudioTrack] = []
    for event in impact_events:
        kind = event.get("kind")
        if kind not in SFX_IMPACTS:
            continue

        try:
            source = generate_sfx("whoosh" if kind == "whoosh" else "impact")
        except Exception:
            continue

        tracks.append(AudioTrack(
            source=source,
            kind="sfx",
            start=round(max(0.0, float(event.get("at", 0.0))), 2),
            duration=float(event.get("duration", 0.45 if kind == "whoosh" else 1.2)),
            gain=[GainPoint(0.0, float(event.get("db", sfx_db)))],
            label=f"sfx_{kind}",
        ))
    return tracks


def apply_color_grade(timeline: Timeline, look: str) -> Timeline:
    """Records a named colour grade on the timeline for the renderer.

    COLOR_GRADES was a table nothing read - defined, exported, asserted by
    its own test, and never applied to anything. Writing it into meta means
    it survives a save/load round trip and re-rendering an adjustment costs
    nothing, which is the point of keeping the edit as data.
    """
    if look not in COLOR_GRADES:
        raise ValueError(f"Unknown colour grade {look!r}. Available: {sorted(COLOR_GRADES)}")
    timeline.meta = dict(timeline.meta or {})
    timeline.meta["color_grade"] = {"look": look, **COLOR_GRADES[look]}
    return timeline
