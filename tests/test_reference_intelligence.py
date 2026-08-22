"""Tests for Phase 4 Reference Intelligence: ingestion, pacing analysis, and StyleProfile synthesis."""

import os
import pytest

import agents.reference_agent as reference_agent
from providers.reference.analyzer import analyze_and_synthesize
from providers.reference.ingest import ingest_reference
import style_profile as sp


def test_ingest_reference_url_parsing():
    url = "https://www.youtube.com/@Veritasium"
    data = ingest_reference(url)
    assert data["channel"] == "Veritasium"
    assert data["channel_slug"] == "veritasium"
    assert data["duration"] > 0


def test_analyze_and_synthesize_creates_valid_profile(tmp_path, monkeypatch):
    import paths
    monkeypatch.setattr(paths, "styles_dir", lambda: tmp_path)

    ingest_data = {
        "channel": "Kurzgesagt",
        "channel_slug": "kurzgesagt",
        "url": "https://youtube.com/@kurzgesagt",
        "duration": 600.0,
        "word_count": 1800,  # 180 WPM -> fast explainer pacing
    }

    profile = analyze_and_synthesize(ingest_data, save_to_library=True)
    assert profile.name == "kurzgesagt"
    assert profile.cut.target_seconds <= 3.0  # Fast pacing
    assert profile.motion.intensity >= 0.6
    assert (tmp_path / "kurzgesagt.json").exists()


def test_reference_agent_end_to_end(monkeypatch, tmp_path):
    import paths
    monkeypatch.setattr(paths, "styles_dir", lambda: tmp_path)

    class FakeLLMProvider:
        def complete(self, prompt, system=None):
            return {
                "text": '{"style_notes": "Energetic, fact-dense narration", "structure_notes": "Hook -> 3 Acts -> Payoff", "angle_notes": "First-principles scientific analysis"}',
                "raw": {}
            }

    import providers.registry as registry
    monkeypatch.setattr(reference_agent, "get_provider", lambda kind, cfg: FakeLLMProvider())

    res = reference_agent.run(
        {"urls": ["https://www.youtube.com/@clever_channel"]},
        {"ACTIVE_PROVIDERS": {"llm": "fake"}},
    )

    assert res["success"] is True
    output = res["output"]
    assert "style_notes" in output
    assert "structure_notes" in output
    assert "angle_notes" in output
    assert output["style_profile"] == "clever-channel"
    assert "suggested_mood" in output
