"""How far the captioner has got, while it is still getting there.

Transcribing ten minutes of narration on a CPU takes minutes, and the Voice
desk used to show a single line for the whole of it - "Aligning captions
against the finished audio" - so a slow pass and a stuck one looked the same
from the room.
"""

import runlog
from providers.caption.whisper_provider import _HeardSoFar, WhisperProvider


def _drain(listener):
    lines = []
    while True:
        try:
            event = listener.get_nowait()
        except Exception:
            return lines
        if event.get("type") == "line":
            lines.append(event)


def _say(writer, *seconds):
    for start, end in seconds:
        writer.write(f"[00:{start:02d}.000 --> 00:{end:02d}.000]  something spoken\n")


def test_it_reports_how_far_into_the_audio_it_has_heard():
    listener = runlog.subscribe("run-cap")
    with runlog.bind("run-cap", "VOICE_GENERATION"):
        writer = _HeardSoFar(duration=60.0)
        _say(writer, (0, 6), (6, 12), (12, 30), (30, 59))
    runlog.unsubscribe("run-cap", listener)

    said = [e["text"] for e in _drain(listener)]
    assert "Captioning 0:06 of 1:00 of narration" in said
    assert "Captioning 0:59 of 1:00 of narration" in said


def test_progress_climbs_with_the_audio():
    listener = runlog.subscribe("run-cap-2")
    with runlog.bind("run-cap-2", "VOICE_GENERATION"):
        writer = _HeardSoFar(duration=100.0)
        _say(writer, (0, 10), (10, 50), (50, 99))
    runlog.unsubscribe("run-cap-2", listener)

    climbing = [e["progress"] for e in _drain(listener)]
    assert climbing == sorted(climbing)
    assert 0.8 < climbing[0] < climbing[-1] <= 0.95


def test_a_segment_every_two_seconds_is_not_a_line_every_two_seconds():
    """A hundred segments would be a hundred lines of scroll. One per
    twentieth of the file is enough to see it moving."""
    listener = runlog.subscribe("run-cap-3")
    with runlog.bind("run-cap-3", "VOICE_GENERATION"):
        writer = _HeardSoFar(duration=600.0)
        _say(writer, *[(i * 2, i * 2 + 2) for i in range(150)])
    runlog.unsubscribe("run-cap-3", listener)

    assert len(_drain(listener)) <= 21


def test_an_unreadable_duration_still_says_where_it_has_reached():
    listener = runlog.subscribe("run-cap-4")
    with runlog.bind("run-cap-4", "VOICE_GENERATION"):
        writer = _HeardSoFar(duration=0.0)
        _say(writer, (0, 8))
    runlog.unsubscribe("run-cap-4", listener)

    assert "Captioning - heard 0:08 so far" in [e["text"] for e in _drain(listener)]


def test_whisper_is_asked_to_narrate_itself(monkeypatch, tmp_path):
    """Without verbose=True there is nothing to listen to at all."""
    seen = {}

    class FakeModel:
        def transcribe(self, path, **kwargs):
            seen.update(kwargs)
            print("[00:00.000 --> 00:02.000]  hello")
            return {"segments": []}

    provider = WhisperProvider()
    monkeypatch.setattr(provider, "_get_model", lambda: FakeModel())

    audio = tmp_path / "narration.wav"
    audio.write_bytes(b"")
    provider.transcribe(str(audio))

    assert seen["verbose"] is True
    assert seen["word_timestamps"] is True
