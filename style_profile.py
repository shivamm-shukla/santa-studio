"""Style Profile: the knobs that decide how a video is cut.

A script says what is said. A style profile says how it is shown - how often
the picture cuts, how much the stills move, how dense the on-screen graphics
are, how the music behaves under the narration. Those choices are what separate
two videos on the same subject, and they were previously scattered as constants
across the agents that happened to need them.

Every field is a number or a small enum rather than prose, for one specific
reason: these values are eventually going to be *measured* off real reference
videos rather than written by hand. "Cuts roughly every four seconds" is
something you can count from frame differences; "energetic and modern" is not.
So the profile is deliberately shaped to be the output of an analysis pass, and
the hand-written presets below are stand-ins for that until it exists.

Profiles are stored in the library, not per project, because the point is to
analyse a channel once and reuse what you learned across everything you make.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, fields


@dataclass
class CutRhythm:
    """How often the picture changes.

    A scene from the script becomes several shots rather than one held clip -
    holding a single stock clip for the length of a paragraph is the single
    most recognisable trait of an automatically assembled video.
    """

    target_seconds: float = 4.0      # average time on one shot
    min_seconds: float = 2.0
    max_seconds: float = 7.0
    variance: float = 0.35           # 0 = metronomic, 1 = wildly uneven

    def shot_lengths(self, total: float, rng: random.Random) -> list[float]:
        """Divides `total` seconds into shot durations following this rhythm.

        Jitter is applied per shot and the result is rescaled to land exactly
        on `total`, because a scene's shots have to fill their scene precisely -
        a rounding drift becomes a black gap or a dropped shot at render time.
        """
        if total <= self.min_seconds:
            return [total]

        lengths: list[float] = []
        remaining = total
        while remaining > 0:
            jitter = 1.0 + rng.uniform(-self.variance, self.variance)
            length = max(self.min_seconds, min(self.max_seconds, self.target_seconds * jitter))
            if remaining - length < self.min_seconds:
                # Rather than leave a stub too short to read, absorb the rest.
                lengths.append(remaining)
                break
            lengths.append(length)
            remaining -= length

        scale = total / sum(lengths)
        return [length * scale for length in lengths]

    @property
    def cuts_per_minute(self) -> float:
        return 60.0 / self.target_seconds if self.target_seconds else 0.0


@dataclass
class MotionStyle:
    """Ken Burns movement on stills, and drift on footage.

    `intensity` scales how far a move travels: 0 leaves everything static,
    1 pushes in hard. Stills need this far more than video does, so they have
    separate probabilities - a still that never moves reads as a dead slide.
    """

    still_probability: float = 1.0   # fraction of image shots that move
    video_probability: float = 0.0   # footage usually carries its own motion
    intensity: float = 0.5
    max_zoom: float = 0.25           # 0.25 = push in to 75% of the frame
    max_pan: float = 0.15            # fraction of the frame travelled
    easing: str = "ease_in_out"


@dataclass
class CaptionStyle:
    """Burnt-in subtitles."""

    enabled: bool = True
    words_per_line: int = 4
    font_size_ratio: float = 0.045   # of frame height, so it scales with output
    position: float = 0.82           # vertical, 0 = top, 1 = bottom
    color: str = "#FFFFFF"
    highlight_color: str = "#FFD24A"
    stroke_width: int = 3
    highlight_spoken_word: bool = True
    emphasize_keywords: bool = True
    uppercase: bool = False


@dataclass
class GraphicsStyle:
    """The overlay layer - callouts, counters, timelines, highlight boxes.

    `density` is overlays per minute. This is the layer the pipeline had none
    of, and on explainer channels it is roughly half of what is on screen, so a
    documentary profile sets it high and a plain narrative profile sets it to
    zero.
    """

    density: float = 6.0
    kinds: tuple[str, ...] = ("text", "lower_third", "counter", "highlight")
    animate_in: str = "slide_up"
    animate_out: str = "fade"
    accent_color: str = "#E8853C"
    show_source_citations: bool = True


@dataclass
class MusicStyle:
    """How the score sits under the narration.

    `bed_db` is the resting level and `duck_db` the level under speech; the
    gap between them is what makes a bed feel like scoring rather than
    wallpaper. `swell_db` lifts the bed at a section boundary or a reveal.
    Concrete decibel values because that is what a Timeline gain curve wants.
    """

    enabled: bool = True
    bed_db: float = -16.0
    duck_db: float = -26.0
    swell_db: float = -10.0
    duck_attack: float = 0.25        # seconds to duck once speech starts
    duck_release: float = 0.6        # seconds to recover once it stops
    mood_arc: tuple[str, ...] = ("curious", "cinematic", "mysterious", "cinematic")
    change_cue_every: float = 90.0   # seconds; 0 keeps one cue throughout
    sfx_on_transitions: bool = True
    sfx_db: float = -18.0


@dataclass
class TransitionStyle:
    """Vocabulary of cuts, and how often each is reached for."""

    weights: dict = field(default_factory=lambda: {
        "cut": 0.75,
        "crossfade": 0.15,
        "dip_to_black": 0.05,
        "whip": 0.05,
    })
    crossfade_seconds: float = 0.4
    whip_seconds: float = 0.25
    section_break_kind: str = "dip_to_black"

    def pick(self, rng: random.Random) -> str:
        kinds = list(self.weights)
        return rng.choices(kinds, weights=[self.weights[k] for k in kinds], k=1)[0]

    def duration_for(self, kind: str) -> float:
        if kind == "cut":
            return 0.0
        if kind == "whip":
            return self.whip_seconds
        return self.crossfade_seconds


@dataclass
class NarrationStyle:
    """Pace and shape of the script itself."""

    words_per_minute: int = 150
    hook_seconds: float = 15.0
    hook_pattern: str = "question"   # question | claim | cold_open | statistic
    recap: bool = True
    call_to_action: bool = True


@dataclass
class StyleProfile:
    name: str = "default"
    description: str = ""
    source: str = "builtin"          # builtin | analyzed:<channel> | user
    width: int = 1920
    height: int = 1080
    fps: int = 30

    cut: CutRhythm = field(default_factory=CutRhythm)
    motion: MotionStyle = field(default_factory=MotionStyle)
    captions: CaptionStyle = field(default_factory=CaptionStyle)
    graphics: GraphicsStyle = field(default_factory=GraphicsStyle)
    music: MusicStyle = field(default_factory=MusicStyle)
    transitions: TransitionStyle = field(default_factory=TransitionStyle)
    narration: NarrationStyle = field(default_factory=NarrationStyle)

    # ---- serialisation ----------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path=None) -> str:
        """Writes to the library, or to an explicit path. Returns the path."""
        if path is None:
            import paths as _paths

            path = _paths.styles_dir() / f"{self.name}.json"
        path = str(path)
        with open(path, "w") as handle:
            json.dump(self.to_dict(), handle, indent=2)
        return path

    @classmethod
    def from_dict(cls, data: dict) -> "StyleProfile":
        nested = {
            "cut": CutRhythm,
            "motion": MotionStyle,
            "captions": CaptionStyle,
            "graphics": GraphicsStyle,
            "music": MusicStyle,
            "transitions": TransitionStyle,
            "narration": NarrationStyle,
        }
        known = {f.name for f in fields(cls)}
        payload = {k: v for k, v in data.items() if k in known and k not in nested}
        for key, target in nested.items():
            value = data.get(key)
            if isinstance(value, dict):
                allowed = {f.name for f in fields(target)}
                clean = {k: v for k, v in value.items() if k in allowed}
                # Tuple-typed fields come back from JSON as lists.
                for name in ("kinds", "mood_arc"):
                    if isinstance(clean.get(name), list):
                        clean[name] = tuple(clean[name])
                payload[key] = target(**clean)
        return cls(**payload)

    @classmethod
    def load(cls, name_or_path) -> "StyleProfile":
        """Accepts a preset name, a library profile name, or a path."""
        import os

        text = str(name_or_path)
        if text in PRESETS:
            return PRESETS[text]()
        if os.path.exists(text):
            with open(text) as handle:
                return cls.from_dict(json.load(handle))

        import paths as _paths

        candidate = _paths.styles_dir() / f"{text}.json"
        if candidate.exists():
            with open(candidate) as handle:
                return cls.from_dict(json.load(handle))
        raise ValueError(
            f"No style profile named {text!r}. Built-in presets: "
            f"{', '.join(sorted(PRESETS))}. Analysed profiles live in "
            f"{_paths.styles_dir()}."
        )


# --------------------------------------------------------------------------
# Presets
#
# Stand-ins until Phase 4 can measure these off real reference videos. The
# numbers are chosen to be distinguishable from each other rather than
# precisely correct - the point is that swapping the profile visibly changes
# the output.
# --------------------------------------------------------------------------

def _documentary() -> StyleProfile:
    """Measured narration, heavy graphics, constant slow motion on stills.

    Modelled on the long-form Hindi explainer format: the picture is almost
    always moving, on-screen text and timelines carry a large share of the
    information, and the score is a real presence rather than a bed.
    """
    profile = StyleProfile(
        name="documentary",
        description="Long-form explainer: measured pace, dense graphics, constant subtle motion.",
    )
    profile.cut = CutRhythm(target_seconds=4.0, min_seconds=2.5, max_seconds=8.0, variance=0.3)
    profile.motion = MotionStyle(
        still_probability=1.0, video_probability=0.2, intensity=0.55,
        max_zoom=0.22, max_pan=0.14,
    )
    profile.graphics = GraphicsStyle(density=8.0, animate_in="slide_up")
    profile.music = MusicStyle(
        bed_db=-15.0, duck_db=-26.0, swell_db=-9.0,
        mood_arc=("curious", "cinematic", "mysterious", "cinematic", "calm"),
        change_cue_every=90.0,
    )
    profile.narration = NarrationStyle(words_per_minute=145, hook_seconds=18, hook_pattern="question")
    return profile


def _fast_explainer() -> StyleProfile:
    """Short, punchy, quick cuts and loud graphics."""
    profile = StyleProfile(
        name="fast-explainer",
        description="Short-form: rapid cuts, aggressive motion, punchy captions.",
    )
    profile.cut = CutRhythm(target_seconds=2.2, min_seconds=1.2, max_seconds=4.0, variance=0.45)
    profile.motion = MotionStyle(
        still_probability=1.0, video_probability=0.35, intensity=0.8,
        max_zoom=0.35, max_pan=0.2,
    )
    profile.captions = CaptionStyle(words_per_line=3, font_size_ratio=0.058, uppercase=True)
    profile.graphics = GraphicsStyle(density=12.0, animate_in="pop", animate_out="pop")
    profile.music = MusicStyle(
        bed_db=-13.0, duck_db=-22.0, swell_db=-8.0,
        mood_arc=("energetic", "energetic", "cinematic"),
        change_cue_every=45.0,
    )
    profile.transitions = TransitionStyle(
        weights={"cut": 0.6, "whip": 0.25, "crossfade": 0.1, "dip_to_black": 0.05}
    )
    profile.narration = NarrationStyle(words_per_minute=175, hook_seconds=8, hook_pattern="claim")
    return profile


def _calm_narrative() -> StyleProfile:
    """Slow, sparse, close to a documentary voiceover with no furniture."""
    profile = StyleProfile(
        name="calm-narrative",
        description="Unhurried storytelling: long shots, minimal graphics, gentle score.",
    )
    profile.cut = CutRhythm(target_seconds=7.0, min_seconds=4.0, max_seconds=12.0, variance=0.25)
    profile.motion = MotionStyle(
        still_probability=0.85, video_probability=0.0, intensity=0.3,
        max_zoom=0.12, max_pan=0.08,
    )
    profile.captions = CaptionStyle(words_per_line=6, highlight_spoken_word=False)
    profile.graphics = GraphicsStyle(density=2.0, animate_in="fade", animate_out="fade")
    profile.music = MusicStyle(
        bed_db=-18.0, duck_db=-28.0, swell_db=-14.0,
        mood_arc=("calm", "curious", "calm"),
        change_cue_every=120.0, sfx_on_transitions=False,
    )
    profile.transitions = TransitionStyle(
        weights={"cut": 0.5, "crossfade": 0.4, "dip_to_black": 0.1}, crossfade_seconds=0.8
    )
    profile.narration = NarrationStyle(words_per_minute=130, hook_seconds=20, hook_pattern="cold_open")
    return profile


PRESETS = {
    "documentary": _documentary,
    "fast-explainer": _fast_explainer,
    "calm-narrative": _calm_narrative,
}

DEFAULT_PRESET = "documentary"


def load(name: str | None = None) -> StyleProfile:
    """The one entry point callers should use."""
    return StyleProfile.load(name or DEFAULT_PRESET)


def list_available() -> dict[str, str]:
    """Preset and library profile names mapped to their descriptions."""
    available = {name: factory().description for name, factory in PRESETS.items()}
    try:
        import paths as _paths

        for path in sorted(_paths.styles_dir().glob("*.json")):
            try:
                with open(path) as handle:
                    data = json.load(handle)
                available[path.stem] = data.get("description", "") or f"analysed profile ({path.stem})"
            except (OSError, json.JSONDecodeError):
                continue
    except Exception:
        pass  # listing built-ins is still useful if the library is unreadable
    return available
