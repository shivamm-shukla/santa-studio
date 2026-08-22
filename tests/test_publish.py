"""Tests for Phase 6 Product: YouTube publishing provider and publish agent."""

import os
import pytest

import agents.publish_agent as publish_agent
from providers.publish.youtube_provider import YouTubeProvider


def test_youtube_provider_dry_run(tmp_path):
    provider = YouTubeProvider(dry_run=True)
    res = provider.upload(
        video_path="runs/fake_video.mp4",
        title="Epic Indian Space History",
        description="Detailed documentary on rocketry.",
        tags=["space", "history"],
        privacy_status="private",
    )
    assert res["dry_run"] is True
    assert res["video_id"] != ""
    assert "https://www.youtube.com/watch?v=" in res["video_url"]
    assert res["thumbnail_uploaded"] is False


def test_publish_agent_dry_run():
    config = {
        "ACTIVE_PROVIDERS": {"publish": "youtube"}
    }
    input_data = {
        "video_path": "runs/test_final.mp4",
        "metadata": {
            "title": "Documentary Test",
            "description": "Full script description",
            "tags": ["documentary", "history"],
        },
        "thumbnail_path": "",
        "privacy_status": "unlisted",
    }

    # Force dry-run for test environment
    os.environ["SANTA_STUDIO_DRY_RUN"] = "1"
    try:
        res = publish_agent.run(input_data, config)
        assert res["success"] is True
        output = res["output"]
        assert output["published"] is True
        assert output["platform"] == "youtube"
        assert output["video_id"] != ""
        assert output["dry_run"] is True
    finally:
        os.environ.pop("SANTA_STUDIO_DRY_RUN", None)
