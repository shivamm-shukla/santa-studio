"""Tests for Phase 2 Visual Craft: timing, cut rhythm, Ken-Burns motion, and overlays."""

import os
import json
import pytest

pytest.importorskip("moviepy")
pytest.importorskip("pydub")

from pydub import AudioSegment
from pydub.generators import Sine
from PIL import Image

import agents.assembler_agent as assembler_agent
import agents.visual_agent as visual_agent
import style_profile as sp
import timeline_builder
from timeline import Motion, Shot, Timeline, Overlay


@pytest.fixture
def sample_voice(tmp_path):
    path = tmp_path / "narration.wav"
    Sine(440).to_audio_segment(duration=6000).export(path, format="wav")
    return str(path)


@pytest.fixture
def sample_image(tmp_path):
    path = tmp_path / "still.jpg"
    img = Image.new("RGB", (1920, 1080), color=(100, 150, 200))
    img.save(path)
    return str(path)


def test_visual_agent_fetches_multi_shots_for_scenes(monkeypatch):
    class FakeProvider:
        def search(self, query):
            return {"asset_type": "image", "asset_path": f"/tmp/{query.replace(' ', '_')}.jpg"}

    monkeypatch.setattr(visual_agent, "get_provider", lambda kind, cfg: FakeProvider())

    scenes = [
        {"visual_hint": "ancient rocket, battlefield explosion", "text": "Short scene"},
        {"visual_hint": "laboratory", "text": "A very long descriptive scene text with more than twenty words to trigger multi-shot query expansion."}
    ]

    res = visual_agent.run({"scenes": scenes}, {"ACTIVE_PROVIDERS": {"visual": "fake"}})
    assert res["success"] is True
    assets = res["output"]["scene_assets"]
    # Scene 0 had 2 comma separated queries -> 2 assets
    scene_0_assets = [a for a in assets if a["scene_index"] == 0]
    # Scene 1 had long text -> 2 assets
    scene_1_assets = [a for a in assets if a["scene_index"] == 1]
    assert len(scene_0_assets) == 2
    assert len(scene_1_assets) == 2


def test_assembler_agent_end_to_end_with_timeline(sample_voice, sample_image, tmp_path):
    out_mp4 = str(tmp_path / "test_run_final.mp4")
    input_data = {
        "run_id": "phase2_test_123",
        "audio_path": sample_voice,
        "script": {
            "script_text": "Scene one text. Scene two text.",
            "scenes": [
                {"timestamp_estimate": "0:00-0:02", "text": "Scene one text", "visual_hint": "scene1"},
                {"timestamp_estimate": "0:02-0:06", "text": "Scene two text", "visual_hint": "scene2"},
            ]
        },
        "scene_assets": [
            {"scene_index": 0, "asset_type": "image", "asset_path": sample_image},
            {"scene_index": 1, "asset_type": "image", "asset_path": sample_image},
        ],
        "output_path": out_mp4,
    }
    config = {
        "ACTIVE_PROVIDERS": {"music": None},
        "STYLE_PROFILE": "documentary",
    }

    res = assembler_agent.run(input_data, config)
    assert res["success"] is True
    assert os.path.exists(res["output"]["video_path"])
    assert os.path.exists(res["output"]["timeline_path"])

    # Verify timeline respected the timestamp estimates (2.0s and 4.0s out of 6.0s total)
    with open(res["output"]["timeline_path"]) as f:
        timeline_data = json.load(f)
    assert len(timeline_data["shots"]) == 2
    assert timeline_data["shots"][0]["duration"] == pytest.approx(2.0, abs=0.1)
    assert timeline_data["shots"][1]["duration"] == pytest.approx(4.0, abs=0.1)
    assert timeline_data["width"] == 1920
    assert timeline_data["height"] == 1080
    assert timeline_data["fps"] == 30


def test_ken_burns_motion_generation():
    profile = sp.load("documentary")
    import random
    rng = random.Random(42)

    from render.motion import build_motion
    motion = build_motion(profile.motion, rng)
    assert motion is not None
    assert not motion.is_static
    assert motion.easing in ("linear", "ease_in", "ease_out", "ease_in_out")
    assert motion.problems("test") == []


def test_overlay_creation_and_validation():
    overlay = Overlay(
        start=1.0,
        duration=3.0,
        kind="text",
        text="Key Insight Callout",
        style={"color": "#FFD24A", "font_size_ratio": 0.05},
        position=(0.5, 0.2),
        anchor="center",
    )
    assert overlay.end == 4.0
    assert overlay.problems(0) == []



def test_a_scene_asking_for_a_document_gets_the_place_instead(monkeypatch):
    """Refusing to invent a notice is right; leaving the scene black is not."""
    import agents.visual_agent as visual_agent
    from providers.visual import art_direction

    asked = []

    class NoStock:
        def search(self, query, **kwargs):
            return {"asset_type": "video", "asset_path": ""}

    class Generator:
        def search(self, query, asset_type="image", variation=0):
            asked.append(query)
            if art_direction.refuses(query):
                return {"asset_type": "image", "asset_path": ""}
            return {"asset_type": "image", "asset_path": f"/tmp/{variation}.jpg"}

    monkeypatch.setattr(
        visual_agent, "get_provider",
        lambda kind, cfg: Generator() if cfg["ACTIVE_PROVIDERS"]["visual"] == "generated" else NoStock(),
    )

    scenes = [{"visual_hint": "official closure notice BGML 2001 Kolar gold fields", "text": "short"}]
    res = visual_agent.run({"scenes": scenes}, {"ACTIVE_PROVIDERS": {"visual": "pexels"}})

    assets = [a for a in res["output"]["scene_assets"] if a["asset_path"]]
    assert assets, "the scene was left with nothing"
    assert not any(art_direction.refuses(q) for q in asked if q == asked[-1])
    assert "notice" not in asked[-1]
