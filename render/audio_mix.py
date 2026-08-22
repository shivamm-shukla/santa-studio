"""Mixes a Timeline's audio tracks down to one file.

This is where the automation curve on an AudioTrack stops being data and
becomes an actual change in level. The old pipeline had one number for the
whole video - `bg_clip.with_volume_scaled(0.12)` - so the score sat at a fixed
distance behind the narration from the first second to the last, which is what
a bed of wallpaper sounds like rather than scoring.

The mix is done with pydub rather than inside the video renderer for three
reasons: it is far quicker than resampling audio through a video pipeline, it
runs without importing MoviePy at all so it can be tested on its own, and it
means the video renderer receives a single finished track and never has to
think about levels.

Rendering a curve is a matter of slicing the track and applying a constant gain
to each slice. Slice boundaries are chosen from the curve itself rather than on
a fixed grid: a section holding a steady level is one slice however long it is,
and only the parts that actually move get subdivided. A twenty minute video
with a handful of cues costs a few hundred slices instead of twenty-four
thousand.
"""

from __future__ import annotations

import math
import os

from providers._ffmpeg_setup import ensure_ffmpeg_on_path

ensure_ffmpeg_on_path()

from pydub import AudioSegment  # noqa: E402

# Finest and coarsest slice the automation renderer will produce. The floor
# stops a steep curve from generating thousands of one-millisecond slices; the
# ceiling stops a slow curve from being rendered as audible steps.
MIN_SLICE_MS = 40
MAX_SLICE_MS = 250

# A change smaller than this is inaudible, so there is no reason to cut a new
# slice for it.
DB_RESOLUTION = 0.5

# Anything at or below this is silence as far as the mixer is concerned.
SILENCE_FLOOR_DB = -80.0

SAMPLE_RATE = 44100


def _load(path: str) -> AudioSegment:
    if not path or not os.path.exists(path):
        raise FileNotFoundError(f"Audio source {path!r} does not exist")
    return AudioSegment.from_file(path)


def _slice_points(track, length_ms: int) -> list[int]:
    """Millisecond boundaries at which this track's gain should be re-applied.

    Derived from the curve rather than from a grid. The curve is piecewise
    linear, so each segment between two gain points is examined on its own: a
    segment that holds a steady level is one slice no matter how long it runs,
    and a segment that moves is divided into just enough steps that no single
    step jumps by more than DB_RESOLUTION. A twenty minute bed sitting at one
    level costs a single slice; a fast duck costs a handful.

    MAX_SLICE_MS applies only where the level is changing - it exists to keep a
    slow ramp from being rendered as audible stair steps, and there are no
    steps to hear across a flat stretch.
    """
    if len(track.gain) < 2:
        return [0, length_ms]

    ordered = sorted(track.gain, key=lambda p: p.time)
    # The curve holds its end values outside the range it covers, so treat
    # everything before the first point and after the last as flat.
    edges = [0.0] + [p.time * 1000 for p in ordered] + [float(length_ms)]

    points = [0]
    for start_ms, end_ms in zip(edges, edges[1:]):
        start_ms = max(0.0, min(start_ms, length_ms))
        end_ms = max(0.0, min(end_ms, length_ms))
        if end_ms <= start_ms:
            continue

        delta_db = abs(track.gain_at(end_ms / 1000.0) - track.gain_at(start_ms / 1000.0))
        if delta_db <= DB_RESOLUTION:
            steps = 1
        else:
            span = end_ms - start_ms
            steps = int(math.ceil(delta_db / DB_RESOLUTION))
            # Clamp so a step is neither pointlessly fine nor audibly coarse.
            steps = max(1, min(steps, int(span // MIN_SLICE_MS) or 1))
            steps = max(steps, int(math.ceil(span / MAX_SLICE_MS)))

        width = (end_ms - start_ms) / steps
        for index in range(1, steps + 1):
            boundary = int(round(start_ms + width * index))
            if boundary > points[-1]:
                points.append(min(boundary, length_ms))

    if points[-1] != length_ms:
        points.append(length_ms)
    return points


def _apply_automation(segment: AudioSegment, track) -> AudioSegment:
    """Renders the track's gain curve onto the audio."""
    if not track.gain:
        return segment
    if len(track.gain) == 1:
        return segment.apply_gain(track.gain[0].db)

    boundaries = _slice_points(track, len(segment))
    pieces = []
    for start_ms, end_ms in zip(boundaries, boundaries[1:]):
        if end_ms <= start_ms:
            continue
        piece = segment[start_ms:end_ms]
        # Sampled at the midpoint so a slice sits on the curve rather than
        # lagging behind it.
        db = track.gain_at(((start_ms + end_ms) / 2) / 1000.0)
        pieces.append(piece if db >= 0 and db == 0 else piece.apply_gain(db))

    if not pieces:
        return segment
    mixed = pieces[0]
    for piece in pieces[1:]:
        mixed += piece
    return mixed


def _fit_length(segment: AudioSegment, track, wanted_ms: int) -> AudioSegment:
    """Trims or loops `segment` to `wanted_ms`."""
    if wanted_ms <= 0:
        return segment

    if len(segment) < wanted_ms:
        if not track.loop:
            # Pad rather than stretch: a music cue shorter than its slot should
            # end where it ends, not be time-warped to fit.
            return segment + AudioSegment.silent(
                duration=wanted_ms - len(segment), frame_rate=segment.frame_rate
            )
        repeats = math.ceil(wanted_ms / max(len(segment), 1))
        segment = segment * repeats

    return segment[:wanted_ms]


def render_track(track, timeline_duration: float) -> AudioSegment:
    """One AudioTrack as a positioned, leveled, faded AudioSegment."""
    segment = _load(track.source)

    start_ms = int(track.in_point * 1000)
    if start_ms:
        segment = segment[start_ms:]

    wanted_ms = int(track.duration * 1000) if track.duration else len(segment)
    # Never let a track run past the end of the video.
    room_ms = max(0, int((timeline_duration - track.start) * 1000))
    wanted_ms = min(wanted_ms, room_ms) if room_ms else wanted_ms

    segment = _fit_length(segment, track, wanted_ms)
    segment = _apply_automation(segment, track)

    if track.fade_in:
        segment = segment.fade_in(min(int(track.fade_in * 1000), len(segment)))
    if track.fade_out:
        segment = segment.fade_out(min(int(track.fade_out * 1000), len(segment)))

    return segment


def duck_curve(voice_path: str, timeline, style, resolution_ms: int = 100) -> list:
    """Builds a music gain curve that follows where the narration actually is.

    A fixed offset under the voice track ducks the music through the pauses too,
    which is the flat, lifeless result the old mix produced. Measuring the
    narration's own envelope instead means the bed comes back up between
    sentences and drops again when speech resumes - the difference between a
    score that breathes and one that just sits there.

    Returns GainPoint values, so the caller can hand them straight to a track.
    """
    from timeline import GainPoint

    voice = _load(voice_path)
    total_ms = len(voice)
    if total_ms == 0:
        return [GainPoint(0.0, style.bed_db)]

    # A window is "speech" if it is meaningfully louder than the quietest part
    # of the recording, which adapts to whatever level the voice was recorded
    # at instead of assuming a fixed threshold.
    windows = [voice[i:i + resolution_ms] for i in range(0, total_ms, resolution_ms)]
    levels = [w.dBFS for w in windows if w.dBFS != float("-inf")]
    if not levels:
        return [GainPoint(0.0, style.bed_db)]

    floor = min(levels)
    ceiling = max(levels)
    threshold = floor + (ceiling - floor) * 0.35

    speaking = [
        (w.dBFS != float("-inf") and w.dBFS >= threshold) for w in windows
    ]

    points: list[GainPoint] = []
    previous = None
    for index, is_speech in enumerate(speaking):
        if is_speech == previous:
            continue
        at = index * resolution_ms / 1000.0
        if is_speech:
            # Duck ahead of the word so the level has already moved by the time
            # the voice arrives.
            points.append(GainPoint(max(0.0, at - style.duck_attack), style.bed_db))
            points.append(GainPoint(at, style.duck_db))
        else:
            points.append(GainPoint(at, style.duck_db))
            points.append(GainPoint(at + style.duck_release, style.bed_db))
        previous = is_speech

    if not points:
        return [GainPoint(0.0, style.bed_db)]
    if points[0].time > 0:
        points.insert(0, GainPoint(0.0, style.bed_db))
    return points


def mix(timeline, output_path: str) -> str:
    """Mixes every track in `timeline` down to a single wav at `output_path`.

    Tracks are laid onto a silent bed of the timeline's full length, so a cue
    that starts at 3:20 lands at 3:20 whatever else is playing.
    """
    duration_ms = int(timeline.duration * 1000)
    if duration_ms <= 0:
        raise ValueError("Cannot mix audio for a timeline with no duration")

    bed = AudioSegment.silent(duration=duration_ms, frame_rate=SAMPLE_RATE)

    for index, track in enumerate(timeline.audio):
        try:
            segment = render_track(track, timeline.duration)
        except FileNotFoundError:
            if track.kind == "voice":
                raise
            continue  # a missing music cue or effect is not worth failing over

        if segment.frame_rate != SAMPLE_RATE:
            segment = segment.set_frame_rate(SAMPLE_RATE)
        if segment.channels != 2:
            segment = segment.set_channels(2)

        bed = bed.overlay(segment, position=int(track.start * 1000))

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    bed.export(output_path, format="wav")
    return output_path


def normalize_to_lufs(path: str, target_db: float = -14.0) -> str:
    """Brings the finished mix to roughly YouTube's target loudness.

    This is an RMS approximation rather than a true EBU R128 measurement - it
    needs no extra dependency and lands close enough that YouTube's own
    normalisation does not have to move the track far. A real loudness meter is
    a later refinement, not a blocker.
    """
    audio = AudioSegment.from_file(path)
    if audio.dBFS == float("-inf"):
        return path
    audio.apply_gain(target_db - audio.dBFS).export(path, format="wav")
    return path
