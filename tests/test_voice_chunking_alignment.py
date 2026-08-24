"""Tests for long script chunking, audio stitching, and forced alignment."""

import os
import pytest

pytest.importorskip("pydub")
from pydub import AudioSegment  # noqa: E402
from pydub.generators import Sine  # noqa: E402

from providers.voice.alignment import _fallback_spread_words, align_words
from providers.voice.chatterbox_provider import ChatterboxProvider, interpreter, is_available
from providers.voice.chunking import chunk_script, stitch_audio_chunks


def test_chunk_script_splits_sentences_and_danda():
    text = "Yeh pehla sentence hai. Aur yeh doosra sentence hai! Kya yeh teesra sentence hai? Haan yeh aakhri hai।"
    chunks = chunk_script(text, max_chars=50, max_words=10)
    assert len(chunks) >= 3
    assert any("pehla sentence" in c for c in chunks)
    assert any("doosra sentence" in c for c in chunks)


def test_chunk_script_handles_empty_or_whitespace():
    assert chunk_script("") == []
    assert chunk_script("   \n\t  ") == []


def test_chunk_script_long_clause_splitting():
    long_clause = "Yeh ek bahut hi lamba sentence hai jismein multiple clauses hain, aur isko bina tode padhna mushkil ho jata hai, lekin hum isko asani se split kar sakte hain."
    chunks = chunk_script(long_clause, max_chars=60, max_words=10)
    assert len(chunks) > 1
    # Everything should be preserved without data loss
    reconstructed = " ".join(chunks)
    assert "bahut hi lamba sentence" in reconstructed
    assert "split kar sakte hain" in reconstructed


def test_stitch_audio_chunks(tmp_path):
    c1 = tmp_path / "c1.wav"
    c2 = tmp_path / "c2.wav"
    Sine(440).to_audio_segment(duration=1000).export(c1, format="wav")
    Sine(880).to_audio_segment(duration=1500).export(c2, format="wav")

    out_path, spans = stitch_audio_chunks([str(c1), str(c2)], pause_ms=200)
    assert os.path.exists(out_path)
    assert len(spans) == 2

    audio = AudioSegment.from_file(out_path)
    # Total duration = 1000ms + 200ms pause + 1500ms = 2700ms (~2.7s)
    assert len(audio) == pytest.approx(2700, abs=50)
    assert spans[0]["start"] == 0.0
    assert spans[0]["end"] == 1.0
    assert spans[1]["start"] == 1.2
    assert spans[1]["end"] == 2.7


def test_fallback_spread_words():
    words = _fallback_spread_words("hello world from santa", duration=4.0, start_offset=1.0)
    assert len(words) == 4
    assert words[0]["word"] == "hello"
    assert words[0]["start"] == 1.0
    assert words[0]["end"] == 2.0
    assert words[-1]["end"] == 5.0


def test_align_words_fallback_on_clean_file(tmp_path):
    audio_path = tmp_path / "sample.wav"
    Sine(440).to_audio_segment(duration=2000).export(audio_path, format="wav")

    res = align_words(str(audio_path), "yeh ek testing script hai")
    assert len(res) == 5
    assert res[0]["word"] == "yeh"
    assert res[-1]["word"] == "hai"
    assert res[-1]["end"] == pytest.approx(2.0, abs=0.2)


def test_chatterbox_provider_initialization():
    # The device is chosen by the runner, inside Chatterbox's own interpreter,
    # so there is nothing here to assert about it. What this side owes the
    # caller is a provider that constructs without Chatterbox installed, and an
    # honest answer about whether that interpreter exists.
    ChatterboxProvider()

    where = interpreter()
    assert where is None or os.path.exists(where)
    assert is_available() == (where is not None)
