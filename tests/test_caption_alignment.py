"""Captions have to be measured off the audio that ships.

Two things were wrong here and both were invisible from the outside:

* Alignment only ran when the spoken script differed from the visible one,
  so an English video kept the voice provider's estimate - gTTS divides the
  total duration by the word count, which drifts on any sentence read
  faster or slower than average.
* Where it did run, it ran *before* the voice filter. The `energetic`
  preset plays the audio back 5% fast, so every caption slid further out of
  sync the longer the video went on.

These use a stub CaptionProvider rather than Whisper, so they assert the
wiring in milliseconds instead of loading a model.
"""

import pytest

import agents.voice_agent as voice_agent
from providers.voice.alignment import _anchor_to_segments, align_words


class StubCaptions:
    """A CaptionProvider that reports fixed measurements."""

    def __init__(self, words=None, segments=None):
        self.words = words or []
        self.segments = segments or []
        self.calls = []

    def transcribe(self, audio_path, language=None):
        self.calls.append({"audio_path": audio_path, "language": language})
        return {"word_timestamps": list(self.words), "segments": list(self.segments)}


class StubVoice:
    def __init__(self, audio_path):
        self.audio_path = audio_path

    def clone_and_generate(self, script_text, voice_sample_path, language="en"):
        # Deliberately naive timings - the kind alignment is meant to replace.
        words = script_text.split()
        return {
            "audio_path": self.audio_path,
            "word_timestamps": [
                {"word": w, "start": float(i), "end": float(i + 1)}
                for i, w in enumerate(words)
            ],
        }


@pytest.fixture
def audio_file(tmp_path):
    path = tmp_path / "narration.wav"
    path.write_bytes(b"RIFF0000WAVE")
    return str(path)


def _wire(monkeypatch, voice, captions, filtered_path=None):
    """Points the registry at stubs and records any filter call."""
    seen = {}

    def fake_get_provider(kind, config):
        if kind == "voice":
            return voice
        if kind == "caption":
            return captions
        raise ValueError(kind)

    def fake_apply_filter(path, preset):
        seen["filtered"] = {"path": path, "preset": preset}
        return filtered_path or path

    monkeypatch.setattr(voice_agent, "get_provider", fake_get_provider)
    monkeypatch.setattr(voice_agent, "apply_filter", fake_apply_filter)
    return seen


CONFIG = {
    "ACTIVE_PROVIDERS": {"voice": "gtts", "caption": "whisper"},
    "OUTPUT_LANGUAGE": "en",
}


# ---------------------------------------------------------------------------
# The caption provider slot is live
# ---------------------------------------------------------------------------


def test_english_captions_are_aligned_not_estimated(monkeypatch, audio_file):
    measured = [
        {"word": "hello", "start": 0.0, "end": 0.62},
        {"word": "world", "start": 0.62, "end": 1.10},
    ]
    captions = StubCaptions(words=measured)
    _wire(monkeypatch, StubVoice(audio_file), captions)

    result = voice_agent.run({"script_text": "hello world"}, CONFIG)

    assert result["success"]
    assert captions.calls, "the caption provider was never asked to transcribe"
    assert result["output"]["word_timestamps"] == measured


def test_alignment_runs_on_the_filtered_audio(monkeypatch, tmp_path, audio_file):
    """A preset that changes tempo changes every timestamp with it."""
    filtered = str(tmp_path / "narration__energetic.wav")
    (tmp_path / "narration__energetic.wav").write_bytes(b"RIFF0000WAVE")

    captions = StubCaptions(words=[{"word": "hello", "start": 0.0, "end": 0.5}])
    seen = _wire(monkeypatch, StubVoice(audio_file), captions, filtered_path=filtered)

    result = voice_agent.run(
        {"script_text": "hello", "filter_preset": "energetic"}, CONFIG
    )

    assert seen["filtered"]["preset"] == "energetic"
    assert captions.calls[-1]["audio_path"] == filtered
    assert result["output"]["audio_path"] == filtered


def test_hinglish_passes_the_visible_text_not_the_spoken_one(monkeypatch, audio_file):
    """Captions are Latin script; only the voice reads Devanagari."""
    captions = StubCaptions(segments=[{"start": 0.0, "end": 2.0}])
    _wire(monkeypatch, StubVoice(audio_file), captions)

    config = dict(CONFIG, OUTPUT_LANGUAGE="hinglish")
    result = voice_agent.run(
        {"script_text": "Aaj hum baat karenge", "script_spoken": "आज हम बात करेंगे"},
        config,
    )

    words = [w["word"] for w in result["output"]["word_timestamps"]]
    assert words == ["Aaj", "hum", "baat", "karenge"]
    assert captions.calls[-1]["language"] == "hi"


def test_a_broken_caption_provider_does_not_fail_the_stage(monkeypatch, audio_file):
    class Exploding:
        def transcribe(self, audio_path, language=None):
            raise RuntimeError("no model on disk")

    _wire(monkeypatch, StubVoice(audio_file), Exploding())

    result = voice_agent.run({"script_text": "hello world"}, CONFIG)

    assert result["success"]
    assert result["output"]["audio_path"] == audio_file


def test_no_caption_provider_configured_still_produces_timings(monkeypatch, audio_file):
    captions = StubCaptions()
    _wire(monkeypatch, StubVoice(audio_file), captions)

    config = {"ACTIVE_PROVIDERS": {"voice": "gtts", "caption": None}, "OUTPUT_LANGUAGE": "en"}
    result = voice_agent.run({"script_text": "hello world"}, config)

    assert result["success"]
    assert not captions.calls


# ---------------------------------------------------------------------------
# Segment anchoring
# ---------------------------------------------------------------------------


def test_anchoring_keeps_every_word_and_respects_pauses():
    segments = [{"start": 0.0, "end": 2.0}, {"start": 5.0, "end": 7.0}]
    words = ["one", "two", "three", "four"]

    aligned = _anchor_to_segments(words, segments)

    assert [w["word"] for w in aligned] == words
    # Nothing is timed into the silence between the two segments.
    assert all(w["end"] <= 2.0 or w["start"] >= 5.0 for w in aligned)
    assert aligned[0]["start"] == 0.0
    assert aligned[-1]["end"] == pytest.approx(7.0, abs=0.01)


def test_anchoring_never_drops_trailing_words():
    """Proportional division rounds down; the remainder has to land somewhere."""
    segments = [{"start": 0.0, "end": 1.0}, {"start": 1.0, "end": 2.0}, {"start": 2.0, "end": 3.0}]
    words = [f"w{i}" for i in range(17)]

    aligned = _anchor_to_segments(words, segments)

    assert [w["word"] for w in aligned] == words
    assert aligned[-1]["end"] <= 3.01


def test_align_words_falls_back_when_there_is_nothing_to_transcribe(tmp_path):
    path = tmp_path / "missing.wav"
    assert align_words(str(path), "some text", language="en") == []
