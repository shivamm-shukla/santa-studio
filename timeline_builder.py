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

import graphics
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


# How many times one clip may be cut back to within a scene. Stock footage
# runs 10-20 seconds, so a third pass into the same file is usually reading
# past the end of it - the renderer holds the last frame there, which is
# quiet but not interesting.
MAX_REUSE_VIDEO = 3
# A still is only ever on screen once per scene. Cutting from a photograph
# back to the same photograph is a jump cut on itself however the Ken Burns
# move is angled, and reads as a mistake rather than as an edit.
MAX_REUSE_IMAGE = 1


def _asset_kind(asset: dict) -> str:
    kind = asset.get("asset_type") or _source_type(asset["asset_path"])
    return kind if kind in ("video", "image") else _source_type(asset["asset_path"])


def _rhythm_lengths(total: float, count: int, profile, rng) -> list[float]:
    """`count` shot lengths summing to `total`, jittered by the profile.

    CutRhythm.shot_lengths picks its own count from the target cadence. This
    is the same idea with the count fixed, for when the available footage
    caps how many times a scene can be cut.
    """
    if count <= 1:
        return [total]
    variance = profile.cut.variance
    weights = [1.0 + rng.uniform(-variance, variance) for _ in range(count)]
    scale = total / sum(weights)
    lengths = [w * scale for w in weights]
    lengths[-1] = total - sum(lengths[:-1])
    return lengths


def _plan_scene(duration: float, assets: list[dict], profile, rng) -> list[tuple[float, dict]]:
    """(length, asset) for each shot in one scene, at the profile's cadence.

    The style profile asks for a cut every few seconds; the footage decides
    how far that can be honoured. A scene with one 20-second slot and one
    video gets cut into several shots reading successive sections of that
    clip, which is a real edit. The same slot with one photograph stays a
    single shot with a Ken Burns move over it, because cutting a still to
    itself is not.
    """
    if not assets:
        return []

    capacity = sum(
        MAX_REUSE_VIDEO if _asset_kind(a) == "video" else MAX_REUSE_IMAGE for a in assets
    )
    # Drawn once: calling shot_lengths again would advance the generator and
    # produce a different plan from the one whose length was measured.
    planned = profile.cut.shot_lengths(duration, rng)
    count = max(len(assets), min(len(planned), capacity))

    lengths = planned if count == len(planned) else _rhythm_lengths(duration, count, profile, rng)

    # Round-robin so a scene alternates between the clips it has rather than
    # exhausting one before touching the next.
    return [(length, assets[i % len(assets)]) for i, length in enumerate(lengths)]


def _build_shots(scenes, scene_assets, durations, profile, rng) -> list[Shot]:
    """Cuts each scene at the style profile's rhythm, across what it has.

    Before this the number of shots was simply the number of assets fetched,
    so a scene with one clip held it for its whole slot however long that
    was - and the cut rhythm in the style profile, which is the knob that
    decides whether a video reads as edited or as a slideshow, was never
    consulted by anything.
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

        # Where we have already read up to inside each source, so cutting
        # back to a clip shows a different part of it rather than replaying
        # the same seconds.
        consumed: dict[str, float] = {}

        for length, asset in _plan_scene(duration, assets, profile, rng):
            path = asset["asset_path"]
            kind = _asset_kind(asset)

            probability = (
                profile.motion.still_probability if kind == "image"
                else profile.motion.video_probability
            )
            motion = build_motion(profile.motion, rng) if rng.random() < probability else None

            in_point = consumed.get(path, 0.0) if kind == "video" else 0.0
            consumed[path] = in_point + length

            shots.append(Shot(
                start=position, duration=length, source=path, source_type=kind,
                in_point=round(in_point, 3), motion=motion, scene_index=index, label=hint,
            ))
            position += length

    return shots


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


def _build_audio(voice_path, duration, profile, music_path, scenes=None, transitions=None, overlays=None) -> list[AudioTrack]:
    from providers.music.director import MusicDirector

    if music_path:
        if not os.path.exists(music_path):
            return [AudioTrack(source=voice_path, kind="voice", duration=duration)]
        class StaticMusicProvider:
            def search(self, mood="curious"):
                return {"track_path": music_path}
        director = MusicDirector(music_provider=StaticMusicProvider())
    else:
        director = MusicDirector()

    return director.build_audio_tracks(
        voice_path=voice_path,
        total_duration=duration,
        profile=profile,
        scenes=scenes,
        transitions=transitions,
        overlays=overlays,
    )


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
    transitions = _build_transitions(shots, profile, rng)

    word_timestamps = voice.get("word_timestamps") or []
    overlays = graphics.build_overlays(
        word_timestamps,
        duration,
        profile,
        topic=data.get("topic") or data.get("user_topic") or "",
        sources=(data.get("research") or {}).get("sources"),
    )

    timeline = Timeline(
        run_id=data.get("run_id", ""),
        width=profile.width,
        height=profile.height,
        fps=profile.fps,
        duration=duration,
        shots=shots,
        overlays=overlays,
        captions=_build_captions(word_timestamps, profile),
        audio=_build_audio(voice_path, duration, profile, music_path, scenes=scenes, transitions=transitions, overlays=overlays),
        transitions=transitions,
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
