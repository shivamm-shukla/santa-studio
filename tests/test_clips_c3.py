"""Tests for Clips Track Phase C3: Multi-platform packaging and YouTube Shorts publishing."""

import os
import pytest

from clips.models import CandidateClip, ClipProject, ClipSource
from clips.publisher import (
    PLATFORM_PRESETS,
    package_clips_bundle,
    publish_short_to_youtube,
)


def test_platform_presets_definitions():
    assert "youtube_shorts" in PLATFORM_PRESETS
    assert "instagram_reels" in PLATFORM_PRESETS
    assert "tiktok" in PLATFORM_PRESETS

    shorts = PLATFORM_PRESETS["youtube_shorts"]
    assert shorts["width"] == 1080
    assert shorts["height"] == 1920
    assert shorts["max_duration"] == 60.0


def test_publish_short_to_youtube_dry_run():
    clip = CandidateClip(
        clip_id="clip_1",
        start_time=0.0,
        end_time=42.0,
        duration=42.0,
        hook_text="Why the Roman Empire collapsed?",
        full_text="Complete clip text",
        score=9.0,
    )

    res = publish_short_to_youtube(
        clip=clip,
        rendered_clip_path="runs/fake_short.mp4",
        title="Roman Empire Secret",
        description="Detailed clip",
        tags=["history"],
        dry_run=True,
    )

    assert res["dry_run"] is True
    assert res["video_id"] != ""
    assert "https://www.youtube.com/watch?v=" in res["video_url"]


def test_publish_short_duration_cap_exceeded():
    clip = CandidateClip(
        clip_id="clip_long",
        start_time=0.0,
        end_time=95.0,
        duration=95.0,
        hook_text="Too long for a short",
        full_text="Long text",
        score=5.0,
    )

    with pytest.raises(ValueError, match="exceeds YouTube Shorts cap"):
        publish_short_to_youtube(
            clip=clip,
            rendered_clip_path="runs/fake.mp4",
            title="Too long",
            dry_run=True,
        )


def test_package_clips_bundle(tmp_path):
    source = ClipSource(
        source_type="upload",
        video_path="",
        title="Bundle Test",
        duration=50.0,
    )
    candidates = [
        CandidateClip(
            clip_id="c1",
            start_time=0.0,
            end_time=25.0,
            duration=25.0,
            hook_text="Hook 1",
            full_text="Full 1",
            score=8.0,
            suggested_title="Clip 1",
        )
    ]
    project = ClipProject(project_id="proj_bundle", source=source, candidates=candidates)

    manifest = package_clips_bundle(project, output_directory=str(tmp_path / "bundle"))
    assert manifest["project_id"] == "proj_bundle"
    assert len(manifest["clips"]) == 1
    assert manifest["clips"][0]["title"] == "Clip 1"
