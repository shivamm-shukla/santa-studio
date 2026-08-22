"""The Timeline: an edit decision list that agents write and a renderer reads.

Agents used to call the renderer directly, which meant every editorial decision
was made and consumed inside one function call and existed nowhere you could
look at it. Anything that needed to vary *across* a video - music that swells
under a reveal and drops under dense narration, a different motion path per
shot, a caption emphasised on one word - had nowhere to be written down. The
whole of the old sound design was a single constant: one volume number applied
to the entire video.

So agents now emit a Timeline instead, and a renderer turns it into a file:

    research -> script -> agents write a Timeline -> renderer -> mp4

Four things fall out of that split:

* Automation becomes expressible. Gain is a list of (time, decibel) points, not
  a scalar, so "quieter here, louder there" is just data.
* The renderer is swappable - MoviePy now, an FFmpeg filtergraph when speed
  matters - because it only has to satisfy this schema.
* Re-rendering costs nothing. Edit a caption, render again, spend no LLM calls.
  That matters a great deal when running on free API tiers.
* It can be tested. You can assert things about a Timeline; you cannot
  meaningfully assert things about an mp4.

Times are seconds from the start of the video, as floats. Rectangles are
normalised to 0..1 of the frame so a motion path survives a change of
resolution.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

SCHEMA_VERSION = 1

# Rendering is allowed to disagree with the declared duration by this much
# before validation complains. Encoders round to frame boundaries, and audio
# and video durations rarely land on exactly the same sample.
DURATION_TOLERANCE = 0.05


# --------------------------------------------------------------------------
# Motion
# --------------------------------------------------------------------------

@dataclass
class Motion:
    """A Ken Burns move across a still, or a slow drift across footage.

    `start_rect` and `end_rect` are (x, y, w, h) in 0..1 of the *source*, so
    (0, 0, 1, 1) is the whole frame and (0.1, 0.1, 0.6, 0.6) is a crop pushed
    in and slightly off-centre. Zoom is the difference in area between the two;
    a pan is the same size in both with different origins.
    """

    start_rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    end_rect: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    easing: str = "ease_in_out"  # linear | ease_in | ease_out | ease_in_out

    EASINGS = ("linear", "ease_in", "ease_out", "ease_in_out")

    @property
    def is_static(self) -> bool:
        return tuple(self.start_rect) == tuple(self.end_rect)

    def problems(self, where: str) -> list[str]:
        out = []
        if self.easing not in self.EASINGS:
            out.append(f"{where}: unknown easing {self.easing!r}")
        for name, rect in (("start_rect", self.start_rect), ("end_rect", self.end_rect)):
            if len(rect) != 4:
                out.append(f"{where}.{name}: expected 4 values, got {len(rect)}")
                continue
            x, y, w, h = rect
            if w <= 0 or h <= 0:
                out.append(f"{where}.{name}: width and height must be positive")
            if not (0 <= x <= 1 and 0 <= y <= 1):
                out.append(f"{where}.{name}: origin {(x, y)} is outside the frame")
            if x + w > 1.0001 or y + h > 1.0001:
                out.append(f"{where}.{name}: rect extends past the frame edge")
        return out


# --------------------------------------------------------------------------
# Visual
# --------------------------------------------------------------------------

@dataclass
class Shot:
    """One continuous piece of picture on screen.

    A scene from the script usually becomes several shots - holding a single
    clip for thirty seconds is what makes a video read as a slideshow - so
    `scene_index` records which script scene a shot serves rather than
    assuming the two are one to one.
    """

    start: float
    duration: float
    source: str = ""                 # path on disk; empty means a solid colour
    source_type: str = "video"       # video | image | color
    in_point: float = 0.0            # where to start reading inside the source
    motion: Motion | None = None
    fit: str = "cover"               # cover crops to fill, contain letterboxes
    color: tuple[int, int, int] = (18, 18, 22)
    scene_index: int = 0
    label: str = ""                  # human note, e.g. the visual hint used

    SOURCE_TYPES = ("video", "image", "color")
    FITS = ("cover", "contain")

    @property
    def end(self) -> float:
        return self.start + self.duration

    def problems(self, index: int) -> list[str]:
        where = f"shots[{index}]"
        out = []
        if self.duration <= 0:
            out.append(f"{where}: duration must be positive, got {self.duration}")
        if self.start < 0:
            out.append(f"{where}: start must not be negative, got {self.start}")
        if self.source_type not in self.SOURCE_TYPES:
            out.append(f"{where}: unknown source_type {self.source_type!r}")
        if self.fit not in self.FITS:
            out.append(f"{where}: unknown fit {self.fit!r}")
        if self.source_type != "color" and not self.source:
            out.append(f"{where}: source_type {self.source_type!r} needs a source path")
        if self.in_point < 0:
            out.append(f"{where}: in_point must not be negative")
        if self.motion:
            out.extend(self.motion.problems(where + ".motion"))
        return out


@dataclass
class Overlay:
    """Anything drawn on top of the picture that is not a caption.

    This is the layer the old pipeline had none of, and it is most of what
    separates an explainer from a slideshow: callouts, counting numbers,
    timelines, arrows, boxes drawn around the thing being talked about.
    """

    start: float
    duration: float
    kind: str = "text"               # text | lower_third | counter | highlight | image
    text: str = ""
    source: str = ""                 # for kind="image"
    position: tuple[float, float] = (0.5, 0.5)   # normalised anchor point
    anchor: str = "center"           # center | top_left | bottom_left | ...
    style: dict = field(default_factory=dict)    # font, size, colors - renderer reads
    animate_in: str = "fade"         # none | fade | slide_up | slide_left | pop
    animate_out: str = "fade"
    data: dict = field(default_factory=dict)     # kind-specific, e.g. counter from/to

    KINDS = ("text", "lower_third", "counter", "highlight", "image")
    ANIMATIONS = ("none", "fade", "slide_up", "slide_down", "slide_left", "slide_right", "pop")

    @property
    def end(self) -> float:
        return self.start + self.duration

    def problems(self, index: int) -> list[str]:
        where = f"overlays[{index}]"
        out = []
        if self.duration <= 0:
            out.append(f"{where}: duration must be positive, got {self.duration}")
        if self.start < 0:
            out.append(f"{where}: start must not be negative")
        if self.kind not in self.KINDS:
            out.append(f"{where}: unknown kind {self.kind!r}")
        if self.kind == "image" and not self.source:
            out.append(f"{where}: kind 'image' needs a source path")
        if self.kind in ("text", "lower_third", "counter") and not self.text and not self.data:
            out.append(f"{where}: kind {self.kind!r} has nothing to draw")
        for name, value in (("animate_in", self.animate_in), ("animate_out", self.animate_out)):
            if value not in self.ANIMATIONS:
                out.append(f"{where}: unknown {name} {value!r}")
        return out


@dataclass
class Word:
    word: str
    start: float
    end: float


@dataclass
class Caption:
    """One on-screen line, with the per-word timings behind it.

    Word timings are kept even though a line is displayed as a unit, because
    highlighting the word currently being spoken is a large part of why modern
    captions feel alive, and throwing the timings away here would mean asking
    for them again later.
    """

    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)
    emphasis: list[int] = field(default_factory=list)  # indices into words
    style: dict = field(default_factory=dict)

    def problems(self, index: int) -> list[str]:
        where = f"captions[{index}]"
        out = []
        if self.end <= self.start:
            out.append(f"{where}: end must be after start ({self.start} -> {self.end})")
        if not self.text.strip():
            out.append(f"{where}: empty caption text")
        for i in self.emphasis:
            if not 0 <= i < len(self.words):
                out.append(f"{where}: emphasis index {i} has no matching word")
        return out


# --------------------------------------------------------------------------
# Audio
# --------------------------------------------------------------------------

@dataclass
class GainPoint:
    """A single point on a volume automation curve, in decibels.

    Decibels rather than a linear scale because that is how the change is
    actually perceived, and because a duck is naturally expressed as "-18 dB
    under speech" rather than as a multiplier.
    """

    time: float
    db: float


@dataclass
class AudioTrack:
    """One audio layer: the narration, a music cue, or a single effect.

    `gain` is the reason this schema exists. A flat bed is one point; a bed
    that swells into a reveal and pulls back under dense narration is several,
    interpolated between. Music is a sequence of cues on this track rather than
    one file looped for the length of the video, so the score can follow the
    shape of the script.
    """

    source: str
    kind: str = "music"              # voice | music | sfx
    start: float = 0.0
    duration: float = 0.0            # 0 means "to the natural end of the source"
    in_point: float = 0.0
    gain: list[GainPoint] = field(default_factory=list)
    loop: bool = False
    fade_in: float = 0.0
    fade_out: float = 0.0
    label: str = ""                  # e.g. the mood this cue was chosen for

    KINDS = ("voice", "music", "sfx")

    def gain_at(self, time: float) -> float:
        """Decibels at `time`, linearly interpolated between the points.

        Outside the defined range the nearest point holds, so a curve does not
        have to cover the whole track to be usable.
        """
        if not self.gain:
            return 0.0
        points = sorted(self.gain, key=lambda p: p.time)
        if time <= points[0].time:
            return points[0].db
        if time >= points[-1].time:
            return points[-1].db
        for earlier, later in zip(points, points[1:]):
            if earlier.time <= time <= later.time:
                span = later.time - earlier.time
                if span <= 0:
                    return later.db
                ratio = (time - earlier.time) / span
                return earlier.db + (later.db - earlier.db) * ratio
        return points[-1].db

    def problems(self, index: int) -> list[str]:
        where = f"audio[{index}]"
        out = []
        if self.kind not in self.KINDS:
            out.append(f"{where}: unknown kind {self.kind!r}")
        if not self.source:
            out.append(f"{where}: missing source path")
        if self.start < 0:
            out.append(f"{where}: start must not be negative")
        if self.duration < 0:
            out.append(f"{where}: duration must not be negative")
        if self.in_point < 0:
            out.append(f"{where}: in_point must not be negative")
        for i, point in enumerate(self.gain):
            if point.time < 0:
                out.append(f"{where}.gain[{i}]: time must not be negative")
            if point.db < -80 or point.db > 12:
                out.append(f"{where}.gain[{i}]: {point.db} dB is outside the sane range")
        return out


# --------------------------------------------------------------------------
# Transitions
# --------------------------------------------------------------------------

@dataclass
class Transition:
    """How one shot gives way to the next, at time `at`."""

    at: float
    kind: str = "cut"                # cut | crossfade | dip_to_black | whip | speed_ramp
    duration: float = 0.0
    sfx: str = ""                    # optional effect fired on the transition

    KINDS = ("cut", "crossfade", "dip_to_black", "whip", "speed_ramp")

    def problems(self, index: int) -> list[str]:
        where = f"transitions[{index}]"
        out = []
        if self.kind not in self.KINDS:
            out.append(f"{where}: unknown kind {self.kind!r}")
        if self.at < 0:
            out.append(f"{where}: at must not be negative")
        if self.kind == "cut" and self.duration:
            out.append(f"{where}: a cut is instantaneous but has duration {self.duration}")
        if self.kind != "cut" and self.duration <= 0:
            out.append(f"{where}: {self.kind!r} needs a positive duration")
        return out


# --------------------------------------------------------------------------
# The timeline
# --------------------------------------------------------------------------

@dataclass
class Timeline:
    run_id: str = ""
    version: int = SCHEMA_VERSION
    width: int = 1920
    height: int = 1080
    fps: int = 30
    duration: float = 0.0
    shots: list[Shot] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    audio: list[AudioTrack] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    meta: dict = field(default_factory=dict)   # style profile used, agent notes

    # ---- derived ----------------------------------------------------------

    @property
    def voice_track(self) -> AudioTrack | None:
        return next((t for t in self.audio if t.kind == "voice"), None)

    def shots_in_scene(self, scene_index: int) -> list[Shot]:
        return [s for s in self.shots if s.scene_index == scene_index]

    def cuts_per_minute(self) -> float:
        """The measured cut rhythm. Style profiles are written in this unit,
        so it is worth being able to read it back off a finished timeline."""
        if self.duration <= 0:
            return 0.0
        return len(self.shots) / (self.duration / 60)

    # ---- validation -------------------------------------------------------

    def problems(self) -> list[str]:
        """Everything wrong with this timeline, as readable sentences.

        Returns a list rather than raising so a caller can report all of it at
        once - fixing one error only to be handed the next is a miserable way
        to debug a generated document.
        """
        out: list[str] = []

        if self.version != SCHEMA_VERSION:
            out.append(
                f"timeline: schema version {self.version} but this build expects "
                f"{SCHEMA_VERSION}"
            )
        if self.width <= 0 or self.height <= 0:
            out.append(f"timeline: bad frame size {self.width}x{self.height}")
        if self.fps <= 0:
            out.append(f"timeline: fps must be positive, got {self.fps}")
        if self.duration <= 0:
            out.append(f"timeline: duration must be positive, got {self.duration}")
        if not self.shots:
            out.append("timeline: no shots, so there is no picture to render")

        for i, shot in enumerate(self.shots):
            out.extend(shot.problems(i))
        for i, overlay in enumerate(self.overlays):
            out.extend(overlay.problems(i))
        for i, caption in enumerate(self.captions):
            out.extend(caption.problems(i))
        for i, track in enumerate(self.audio):
            out.extend(track.problems(i))
        for i, transition in enumerate(self.transitions):
            out.extend(transition.problems(i))

        out.extend(self._coverage_problems())

        voices = [t for t in self.audio if t.kind == "voice"]
        if len(voices) > 1:
            out.append(f"timeline: {len(voices)} voice tracks, expected at most one")

        return out

    def _coverage_problems(self) -> list[str]:
        """Shots must tile the video with no gaps and no overlaps.

        A gap renders as a black flash and an overlap silently drops a shot, and
        both are easy to produce by accident when durations are computed from
        estimated timings. Catching it here is much cheaper than noticing it in
        a finished file.
        """
        if not self.shots:
            return []
        out = []
        ordered = sorted(self.shots, key=lambda s: s.start)

        if ordered[0].start > DURATION_TOLERANCE:
            out.append(
                f"timeline: picture does not start until {ordered[0].start:.2f}s, "
                f"leaving a gap at the head"
            )

        for earlier, later in zip(ordered, ordered[1:]):
            delta = later.start - earlier.end
            if delta > DURATION_TOLERANCE:
                out.append(
                    f"timeline: {delta:.2f}s gap between shots at "
                    f"{earlier.end:.2f}s and {later.start:.2f}s"
                )
            elif delta < -DURATION_TOLERANCE:
                out.append(
                    f"timeline: shots overlap by {-delta:.2f}s at {later.start:.2f}s"
                )

        tail = self.duration - ordered[-1].end
        if tail > DURATION_TOLERANCE:
            out.append(
                f"timeline: picture ends {tail:.2f}s before the declared duration"
            )
        elif tail < -DURATION_TOLERANCE:
            out.append(
                f"timeline: picture runs {-tail:.2f}s past the declared duration"
            )
        return out

    def validate(self) -> None:
        """Raises ValueError listing every problem, or returns quietly."""
        problems = self.problems()
        if problems:
            raise ValueError(
                "This timeline cannot be rendered:\n  - " + "\n  - ".join(problems)
            )

    # ---- serialisation ----------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path) -> None:
        """Writes atomically, so an interrupted save cannot leave a half-written
        timeline where a valid one used to be."""
        import os
        import uuid

        path = str(path)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temp = f"{path}.tmp.{uuid.uuid4().hex[:8]}"
        try:
            with open(temp, "w") as handle:
                json.dump(self.to_dict(), handle, indent=2)
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                except OSError:
                    pass

    @classmethod
    def from_dict(cls, data: dict) -> "Timeline":
        known = {f.name for f in fields(cls)}
        payload: dict[str, Any] = {k: v for k, v in data.items() if k in known}

        payload["shots"] = [_build(Shot, s, motion="motion") for s in data.get("shots", [])]
        payload["overlays"] = [_build(Overlay, o) for o in data.get("overlays", [])]
        payload["captions"] = [
            _build(Caption, c, words="words") for c in data.get("captions", [])
        ]
        payload["audio"] = [
            _build(AudioTrack, a, gain="gain") for a in data.get("audio", [])
        ]
        payload["transitions"] = [_build(Transition, t) for t in data.get("transitions", [])]
        return cls(**payload)

    @classmethod
    def load(cls, path) -> "Timeline":
        with open(path) as handle:
            return cls.from_dict(json.load(handle))


_NESTED = {
    "motion": Motion,
    "words": Word,
    "gain": GainPoint,
}

# JSON has no tuple type, so anything declared as one comes back as a list.
# Coercing on the way in means a loaded timeline compares equal to the one that
# was saved, and the renderer can rely on these being fixed-length tuples
# whether the timeline was built in memory or read off disk.
_TUPLE_FIELDS = {
    Motion: ("start_rect", "end_rect"),
    Shot: ("color",),
    Overlay: ("position",),
}


def _coerce(cls, payload: dict) -> dict:
    for name in _TUPLE_FIELDS.get(cls, ()):
        if isinstance(payload.get(name), list):
            payload[name] = tuple(payload[name])
    return payload


def _fill(cls, data: dict):
    """Builds `cls` from `data`, dropping unknown keys.

    Unknown keys are dropped rather than raising, matching how PipelineState
    loads: a timeline written by a slightly different build should still open,
    since the alternative is an unopenable project directory.
    """
    known = {f.name for f in fields(cls)}
    return cls(**_coerce(cls, {k: v for k, v in data.items() if k in known}))


def _build(cls, data: dict, **nested):
    """Rebuilds one dataclass from a dict, rehydrating its nested members."""
    known = {f.name for f in fields(cls)}
    payload = _coerce(cls, {k: v for k, v in data.items() if k in known})
    for attribute, key in nested.items():
        target = _NESTED[key]
        value = data.get(attribute)
        if value is None:
            continue
        if isinstance(value, list):
            payload[attribute] = [
                _fill(target, item) if isinstance(item, dict) else item for item in value
            ]
        elif isinstance(value, dict):
            payload[attribute] = _fill(target, value)
    return cls(**payload)
