"""Turns a finished PipelineState into a Timeline.

This is the bridge between the agents that exist today and the renderer that
replaced the old assembler. Everything upstream keeps working unchanged; this
reads what the agents produced and writes down the edit.

The one real decision it makes is how long each scene is on screen, and that is
worth spelling out because the old assembler got it wrong in a way that
explains most of what a viewer noticed. It divided the narration equally:

    per_scene_duration = total_duration / len(scene_assets)

Every scene got the same slice whatever was being said over it, so the picture
and the words drifted apart within about thirty seconds. Meanwhile the script
agent had been emitting a `timestamp_estimate` for every scene all along, and
nothing read it.

So durations come from, in order of preference:

1. the script's own `timestamp_estimate` range, when the scenes parse into a
   sensible increasing sequence;
2. the proportion of the script's words that scene contains, which is a good
   approximation because narration is read at a fairly steady pace;
3. an equal split, which is the old behaviour and only happens when there is
   nothing better to go on.

Whatever the source, the result is scaled to land exactly on the voice track's
length. The Timeline is validated to tile the video with no gaps, so a rounding
drift is a hard error rather than a black flash in the finished file.
"""

from __future__ import annotations

import os
import random
import re

import style_profile as sp
from render import audio_mix
from render.motion import build_motion
from timeline import AudioTrack, Caption, GainPoint, Shot, Timeline, Transition, Word

# Sources whose extension is not one of these are treated as video.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}

_TIMESTAMP = re.compile(r"(\d+):(\d{1,2})")


# --------------------------------------------------------------------------
# Scene timing
# --------------------------------------------------------------------------

def _parse_timestamp(text: str) -> float | None:
    match = _TIMESTAMP.search(text or "")
    if not match:
        return None
    minutes, seconds = int(match.group(1)), int(match.group(2))
    return minutes * 60 + seconds


def _spans_from_estimates(scenes: list[dict]) -> list[float] | None:
    """Scene lengths taken from the script's own timestamps.

    Returns None unless every scene has a parseable start and the sequence
    increases - a partially-filled or scrambled set of estimates is worse than
    no estimates, because it would put the picture confidently in the wrong
    place.
    """
    starts = []
    for scene in scenes:
        start = _parse_timestamp(scene.get("timestamp_estimate", ""))
        if start is None:
            return None
        starts.append(start)

    if starts != sorted(starts) or len(set(starts)) != len(starts):
        return None

    # The last scene has no following start, so use its own range end if the
    # estimate carries one, and otherwise the average of the others.
    spans = [later - earlier for earlier, later in zip(starts, starts[1:])]
    if not spans:
        return None

    last = scenes[-1].get("timestamp_estimate", "")
    ends = _TIMESTAMP.findall(last)
    if len(ends) >= 2:
        final = (int(ends[-1][0]) * 60 + int(ends[-1][1])) - starts[-1]
    else:
        final = sum(spans) / len(spans)

    spans.append(max(final, 0.5))
    return spans if all(span > 0 for span in spans) else None


def _spans_from_word_counts(scenes: list[dict]) -> list[float] | None:
    """Scene lengths in proportion to how much is said in each.

    Narration is read at a fairly steady pace, so word count is a decent
    stand-in for time and a great deal better than an equal split.
    """
    counts = [len((scene.get("text") or "").split()) for scene in scenes]
    if not any(counts):
        return None
    # A scene with no words still needs to be on screen for a moment.
    return [float(count) or 0.5 for count in counts]


def scene_durations(scenes: list[dict], total: float) -> list[float]:
    """How long each scene holds the screen, summing exactly to `total`."""
    if not scenes:
        return []
    if len(scenes) == 1:
        return [total]

    spans = _spans_from_estimates(scenes) or _spans_from_word_counts(scenes)
    if not spans:
        spans = [1.0] * len(scenes)

    scale = total / sum(spans)
    durations = [span * scale for span in spans]

    # Absorb floating-point drift into the last scene so the sum is exact;
    # the timeline validator treats a gap as an error, not a rounding detail.
    durations[-1] = total - sum(durations[:-1])
    return durations


# --------------------------------------------------------------------------
# Pieces
# --------------------------------------------------------------------------

def _source_type(path: str) -> str:
    return "image" if os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS else "video"


def _assets_for_scene(scene_assets: list[dict], index: int) -> list[dict]:
    return [a for a in scene_assets if a.get("scene_index") == index and a.get("asset_path")]


def _build_shots(scenes, scene_assets, durations, profile, rng) -> list[Shot]:
    """One shot per usable asset, sharing its scene's time between them.

    A scene is only cut into several shots when there are several *different*
    assets for it. Repeating one clip across a cut is a jump cut on itself,
    which looks worse than simply holding it - so the cut rhythm in the style
    profile can only be honoured as far as the footage allows. Fetching several
    clips per scene is visual-craft work upstream of here.
    """
    shots: list[Shot] = []
    position = 0.0

    for index, (scene, duration) in enumerate(zip(scenes, durations)):
        assets = _assets_for_scene(scene_assets, index)
        hint = scene.get("visual_hint", "")

        if not assets:
            shots.append(Shot(start=position, duration=duration, source_type="color",
                              scene_index=index, label=hint))
            position += duration
            continue

        lengths = _split_evenly(duration, len(assets))
        for asset, length in zip(assets, lengths):
            path = asset["asset_path"]
            kind = asset.get("asset_type") or _source_type(path)
            if kind not in ("video", "image"):
                kind = _source_type(path)

            probability = (
                profile.motion.still_probability if kind == "image"
                else profile.motion.video_probability
            )
            motion = build_motion(profile.motion, rng) if rng.random() < probability else None

            shots.append(Shot(
                start=position, duration=length, source=path, source_type=kind,
                motion=motion, scene_index=index, label=hint,
            ))
            position += length

    return shots


def _split_evenly(total: float, parts: int) -> list[float]:
    if parts <= 1:
        return [total]
    share = total / parts
    lengths = [share] * parts
    lengths[-1] = total - share * (parts - 1)
    return lengths


def _build_captions(word_timestamps, profile) -> list[Caption]:
    """Groups word timings into readable lines."""
    style = profile.captions
    if not style.enabled or not word_timestamps:
        return []

    captions = []
    size = max(1, style.words_per_line)
    for start_index in range(0, len(word_timestamps), size):
        chunk = word_timestamps[start_index:start_index + size]
        words = [
            Word(word=str(w.get("word", "")), start=float(w.get("start", 0)),
                 end=float(w.get("end", 0)))
            for w in chunk
        ]
        text = " ".join(word.word for word in words).strip()
        if not text or words[-1].end <= words[0].start:
            continue
        captions.append(Caption(
            start=words[0].start, end=words[-1].end, text=text, words=words,
        ))
    return captions


def _build_transitions(shots, profile, rng) -> list[Transition]:
    """A transition at every cut except the first, drawn from the profile."""
    transitions = []
    for shot in shots[1:]:
        kind = profile.transitions.pick(rng)
        transitions.append(Transition(
            at=shot.start,
            kind=kind,
            duration=profile.transitions.duration_for(kind),
        ))
    return transitions


def _build_audio(voice_path, duration, profile, music_path) -> list[AudioTrack]:
    tracks = [AudioTrack(source=voice_path, kind="voice", duration=duration)]

    if not (profile.music.enabled and music_path and os.path.exists(music_path)):
        return tracks

    try:
        # Following the narration's own envelope rather than sitting at a fixed
        # offset under it is what lets the bed come back up between sentences.
        curve = audio_mix.duck_curve(voice_path, None, profile.music)
    except Exception:
        curve = [GainPoint(0.0, profile.music.bed_db)]

    tracks.append(AudioTrack(
        source=music_path, kind="music", duration=duration, loop=True,
        gain=curve, fade_in=1.0, fade_out=2.0, label=profile.music.mood_arc[0],
    ))
    return tracks


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def build(state, profile=None, music_path: str = "", seed: int | None = None) -> Timeline:
    """Builds a Timeline from a PipelineState (or a plain dict of one).

    `seed` makes the generated motion and transition choices reproducible,
    which matters because re-rendering the same project should not silently
    produce a different edit.
    """
    data = state if isinstance(state, dict) else state.__dict__
    profile = profile or sp.load()
    rng = random.Random(seed if seed is not None else _seed_from(data.get("run_id", "")))

    voice = data.get("voice_output") or {}
    voice_path = voice.get("audio_path", "")
    if not voice_path or not os.path.exists(voice_path):
        raise ValueError(
            "This run has no voice track on disk, so there is nothing to build a "
            "timeline against. Re-run the voice stage first."
        )

    duration = _audio_duration(voice_path)
    script = data.get("script") or {}
    scenes = script.get("scenes") or [{"text": script.get("script_text", "")}]
    scene_assets = (data.get("visual_output") or {}).get("scene_assets") or []

    durations = scene_durations(scenes, duration)
    shots = _build_shots(scenes, scene_assets, durations, profile, rng)

    timeline = Timeline(
        run_id=data.get("run_id", ""),
        width=profile.width,
        height=profile.height,
        fps=profile.fps,
        duration=duration,
        shots=shots,
        captions=_build_captions(voice.get("word_timestamps") or [], profile),
        audio=_build_audio(voice_path, duration, profile, music_path),
        transitions=_build_transitions(shots, profile, rng),
    )
    timeline.meta = {
        "style_profile": profile.name,
        "caption_style": _caption_style(profile),
        "topic": data.get("topic") or data.get("user_topic") or "",
        "seed": seed,
    }
    return timeline


def _caption_style(profile) -> dict:
    import dataclasses

    return dataclasses.asdict(profile.captions)


def _seed_from(run_id: str) -> int:
    """A stable seed per run, so the same project always cuts the same way."""
    import hashlib

    if not run_id:
        return 0
    return int(hashlib.sha256(run_id.encode()).hexdigest()[:8], 16)


def _audio_duration(path: str) -> float:
    from providers._ffmpeg_setup import ensure_ffmpeg_on_path

    ensure_ffmpeg_on_path()
    from pydub import AudioSegment

    return len(AudioSegment.from_file(path)) / 1000.0
