"""What the Voice desk shows while a clone is being narrated.

Cloning a few hundred words on a CPU takes tens of minutes, and the room used
to show one line - "Narrating 561 words" - for the whole of it, because the
runner was driven by subprocess.run(capture_output=True): its progress lines
existed, but both pipes were only read once the child had already exited. You
could not tell a slow run from a hung one without going and looking at `ps`.
"""

import json
import os
import sys

import pytest

import runlog
from providers.voice import chatterbox_provider


FAKE_RUNNER = '''
import json, sys
request = json.load(sys.stdin)
chunks = request["chunks"]
sys.stderr.write("some model chatter\\n")
sys.stderr.write('@progress {"event": "loading", "total": %d}\\n' % len(chunks))
sys.stderr.flush()
files = []
for i, _ in enumerate(chunks):
    path = request["out_dir"] + "/chunk_%03d.wav" % i
    open(path, "w").write("x")
    files.append(path)
    sys.stderr.write('@progress {"event": "chunk", "done": %d, "total": %d}\\n' % (i + 1, len(chunks)))
    sys.stderr.flush()
json.dump({"files": files, "sample_rate": 24000}, sys.stdout)
'''

SILENT_RUNNER = '''
import sys
sys.stderr.write("CUDA out of memory\\n")
'''


def _runner(tmp_path, source, monkeypatch):
    script = tmp_path / "runner.py"
    script.write_text(source)
    monkeypatch.setattr(chatterbox_provider, "RUNNER", str(script))
    monkeypatch.setattr(chatterbox_provider, "interpreter", lambda: sys.executable)
    return chatterbox_provider.ChatterboxProvider()


def _drain(listener):
    lines = []
    while True:
        try:
            event = listener.get_nowait()
        except Exception:
            return lines
        if event.get("type") == "line":
            lines.append(event)


def test_every_finished_piece_reaches_the_room(tmp_path, monkeypatch):
    provider = _runner(tmp_path, FAKE_RUNNER, monkeypatch)
    out_dir = tmp_path / "work"
    out_dir.mkdir()

    listener = runlog.subscribe("run-voice")
    with runlog.bind("run-voice", "VOICE_GENERATION"):
        files = provider._synthesise(["one", "two", "three"], "ref.wav", "en", str(out_dir))
    runlog.unsubscribe("run-voice", listener)

    assert len(files) == 3
    said = [e["text"] for e in _drain(listener)]
    assert any("Loading the voice model" in line for line in said)
    assert "Narrated 1 of 3 pieces" in said
    assert "Narrated 3 of 3 pieces" in said


def test_progress_climbs_and_is_reported_for_the_voice_desk(tmp_path, monkeypatch):
    provider = _runner(tmp_path, FAKE_RUNNER, monkeypatch)
    out_dir = tmp_path / "work"
    out_dir.mkdir()

    listener = runlog.subscribe("run-voice-2")
    with runlog.bind("run-voice-2", "VOICE_GENERATION"):
        provider._synthesise(["one", "two"], "ref.wav", "en", str(out_dir))
    runlog.unsubscribe("run-voice-2", listener)

    events = _drain(listener)
    assert all(e["agent"] == "voice" for e in events)
    climbing = [e["progress"] for e in events]
    assert climbing == sorted(climbing)
    assert climbing[-1] > climbing[0]


def test_a_runner_that_says_nothing_still_explains_itself(tmp_path, monkeypatch):
    """The stderr tail is the only account of a model that died on startup."""
    provider = _runner(tmp_path, SILENT_RUNNER, monkeypatch)

    with pytest.raises(RuntimeError) as failure:
        provider._synthesise(["one"], "ref.wav", "en", str(tmp_path))

    assert "CUDA out of memory" in str(failure.value)


def test_a_runner_that_hangs_is_killed_rather_than_waited_on(tmp_path, monkeypatch):
    provider = _runner(tmp_path, "import time\ntime.sleep(30)\n", monkeypatch)
    monkeypatch.setattr(chatterbox_provider, "TIMEOUT_SECONDS", 1)

    with pytest.raises(RuntimeError) as failure:
        provider._synthesise(["one"], "ref.wav", "en", str(tmp_path))

    assert "did not finish" in str(failure.value)
