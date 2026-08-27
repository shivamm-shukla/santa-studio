"""Tests for Phase 4 Reference Intelligence: ingestion, pacing analysis, and StyleProfile synthesis."""

import os
import pytest

import agents.reference_agent as reference_agent
from providers.reference.analyzer import analyze_and_synthesize
from providers.reference.ingest import ingest_reference
import style_profile as sp


def test_ingest_reference_url_parsing(monkeypatch):
    """What is left when the video cannot be opened: the name in the URL.

    This asked YouTube for a real channel over the network, which made it slow
    and made it depend on a stranger's uptime. It also asserted a duration -
    which passed only because the fallback used to invent one, a ten-minute
    video of fifteen hundred words that nobody had measured. Reporting zero is
    the honest answer, and it is what tells the analyser to use its default
    openly rather than dividing a made-up figure by another one.
    """
    import yt_dlp

    def unavailable(*args, **kwargs):
        raise RuntimeError("no network in a unit test")

    monkeypatch.setattr(yt_dlp, "YoutubeDL", unavailable)

    data = ingest_reference("https://www.youtube.com/@Veritasium")

    assert data["method"] == "heuristic"
    assert data["channel"] == "Veritasium"
    assert data["channel_slug"] == "veritasium"
    assert data["duration"] == 0.0
    assert data["word_count"] == 0


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


# ---------------------------------------------------------------------------
# Reference transcripts are fetched, not merely located
# ---------------------------------------------------------------------------

class _Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def _tracks(ext, url="https://example.test/sub"):
    return [{"ext": ext, "url": url}]


def test_json3_captions_are_read(monkeypatch):
    from providers.reference import ingest

    monkeypatch.setattr(ingest.requests, "get", lambda url, timeout=None: _Response(
        '{"events":[{"segs":[{"utf8":"kolar "},{"utf8":"gold "},{"utf8":"fields"}]}]}'
    ))

    text = ingest._fetch_transcript({"subtitles": {"en": _tracks("json3")}})
    assert text == "kolar gold fields"


def test_vtt_captions_lose_their_timestamps_and_their_repeats(monkeypatch):
    from providers.reference import ingest

    vtt = (
        "WEBVTT\n\n"
        "00:00:01.000 --> 00:00:02.000\n<c>kolar</c>\n\n"
        "00:00:02.000 --> 00:00:03.000\nkolar\ngold fields\n"
    )
    monkeypatch.setattr(ingest.requests, "get", lambda url, timeout=None: _Response(vtt))

    assert ingest._fetch_transcript({"subtitles": {"en": _tracks("vtt")}}) == "kolar gold fields"


def test_manual_subtitles_are_preferred_over_generated_ones(monkeypatch):
    from providers.reference import ingest

    served = {
        "https://example.test/manual": '{"events":[{"segs":[{"utf8":"written by a human"}]}]}',
        "https://example.test/auto": '{"events":[{"segs":[{"utf8":"heard by a machine"}]}]}',
    }
    monkeypatch.setattr(ingest.requests, "get",
                        lambda url, timeout=None: _Response(served[url]))

    text = ingest._fetch_transcript({
        "subtitles": {"en": _tracks("json3", "https://example.test/manual")},
        "automatic_captions": {"en": _tracks("json3", "https://example.test/auto")},
    })
    assert text == "written by a human"


def test_a_subtitle_url_that_fails_falls_through_to_the_next(monkeypatch):
    from providers.reference import ingest

    def get(url, timeout=None):
        if "broken" in url:
            raise RuntimeError("connection reset")
        return _Response('<transcript><text start="0">the fallback</text></transcript>')

    monkeypatch.setattr(ingest.requests, "get", get)

    text = ingest._fetch_transcript({
        "subtitles": {"en": [
            {"ext": "json3", "url": "https://example.test/broken"},
            {"ext": "srv1", "url": "https://example.test/works"},
        ]},
    })
    assert text == "the fallback"


def test_no_subtitles_at_all_is_an_empty_transcript_not_a_crash():
    from providers.reference import ingest

    assert ingest._fetch_transcript({}) == ""
    assert ingest._fetch_transcript({"subtitles": {}, "automatic_captions": {}}) == ""
