"""Tests for Clips Track Phase C2: Two-pointer trimming, impact effects, and vertical captions."""

import pytest

from clips.editor import (
    COLOR_GRADES,
    adjust_clip_range,
    build_impact_overlays,
    build_vertical_captions,
)
from clips.models import CandidateClip, ClipProject, ClipSource, SentenceSpan, TranscriptWord


@pytest.fixture
def sample_clip_project():
    words = [
        TranscriptWord("Why", 0.0, 0.5),
        TranscriptWord("is", 0.5, 0.8),
        TranscriptWord("this", 0.8, 1.2),
        TranscriptWord("happening?", 1.2, 1.8),
        TranscriptWord("Because", 2.0, 2.4),
        TranscriptWord("of", 2.4, 2.6),
        TranscriptWord("gravity.", 2.6, 3.2),
        TranscriptWord("And", 4.0, 4.4),
        TranscriptWord("now", 4.4, 4.7),
        TranscriptWord("we", 4.7, 5.0),
        TranscriptWord("know.", 5.0, 5.6),
    ]
    sentences = [
        SentenceSpan("Why is this happening?", 0.0, 1.8),
        SentenceSpan("Because of gravity.", 2.0, 3.2),
        SentenceSpan("And now we know.", 4.0, 5.6),
    ]
    source = ClipSource(
        source_type="upload",
        video_path="",
        title="Test",
        duration=6.0,
        transcript=words,
        sentences=sentences,
    )
    candidates = [
        CandidateClip(
            clip_id="clip_1",
            start_time=0.0,
            end_time=3.2,
            duration=3.2,
            hook_text="Why is this happening?",
            full_text="Why is this happening? Because of gravity.",
            score=8.5,
        )
    ]
    return ClipProject(project_id="test_proj", source=source, candidates=candidates)


def test_two_pointer_range_adjustment_with_snapping(sample_clip_project):
    # Adjust range to 1.5 - 5.2 -> snaps to sentences 0 and 2 (0.0 to 5.6)
    adjusted = adjust_clip_range(
        sample_clip_project,
        clip_id="clip_1",
        new_start=1.5,
        new_end=5.2,
        snap_to_sentences=True,
    )
    assert adjusted.start_time == 0.0
    assert adjusted.end_time == 5.6
    assert "gravity" in adjusted.full_text
    assert "know." in adjusted.full_text


def test_build_vertical_captions():
    raw_words = [
        {"word": "Never", "start": 0.0, "end": 0.4},
        {"word": "make", "start": 0.4, "end": 0.7},
        {"word": "this", "start": 0.7, "end": 1.0},
        {"word": "mistake", "start": 1.0, "end": 1.5},
        {"word": "again", "start": 1.5, "end": 2.0},
    ]

    captions = build_vertical_captions(raw_words, start_time=0.0, end_time=2.0, words_per_card=3)
    assert len(captions) == 2
    assert captions[0].text == "NEVER MAKE THIS"
    assert captions[1].text == "MISTAKE AGAIN"


def test_build_impact_overlays():
    events = [
        {"kind": "flash", "at": 0.5, "duration": 0.1},
        {"kind": "punch_in", "at": 1.8, "duration": 0.25},
    ]
    overlays = build_impact_overlays(events)
    assert len(overlays) == 2
    assert overlays[0].kind == "color"
    assert overlays[1].kind == "zoom"


def test_color_grades_presets():
    for name, grade in COLOR_GRADES.items():
        assert "contrast" in grade
        assert "saturation" in grade
        assert "brightness" in grade
