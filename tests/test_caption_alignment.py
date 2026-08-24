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
from pydub.generators import Sine
from providers.voice.alignment import _anchor_to_segments, align_words
from providers.voice.chunking import chunk_script


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


# ---------------------------------------------------------------------------
# Synthesis chunk spans are a measurement, and outrank a guess
# ---------------------------------------------------------------------------

HINGLISH = (
    "Kolar Gold Fields ek waqt duniya ki sabse gehri sona ki khaan thi aur "
    "wahan hazaaron log kaam karte the. Do hazaar ek mein ise band kar diya "
    "gaya kyunki nikaalne ki laagat sone ki keemat se zyada ho gayi thi."
)

# What stitch_audio_chunks measures for the two chunks HINGLISH splits into,
# with the 250ms pause it stitches between them.
HINGLISH_SPANS = [
    {"start": 0.0, "end": 6.0, "duration": 6.0},
    {"start": 6.25, "end": 12.25, "duration": 6.0},
]


def test_chunk_spans_beat_a_transcript_that_heard_the_wrong_words(audio_file):
    """The Hinglish case this exists for.

    Whisper on Hindi speech returns one run-on segment and words that are not
    in the script. The spans were measured off the file, so they hold.
    """
    captions = StubCaptions(
        words=[{"word": "BGML", "start": 0.0, "end": 12.25}],
        segments=[{"start": 0.0, "end": 12.25}],
    )

    aligned = align_words(
        audio_file,
        HINGLISH,
        language="hi",
        chunk_spans=HINGLISH_SPANS,
        provider=captions,
    )

    assert [w["word"] for w in aligned] == HINGLISH.split()

    first, second = chunk_script(HINGLISH)
    boundary = len(first.split())
    assert aligned[boundary - 1]["end"] <= 6.0
    assert aligned[boundary]["start"] >= 6.25
    assert aligned[-1]["end"] == pytest.approx(12.25, abs=0.05)


def test_no_caption_is_left_hanging_over_the_stitched_pause(audio_file):
    aligned = align_words(
        audio_file, HINGLISH, language="hi", chunk_spans=HINGLISH_SPANS,
        provider=StubCaptions(segments=[{"start": 0.0, "end": 12.25}]),
    )

    for word in aligned:
        assert not (word["start"] < 6.25 and word["end"] > 6.0), (
            f"{word['word']!r} is on screen during the pause between chunks"
        )


def test_spans_still_anchor_when_the_caption_text_chunks_differently(audio_file):
    """Devanagari audio, Latin captions - the two need not split alike.

    Pairing is off in that case, but the spans are still real speech
    boundaries, so they are used proportionally rather than thrown away for a
    transcript that misheard the language.
    """
    visible = "ek do teen chaar"

    aligned = align_words(
        audio_file, visible, language="hi", chunk_spans=HINGLISH_SPANS,
        provider=StubCaptions(segments=[{"start": 0.0, "end": 99.0}]),
    )

    assert [w["word"] for w in aligned] == visible.split()
    assert aligned[-1]["end"] == pytest.approx(12.25, abs=0.05)


def test_english_keeps_its_exact_transcript_over_the_spans(audio_file):
    """Same script spoken and shown: the measured words are the captions."""
    measured = [
        {"word": "hello", "start": 0.0, "end": 0.62},
        {"word": "world", "start": 0.62, "end": 1.10},
    ]

    aligned = align_words(
        audio_file, "hello world", language="en",
        chunk_spans=[{"start": 0.0, "end": 9.0, "duration": 9.0}],
        provider=StubCaptions(words=measured),
    )

    assert aligned == measured


def test_spans_survive_a_transcriber_that_raises(audio_file):
    class Broken:
        def transcribe(self, audio_path, language=None):
            raise RuntimeError("no model")

    aligned = align_words(
        audio_file, HINGLISH, language="hi", chunk_spans=HINGLISH_SPANS,
        provider=Broken(),
    )

    assert [w["word"] for w in aligned] == HINGLISH.split()


# ---------------------------------------------------------------------------
# Carrying the spans through the stage, across the filter
# ---------------------------------------------------------------------------


class SpanVoice(StubVoice):
    """A voice provider that measured where its chunks landed."""

    def __init__(self, audio_path, spans):
        super().__init__(audio_path)
        self.spans = spans

    def clone_and_generate(self, script_text, voice_sample_path, language="en"):
        result = super().clone_and_generate(script_text, voice_sample_path, language)
        result["chunk_spans"] = list(self.spans)
        return result


def _tone(path, seconds):
    Sine(440).to_audio_segment(duration=int(seconds * 1000)).export(path, format="wav")
    return str(path)


def test_the_spans_reach_alignment(monkeypatch, audio_file):
    spans = [{"start": 0.0, "end": 3.0, "duration": 3.0}]
    seen = {}

    def capture(path, text, language=None, chunk_spans=None, provider=None):
        seen["chunk_spans"] = chunk_spans
        return []

    _wire(monkeypatch, SpanVoice(audio_file, spans), StubCaptions())
    monkeypatch.setattr(voice_agent, "align_words", capture)

    result = voice_agent.run({"script_text": "hello world"}, CONFIG)

    assert result["success"]
    assert seen["chunk_spans"] == spans
    # And they are not smuggled out as part of the stage's output.
    assert "chunk_spans" not in result["output"]


def test_a_tempo_preset_moves_the_spans_with_the_audio(monkeypatch, tmp_path):
    """`energetic` plays the take 5% fast, so every span shortens with it."""
    unfiltered = _tone(tmp_path / "narration.wav", 4.0)
    filtered = _tone(tmp_path / "narration__energetic.wav", 2.0)

    spans = [{"start": 0.0, "end": 2.0, "duration": 2.0},
             {"start": 2.0, "end": 4.0, "duration": 2.0}]
    seen = {}

    def capture(path, text, language=None, chunk_spans=None, provider=None):
        seen["chunk_spans"] = chunk_spans
        return []

    _wire(monkeypatch, SpanVoice(unfiltered, spans), StubCaptions(),
          filtered_path=filtered)
    monkeypatch.setattr(voice_agent, "align_words", capture)

    voice_agent.run({"script_text": "hello", "filter_preset": "energetic"}, CONFIG)

    moved = seen["chunk_spans"]
    assert moved[0]["end"] == pytest.approx(1.0, abs=0.05)
    assert moved[-1]["end"] == pytest.approx(2.0, abs=0.05)


def test_a_preset_that_keeps_the_length_keeps_the_spans(monkeypatch, tmp_path):
    same = _tone(tmp_path / "narration.wav", 3.0)
    filtered = _tone(tmp_path / "narration__warm.wav", 3.0)

    spans = [{"start": 0.0, "end": 3.0, "duration": 3.0}]
    seen = {}

    def capture(path, text, language=None, chunk_spans=None, provider=None):
        seen["chunk_spans"] = chunk_spans
        return []

    _wire(monkeypatch, SpanVoice(same, spans), StubCaptions(), filtered_path=filtered)
    monkeypatch.setattr(voice_agent, "align_words", capture)

    voice_agent.run({"script_text": "hello", "filter_preset": "warm"}, CONFIG)

    assert seen["chunk_spans"] == spans


def test_unmeasurable_audio_drops_the_spans_rather_than_trusting_them(
    monkeypatch, tmp_path, audio_file
):
    """A stale span is worse than none: it would desync every caption."""
    seen = {}

    def capture(path, text, language=None, chunk_spans=None, provider=None):
        seen["chunk_spans"] = chunk_spans
        return []

    spans = [{"start": 0.0, "end": 3.0, "duration": 3.0}]
    _wire(monkeypatch, SpanVoice(audio_file, spans), StubCaptions(),
          filtered_path=audio_file)
    monkeypatch.setattr(voice_agent, "align_words", capture)

    voice_agent.run({"script_text": "hello", "filter_preset": "deep"}, CONFIG)

    assert seen["chunk_spans"] is None


def test_a_provider_without_spans_still_works(monkeypatch, audio_file):
    seen = {}

    def capture(path, text, language=None, chunk_spans=None, provider=None):
        seen["chunk_spans"] = chunk_spans
        return []

    _wire(monkeypatch, StubVoice(audio_file), StubCaptions())
    monkeypatch.setattr(voice_agent, "align_words", capture)

    result = voice_agent.run({"script_text": "hello world"}, CONFIG)

    assert result["success"]
    assert seen["chunk_spans"] is None
