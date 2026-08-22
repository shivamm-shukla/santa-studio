"""Tests for Clips Track Phase C1: Ingest, Candidate Window Ranking, and Vertical Reframing."""

import os
import json
import pytest

pytest.importorskip("moviepy")
from PIL import Image
from moviepy import ImageClip

from clips.analyzer import rank_candidate_clips
from clips.engine import create_clip_project
from clips.models import ClipSource, TranscriptWord
from clips.reframing import calculate_crop_window, render_vertical_clip
from clips.transcript import snap_to_sentence_boundaries, words_to_sentences


@pytest.fixture
def mock_video(tmp_path):
    img_path = tmp_path / "frame.jpg"
    img = Image.new("RGB", (1920, 1080), color=(50, 100, 150))
    img.save(img_path)

    out_mp4 = str(tmp_path / "mock_source.mp4")
    clip = ImageClip(str(img_path)).with_duration(75.0)
    clip.write_videofile(out_mp4, fps=24, codec="libx264", logger=None)
    return out_mp4


def test_words_to_sentences_grouping():
    words = [
        TranscriptWord("Why", 0.0, 0.5),
        TranscriptWord("did", 0.5, 0.8),
        TranscriptWord("this", 0.8, 1.1),
        TranscriptWord("fail?", 1.1, 1.6),
        TranscriptWord("Because", 2.2, 2.7),
        TranscriptWord("the", 2.7, 2.9),
        TranscriptWord("engine", 2.9, 3.4),
        TranscriptWord("exploded.", 3.4, 4.0),
    ]

    sentences = words_to_sentences(words)
    assert len(sentences) == 2
    assert sentences[0].text == "Why did this fail?"
    assert sentences[0].start == 0.0
    assert sentences[0].end == 1.6
    assert sentences[1].text == "Because the engine exploded."
    assert sentences[1].start == 2.2
    assert sentences[1].end == 4.0


def test_snap_to_sentence_boundaries():
    words = [
        TranscriptWord("Sentence", 0.0, 1.0),
        TranscriptWord("one.", 1.0, 2.0),
        TranscriptWord("Sentence", 3.0, 4.0),
        TranscriptWord("two.", 4.0, 5.0),
        TranscriptWord("Sentence", 6.0, 7.0),
        TranscriptWord("three.", 7.0, 8.0),
    ]
    sentences = words_to_sentences(words)

    start, end, matched = snap_to_sentence_boundaries(1.5, 4.5, sentences, min_duration=2.0)
    assert start == 0.0
    assert end >= 5.0
    assert len(matched) >= 2


def test_candidate_ranking_and_deduplication():
    # Build a simulated 90s transcript with multiple sentences
    words = []
    t = 0.0
    for i in range(30):
        w1 = TranscriptWord(f"Word{i}", round(t, 2), round(t + 0.4, 2))
        w2 = TranscriptWord("and", round(t + 0.4, 2), round(t + 0.7, 2))
        w3 = TranscriptWord("point.", round(t + 0.7, 2), round(t + 1.2, 2)) if (i % 3 == 2) else TranscriptWord("next", round(t + 0.7, 2), round(t + 1.2, 2))
        words.extend([w1, w2, w3])
        t += 1.5

    # Insert a high-curiosity question hook in the middle
    words.insert(10, TranscriptWord("Why", 5.0, 5.4))
    words.insert(11, TranscriptWord("is", 5.4, 5.7))
    words.insert(12, TranscriptWord("this", 5.7, 6.0))
    words.insert(13, TranscriptWord("insane", 6.0, 6.5))
    words.insert(14, TranscriptWord("secret", 6.5, 7.0))
    words.insert(15, TranscriptWord("hidden?", 7.0, 7.6))

    sentences = words_to_sentences(words)
    source = ClipSource(
        source_type="upload",
        video_path="",
        title="Test Longform",
        duration=90.0,
        transcript=words,
        sentences=sentences,
    )

    ranked = rank_candidate_clips(source, target_count=3, min_duration=10.0, max_duration=40.0)
    assert len(ranked) >= 1
    assert ranked[0].score > 0
    # Top ranked clip should mention the question hook or trigger words
    assert any("hook" in r.lower() or "trigger" in r.lower() for r in ranked[0].reasons)


def test_calculate_crop_window():
    # 1920x1080 source, 9:16 target (width = 608)
    x1, y1, crop_w, crop_h = calculate_crop_window(1920, 1080, crop_x_center_ratio=0.5)
    assert crop_h == 1080
    assert crop_w == 608
    assert y1 == 0
    assert x1 == (1920 - 608) // 2  # 656

    # Offset to left
    x1_left, _, _, _ = calculate_crop_window(1920, 1080, crop_x_center_ratio=0.1)
    assert x1_left == 0

    # Offset to right
    x1_right, _, _, _ = calculate_crop_window(1920, 1080, crop_x_center_ratio=0.9)
    assert x1_right == 1920 - 608


def test_render_vertical_clip_end_to_end(mock_video, tmp_path):
    out_clip = str(tmp_path / "vertical_preview.mp4")
    res = render_vertical_clip(
        source_video_path=mock_video,
        start_time=5.0,
        end_time=15.0,
        output_path=out_clip,
        crop_x_center_ratio=0.5,
        width=720,
        height=1280,
    )
    assert os.path.exists(res)
    assert os.path.getsize(res) > 0


def test_create_clip_project_end_to_end(mock_video, monkeypatch):
    class FakeWhisperModel:
        def transcribe(self, path, word_timestamps=True):
            return {
                "segments": [{
                    "words": [
                        {"word": "Why", "start": 0.0, "end": 0.5},
                        {"word": "is", "start": 0.5, "end": 0.8},
                        {"word": "this", "start": 0.8, "end": 1.2},
                        {"word": "shocking?", "start": 1.2, "end": 1.8},
                        {"word": "Let", "start": 2.0, "end": 2.4},
                        {"word": "us", "start": 2.4, "end": 2.7},
                        {"word": "investigate", "start": 2.7, "end": 3.4},
                        {"word": "the", "start": 3.4, "end": 3.8},
                        {"word": "truth.", "start": 3.8, "end": 25.0},
                    ]
                }]
            }

    import whisper
    monkeypatch.setattr(whisper, "load_model", lambda name: FakeWhisperModel())

    project = create_clip_project(
        source_type="upload",
        source_target=mock_video,
        target_count=2,
        render_previews=False,
    )

    # A bare hex handle rather than a prefixed one: the project directory is
    # found by its trailing 8 characters, so every id sharing a "clip_proj_"
    # prefix would resolve to the same folder.
    assert len(project.project_id) == 12
    assert all(c in "0123456789abcdef" for c in project.project_id)
    assert len(project.candidates) >= 1
    # Stored like any other project, so ls / rm / gc / export reach it.
    import paths

    project_dir = paths.find_project(project.project_id)
    assert project_dir is not None
    assert (project_dir / "project.json").exists()
    assert project_dir.is_relative_to(paths.projects_dir())
