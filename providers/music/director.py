"""Music Director: maps script emotional shape and pacing to dynamic audio cues.

Instead of playing a single looped track at a flat volume for 15 minutes,
the Music Director:
1. Slices the score into distinct mood cues based on the style profile's mood_arc
   (e.g., curious opening -> tense investigation -> triumphant climax -> calm wrap-up).
2. Generates dynamic gain automation curves (sidechain ducking under voice, swells during pauses).
3. Adds SFX tracks at structural moments (whoosh on scene transitions, impact on reveals,
   riser before section breaks, pop on graphic callouts).
"""

from __future__ import annotations

import os
from typing import List, Optional

import paths
from providers.music.ambient_music_provider import AmbientMusicProvider
from providers.music.sfx import generate_sfx
from render import audio_mix
from timeline import AudioTrack, GainPoint, Timeline


class MusicDirector:
    def __init__(self, music_provider=None):
        self.music_provider = music_provider or AmbientMusicProvider()

    def build_audio_tracks(
        self,
        voice_path: str,
        total_duration: float,
        profile,
        scenes: Optional[List[dict]] = None,
        transitions: Optional[List] = None,
        overlays: Optional[List] = None,
    ) -> List[AudioTrack]:
        """Creates the complete multi-cue music and SFX arrangement for a Timeline."""
        tracks: List[AudioTrack] = []

        if not voice_path or not os.path.exists(voice_path) or total_duration <= 0:
            return tracks

        # 1. Voice track
        tracks.append(AudioTrack(source=voice_path, kind="voice", duration=total_duration))

        if not profile.music.enabled:
            return tracks

        # 2. Dynamic multi-cue background score
        mood_arc = profile.music.mood_arc or ("curious", "cinematic", "mysterious")
        change_every = profile.music.change_cue_every or 90.0

        # Build narration ducking curve
        try:
            duck_curve = audio_mix.duck_curve(voice_path, None, profile.music)
        except Exception:
            duck_curve = [GainPoint(0.0, profile.music.bed_db)]

        # If change_every <= 0 or duration is short, single cue
        if change_every <= 0 or total_duration <= change_every * 1.2:
            mood = mood_arc[0] if mood_arc else "curious"
            track_res = self.music_provider.search(mood=mood)
            bg_path = track_res.get("track_path", "")
            if bg_path and os.path.exists(bg_path):
                tracks.append(AudioTrack(
                    source=bg_path,
                    kind="music",
                    start=0.0,
                    duration=total_duration,
                    loop=True,
                    gain=duck_curve,
                    fade_in=1.0,
                    fade_out=2.0,
                    label=f"cue_0_{mood}",
                ))
        else:
            # Multi-cue arrangement
            n_cues = max(1, int(round(total_duration / change_every)))
            cue_len = total_duration / n_cues

            for i in range(n_cues):
                mood = mood_arc[i % len(mood_arc)]
                track_res = self.music_provider.search(mood=mood)
                bg_path = track_res.get("track_path", "")
                if not (bg_path and os.path.exists(bg_path)):
                    continue

                start_t = i * cue_len
                end_t = min(total_duration, (i + 1) * cue_len)
                duration_t = end_t - start_t

                # Slice the duck curve for this cue window
                cue_gain = [
                    GainPoint(max(0.0, p.time - start_t), p.db)
                    for p in duck_curve
                    if start_t <= p.time <= end_t
                ]
                if not cue_gain:
                    cue_gain = [GainPoint(0.0, profile.music.bed_db)]

                tracks.append(AudioTrack(
                    source=bg_path,
                    kind="music",
                    start=round(start_t, 2),
                    duration=round(duration_t, 2),
                    loop=True,
                    gain=cue_gain,
                    fade_in=1.5 if i > 0 else 1.0,
                    fade_out=1.5 if i < n_cues - 1 else 2.0,
                    label=f"cue_{i}_{mood}",
                ))

        # 3. SFX at structural moments
        #
        # Not at every cut. A documentary cuts every four seconds and a
        # quarter of those are dissolves, so whooshing each one is a whoosh
        # every fifteen seconds for the length of the video - which stops
        # reading as emphasis within about a minute and starts reading as a
        # tic. A structural moment is a section break: the dip to black the
        # style profile nominates, plus the boundaries of the music cues,
        # which is where the score itself changes.
        if profile.music.sfx_on_transitions:
            for at in self._structural_moments(tracks, transitions, profile, total_duration):
                tracks.append(AudioTrack(
                    source=generate_sfx("whoosh"),
                    kind="sfx",
                    start=round(max(0.0, at - 0.2), 2),
                    duration=0.45,
                    gain=[GainPoint(0.0, profile.music.sfx_db)],
                    label="sfx_whoosh",
                ))

            # Reveal impact at opening hook
            impact_path = generate_sfx("impact")
            tracks.append(AudioTrack(
                source=impact_path,
                kind="sfx",
                start=0.1,
                duration=1.2,
                gain=[GainPoint(0.0, profile.music.sfx_db + 2.0)],
                label="sfx_hook_impact",
            ))

            # Pop on overlays
            if overlays:
                pop_path = generate_sfx("pop")
                for ov in overlays:
                    if ov.start > 0.5:
                        tracks.append(AudioTrack(
                            source=pop_path,
                            kind="sfx",
                            start=round(ov.start, 2),
                            duration=0.15,
                            gain=[GainPoint(0.0, profile.music.sfx_db - 4.0)],
                            label="sfx_pop",
                        ))

        return tracks

    # ----------------------------------------------------------------------

    SECTION_BREAK_KINDS = ("dip_to_black",)
    # Never two structural hits closer together than this.
    MIN_SFX_GAP = 20.0

    def _structural_moments(self, tracks, transitions, profile, total_duration) -> list:
        """Where a section actually begins, in seconds.

        Two signals, both already decided elsewhere: the transition kind the
        style profile reserves for a section break, and the start of each
        music cue. Deduplicated and thinned, so a long video gets a handful
        of accents rather than one per cut.
        """
        moments: list[float] = []

        break_kind = getattr(profile.transitions, "section_break_kind", "dip_to_black")
        wanted = set(self.SECTION_BREAK_KINDS) | {break_kind}
        for transition in transitions or []:
            if transition.kind in wanted and transition.at > 0.5:
                moments.append(float(transition.at))

        for track in tracks:
            if track.kind == "music" and track.start > 0.5:
                moments.append(float(track.start))

        chosen: list[float] = []
        for at in sorted(moments):
            if at >= total_duration - 0.5:
                continue
            if chosen and at - chosen[-1] < self.MIN_SFX_GAP:
                continue
            chosen.append(at)
        return chosen
