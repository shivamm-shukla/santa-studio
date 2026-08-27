"""What a reference channel actually changes about the video.

It changed nothing. The chain was broken in four places at once, and each
break hid the next: yt-dlp was never a declared dependency, so ingestion fell
to a heuristic that invented a ten-minute video of fifteen hundred words; that
divided out to exactly the 150 wpm the analyser defaults to, so every channel
produced an identical profile; the profile was saved to the library and read
back from a config key nothing ever set; and the style, structure and angle
notes were passed to the research agent, which has never read them, and to the
writer, which was never given them.

So a run with a reference URL and a run without produced the same video. These
pin each link.
"""

import pytest

import manager
import style_profile as sp
from providers.reference.analyzer import analyze_and_synthesize
from providers.reference.ingest import _slugify, ingest_reference
from state import PipelineState


REFERENCE = {
    "style_notes": "Steady, conversational, moderate pace.",
    "structure_notes": "A five-second hook, then three sections, then a recap.",
    "angle_notes": "First person, an informed guide rather than a provocateur.",
    "style_profile": "a-reference-channel",
    "suggested_mood": "calm",
}


def _state():
    state = PipelineState(niche="history", user_topic="containers")
    state.topic = "how a metal box rewired world trade"
    state.reference_analysis = dict(REFERENCE)
    state.research = {"research_summary": "s", "sources": []}
    state.factcheck = {"verified_claims": ["A claim."], "flagged_claims": []}
    state.script = {"script_text": "x", "scenes": []}
    state.voice_output = {"audio_path": "/tmp/x.wav"}
    state.video_output = {"video_path": "/tmp/master.mp4"}
    state.visual_output = {"scene_assets": []}
    return state


# ---------------------------------------------------------------------------
# Measuring the reference
# ---------------------------------------------------------------------------


def test_a_channel_named_in_devanagari_still_has_a_name():
    """It slugged to the empty string, so every profile learned from an Indian
    channel was saved as "reference" and overwrote the last one."""
    assert _slugify("शिवम् शुक्ल") not in ("", "reference")
    assert _slugify("Dhruv Rathee") == "dhruv-rathee"
    assert _slugify("") == "reference"


def test_nothing_measured_is_reported_as_nothing(monkeypatch):
    """The fallback claimed a ten-minute video of fifteen hundred words. That
    is a made-up measurement wearing a real one's clothes."""
    monkeypatch.setattr(
        "providers.reference.ingest.requests.get",
        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    ingested = ingest_reference("https://www.youtube.com/@nobody-home-xyz-404")

    if ingested.get("method") == "heuristic":
        assert ingested["duration"] == 0.0
        assert ingested["word_count"] == 0


def test_a_faster_channel_and_a_slower_one_do_not_produce_one_profile():
    """The whole point of measuring is that the answer differs."""
    fast = analyze_and_synthesize(
        {"channel_slug": "fast", "duration": 600.0, "word_count": 2000},
        save_to_library=False,
    )
    slow = analyze_and_synthesize(
        {"channel_slug": "slow", "duration": 600.0, "word_count": 1000},
        save_to_library=False,
    )

    assert fast.narration.words_per_minute > slow.narration.words_per_minute
    assert fast.cut.target_seconds < slow.cut.target_seconds
    assert fast.music.mood_arc != slow.music.mood_arc


# ---------------------------------------------------------------------------
# Getting it to the stages that can act on it
# ---------------------------------------------------------------------------


def test_the_writer_is_told_the_shape_to_write_in():
    given = manager._build_input(_state(), "SCRIPTING")

    assert given["structure_notes"] == REFERENCE["structure_notes"]
    assert given["style_notes"] == REFERENCE["style_notes"]
    assert given["angle_notes"] == REFERENCE["angle_notes"]


def test_the_editor_cuts_to_the_profile_that_was_learned():
    """It read a config key nothing sets, so a run that had just measured a
    channel's pacing rendered at the built-in default's instead."""
    given = manager._build_input(_state(), "VIDEO_ASSEMBLY")

    assert given["style_profile"] == "a-reference-channel"
    assert given["mood"] == "calm"


def test_a_run_with_no_reference_asks_for_no_particular_profile():
    state = _state()
    state.reference_analysis = None

    assert manager._build_input(state, "VIDEO_ASSEMBLY")["style_profile"] == ""


def test_research_is_not_handed_notes_it_has_never_read():
    """They describe how a channel is cut and paced. Passing something nothing
    reads only makes it look like it is being used."""
    assert "reference_notes" not in manager._build_input(_state(), "RESEARCHING")


def test_the_short_is_written_where_the_master_is():
    assert manager._build_input(_state(), "SHORTS_EXTRACTION")["topic"]


# ---------------------------------------------------------------------------
# When the library has been tidied
# ---------------------------------------------------------------------------


def test_a_missing_profile_renders_at_the_default_rather_than_halting(monkeypatch, tmp_path):
    """The library is a directory a person can delete from, and by this point
    the run already has its narration and its footage."""
    import agents.assembler_agent as assembler

    voice = tmp_path / "narration.wav"
    voice.write_bytes(b"RIFF0000WAVE")

    loaded = []
    real_load = sp.load

    def picky(name=None):
        loaded.append(name)
        if name == "a-reference-channel":
            raise FileNotFoundError(name)
        return real_load(name)

    def stop_here(*args, **kwargs):
        raise RuntimeError("far enough - the profile was already chosen")

    monkeypatch.setattr(assembler.sp, "load", picky)
    monkeypatch.setattr(assembler.timeline_builder, "build", stop_here)

    result = assembler.run(
        {
            "style_profile": "a-reference-channel",
            "run_id": "r",
            "audio_path": str(voice),
            "scene_assets": [],
            "scenes": [],
            "script_text": "x",
        },
        {"ACTIVE_PROVIDERS": {}},
    )

    assert loaded == ["a-reference-channel", "documentary"]
    # It stopped at the stub, not on the profile that was missing.
    assert "far enough" in str(result.get("error") or "")
