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


# ---------------------------------------------------------------------------
# Per-platform formatting
# ---------------------------------------------------------------------------


def test_each_platform_gets_its_own_size_and_cap():
    """`platforms` was accepted and never used: one 9:16 master was rendered
    whatever was asked for, so a TikTok cut and an Instagram cut were the
    same file and `landscape` produced a vertical crop."""
    from clips.publisher import format_for_platform

    clip = CandidateClip(
        clip_id="c1", start_time=10.0, end_time=100.0, duration=90.0,
        hook_text="h", full_text="f", score=8.0,
    )

    shorts = format_for_platform(clip, "youtube_shorts")
    reels = format_for_platform(clip, "instagram_reels")
    landscape = format_for_platform(clip, "landscape")

    assert shorts["duration"] == 60.0 and shorts["truncated"] is True
    assert reels["duration"] == 90.0 and reels["truncated"] is False
    assert (landscape["width"], landscape["height"]) == (1920, 1080)
    assert (shorts["width"], shorts["height"]) == (1080, 1920)
    assert reels["safe_margin_bottom"] > 0


def test_an_unknown_platform_is_rejected_rather_than_ignored():
    from clips.publisher import format_for_platform

    clip = CandidateClip(clip_id="c", start_time=0.0, end_time=10.0, duration=10.0,
                         hook_text="h", full_text="f", score=1.0)
    with pytest.raises(ValueError, match="Unknown platform"):
        format_for_platform(clip, "myspace")


def test_bundle_records_a_format_per_requested_platform(tmp_path):
    source = ClipSource(source_type="upload", video_path="", title="Bundle", duration=50.0)
    clip = CandidateClip(clip_id="c1", start_time=0.0, end_time=25.0, duration=25.0,
                         hook_text="Hook", full_text="Full", score=8.0)
    project = ClipProject(project_id="proj", source=source, candidates=[clip])

    manifest = package_clips_bundle(
        project,
        output_directory=str(tmp_path / "bundle"),
        platforms=["youtube_shorts", "tiktok"],
    )

    formats = manifest["clips"][0]["formats"]
    assert set(formats) == {"youtube_shorts", "tiktok"}
    assert manifest["platforms"] == ["youtube_shorts", "tiktok"]


def test_a_clip_exactly_at_the_cap_is_still_a_short():
    """The cap was max_duration + 1.0, so a 61-second clip uploaded as a
    Short and YouTube treated it as an ordinary video."""
    from clips.publisher import publish_short_to_youtube

    over = CandidateClip(clip_id="c", start_time=0.0, end_time=60.5, duration=60.5,
                         hook_text="h", full_text="f", score=1.0)
    with pytest.raises(ValueError, match="exceeds YouTube Shorts cap"):
        publish_short_to_youtube(clip=over, rendered_clip_path="x.mp4",
                                 title="t", dry_run=True)


# ---------------------------------------------------------------------------
# Reframing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("src_w,src_h,out_w,out_h", [
    (1920, 1080, 1080, 1920),
    (1080, 1920, 1080, 1920),
    (1920, 1080, 1920, 1080),
    (640, 640, 1080, 1920),
])
def test_the_crop_matches_the_output_shape(src_w, src_h, out_w, out_h):
    """A crop that does not match the output aspect is a stretch."""
    from clips.reframing import calculate_crop_window

    _, _, crop_w, crop_h = calculate_crop_window(
        src_w, src_h, 0.5, target_aspect=out_w / out_h
    )

    assert crop_w / crop_h == pytest.approx(out_w / out_h, rel=0.01)
    assert crop_w <= src_w and crop_h <= src_h
    assert crop_w % 2 == 0 and crop_h % 2 == 0


def test_the_crop_follows_the_subject():
    from clips.reframing import calculate_crop_window

    left, _, width, _ = calculate_crop_window(1920, 1080, 0.2, target_aspect=9 / 16)
    right, _, _, _ = calculate_crop_window(1920, 1080, 0.8, target_aspect=9 / 16)

    assert left < right
    assert left + width <= 1920


def test_subject_detection_falls_back_to_centre_on_a_bad_file():
    from clips.reframing import detect_subject_x

    assert detect_subject_x("/nonexistent.mp4", 0.0, 5.0) == 0.5
