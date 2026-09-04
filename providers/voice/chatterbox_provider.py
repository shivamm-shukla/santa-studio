"""Chatterbox Voice Provider (Resemble AI).

MIT-licensed zero-shot voice cloning with multilingual support (including
Hindi and English). The weights are open and safe for commercial use, which
XTTS-v2's are not - see providers/voice/xtts_provider.py for that note.

Synthesis does not happen in this process. Chatterbox pins torch==2.6.0,
numpy<2 and transformers==5.2.0, while the studio runs torch 2.13 and numpy
2.5 with whisper, coqui-tts and moviepy on top of them; installing it
alongside would downgrade the stack the rest of the pipeline depends on. So
it gets an interpreter of its own and is driven as a subprocess - see
chatterbox_runner.py, which is the only thing that runs in it.

Everything either side of synthesis stays here: chunking a long script,
stitching the pieces back together, and aligning captions against the audio
that actually ships.
"""

from __future__ import annotations

import collections
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Optional

import paths
import runlog
from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import VoiceProvider
from providers.voice import pace
from providers.voice.alignment import align_words
from providers.voice.chunking import chunk_script, stitch_audio_chunks

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chatterbox_runner.py")

# Loading the model and synthesising a few minutes of narration on a CPU is
# slow, and a run that is nearly finished should not be thrown away for being
# a little slower than expected.
TIMEOUT_SECONDS = int(os.getenv("CHATTERBOX_TIMEOUT", "3600"))

# How the reading is dialled in. These names are the model's own generation
# parameters and are passed straight through to it; the runner holds the
# narration-tuned defaults and only applies the ones its model accepts, so
# leaving any of these unset is the normal case.
DIAL_ENV = {
    "exaggeration": "VOICE_EXAGGERATION",
    "cfg_weight": "VOICE_CFG_WEIGHT",
    "temperature": "VOICE_TEMPERATURE",
    "repetition_penalty": "VOICE_REPETITION_PENALTY",
}

# Playback speed of the finished narration, 1.0 being however fast the
# reference clip reads. Applied after stitching, pitch preserved.
PACE_ENV = "VOICE_PACE"


def dials_from_env() -> dict:
    """The generation settings a run has overridden, if any."""
    settings = {}
    for name, variable in DIAL_ENV.items():
        raw = os.getenv(variable, "").strip()
        if not raw:
            continue
        try:
            settings[name] = float(raw)
        except ValueError:
            # A typo in a dial should not lose a run that is otherwise fine;
            # the tuned default is a perfectly good answer.
            continue
    return settings


def pace_from_env() -> float:
    raw = os.getenv(PACE_ENV, "").strip()
    if not raw:
        return 1.0
    try:
        return float(raw)
    except ValueError:
        return 1.0

# What the runner prefixes a progress line with. Everything else it writes to
# stderr is the model narrating itself, and is kept only to explain a failure.
PROGRESS_PREFIX = "@progress "


def _progress_from(line: str) -> Optional[dict]:
    if not line.startswith(PROGRESS_PREFIX):
        return None
    try:
        note = json.loads(line[len(PROGRESS_PREFIX):])
    except ValueError:
        return None
    return note if isinstance(note, dict) else None


def _time_left(seconds: float) -> str:
    if seconds < 75:
        return "under a minute left"
    return f"about {round(seconds / 60)} min left"


class _Report:
    """The runner's chunk counter, as a line on the Voice desk.

    Cloning is slow enough on a CPU that "how much is done" is the only
    question worth answering while it runs, and the estimate is measured from
    the pieces this machine has actually finished rather than guessed from
    the word count - the first piece also pays for loading the model, so it
    is left out of the average.
    """

    def __init__(self):
        self._first_done_at = None

    def __call__(self, note: dict) -> None:
        event = note.get("event")
        total = int(note.get("total") or 0)

        if event == "loading":
            runlog.report(
                f"Loading the voice model ({total} pieces to narrate)", progress=0.18
            )
            return
        if event == "loaded":
            runlog.report("Model loaded - narrating the first piece", progress=0.2)
            return
        if event != "chunk" or not total:
            return

        done = int(note.get("done") or 0)
        now = time.monotonic()
        if self._first_done_at is None or done <= 1:
            self._first_done_at = now
            left = ""
        else:
            per_piece = (now - self._first_done_at) / (done - 1)
            left = "" if done >= total else f" - {_time_left(per_piece * (total - done))}"

        runlog.report(
            f"Narrated {done} of {total} pieces{left}",
            progress=0.2 + 0.35 * (done / total),
        )


def _reply_from(stdout: str) -> Optional[dict]:
    """The JSON reply out of whatever else ended up on stdout.

    The runner keeps its own stdout clean, but it is one library upgrade away
    from a new progress line landing there, and a run that synthesised
    correctly should not be thrown away over a banner. The reply is the last
    JSON object written, so read backwards for it.
    """
    stdout = stdout.strip()
    if not stdout:
        return None

    try:
        parsed = json.loads(stdout)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        pass

    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def interpreter() -> Optional[str]:
    """The Python that has Chatterbox installed, or None.

    CHATTERBOX_PYTHON points at it explicitly; otherwise the venv the setup
    docs create. Returning None rather than raising lets `doctor` and the
    provider registry report it as missing without a stack trace.
    """
    explicit = os.getenv("CHATTERBOX_PYTHON", "").strip()
    if explicit:
        return explicit if os.path.exists(explicit) else None

    candidate = paths.home() / "venvs" / "chatterbox" / "bin" / "python"
    return str(candidate) if candidate.exists() else None


def is_available() -> bool:
    return interpreter() is not None


class ChatterboxProvider(VoiceProvider):
    """Zero-shot voice cloning from a reference sample."""

    def __init__(self, device: Optional[str] = None):
        # Kept for interface compatibility; the runner picks its own device
        # from what its own torch can see.
        self._device = device

    def _synthesise(
        self, chunks: list[str], reference: str, language: str, out_dir: str
    ) -> tuple[list[str], int]:
        python = interpreter()
        if not python:
            raise RuntimeError(
                "Chatterbox is not installed. It needs an environment of its "
                "own because it pins torch 2.6 and numpy 1.x; see the README, "
                "or set CHATTERBOX_PYTHON to an interpreter that has it."
            )

        request = json.dumps({
            "chunks": chunks,
            "reference": reference,
            "language": language,
            "out_dir": out_dir,
            "voice": dials_from_env(),
        })

        stdout, tail = self._drive(python, request)

        if not stdout.strip():
            # stderr carries the real reason - a missing model download, an
            # out-of-memory kill - and losing it makes this impossible to
            # diagnose from a run log.
            raise RuntimeError(
                "Chatterbox produced no output. " + (" / ".join(tail[-5:]) if tail else "")
            )

        result = _reply_from(stdout)
        if result is None:
            raise RuntimeError(f"Chatterbox returned unreadable output: {stdout[:200]}")

        if "error" in result:
            raise RuntimeError(f"Chatterbox failed: {result['error']}")

        files = result.get("files") or []
        if not files:
            raise RuntimeError("Chatterbox returned no audio.")
        # The model's own rate, not an assumed one. Resampling a 22.05k take
        # as if it were 24k is a silent 9% speed and pitch error, which is
        # exactly the kind of thing that makes a clone sound wrong without
        # anything looking broken.
        return files, int(result.get("sample_rate") or 24000)

    def _drive(self, python: str, request: str) -> tuple[str, list[str]]:
        """Runs the runner and listens to it while it works.

        This used to be a single subprocess.run(capture_output=True), which
        reads both pipes only once the child has exited: the runner's progress
        lines existed but nobody heard them until the work they described was
        already over. The pipes are pumped by threads instead, so a chunk
        finishing reaches the room the moment it finishes, and the timeout is
        still enforced from here.
        """
        process = subprocess.Popen(
            [python, RUNNER],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        tail: collections.deque[str] = collections.deque(maxlen=40)
        out: list[str] = []
        report = _Report()
        # runlog's binding is per-thread, and the pump is not the thread the
        # agent runs on, so it carries the agent's run and state over itself.
        active = runlog.current()

        def watch_stderr():
            with (runlog.bind(*active) if active else contextlib.nullcontext()):
                for raw in process.stderr:
                    line = raw.rstrip()
                    note = _progress_from(line)
                    if note:
                        report(note)
                    elif line:
                        tail.append(line)

        def collect_stdout():
            out.append(process.stdout.read())

        pumps = [
            threading.Thread(target=watch_stderr, daemon=True),
            threading.Thread(target=collect_stdout, daemon=True),
        ]
        for pump in pumps:
            pump.start()

        try:
            process.stdin.write(request)
            process.stdin.close()
        except (BrokenPipeError, ValueError):
            pass  # died on startup; the wait below reports why

        try:
            process.wait(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as e:
            process.kill()
            raise RuntimeError(
                f"Chatterbox did not finish within {TIMEOUT_SECONDS}s. Raise "
                "CHATTERBOX_TIMEOUT, or use a shorter script."
            ) from e

        for pump in pumps:
            pump.join(timeout=5)
        return "".join(out), list(tail)

    def clone_and_generate(
        self, script_text: str, voice_sample_path: str, language: str = "en"
    ) -> dict:
        if not script_text.strip():
            raise RuntimeError("Cannot synthesize speech from empty script text.")
        if not voice_sample_path or not os.path.exists(voice_sample_path):
            raise RuntimeError(
                f"Voice sample not found at {voice_sample_path!r} - a real "
                "sample (~8-20s of speech) is required to clone a voice."
            )

        ensure_ffmpeg_on_path()

        chunks = chunk_script(script_text) or [script_text]
        work_dir = tempfile.mkdtemp(prefix="chatterbox-")
        try:
            chunk_files, sample_rate = self._synthesise(
                chunks, voice_sample_path, language, work_dir
            )

            output_dir = str(paths.scoped_dir("voice"))
            os.makedirs(output_dir, exist_ok=True)
            # `texts` is what makes the joins sound like punctuation rather
            # than like a metronome: the gap after a piece is chosen by what
            # that piece ends on, so a comma gets a breath and a full stop
            # gets a beat.
            final_path, chunk_spans = stitch_audio_chunks(
                chunk_files,
                output_path=os.path.join(output_dir, "narration.wav"),
                sample_rate=sample_rate,
                texts=chunks,
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        speed = pace_from_env()
        retimed = pace.retime(
            final_path, speed, output_path=os.path.join(output_dir, "narration_paced.wav")
        )
        if retimed != final_path:
            runlog.report(f"Narration retimed to {speed:.2f}x")
            final_path = retimed
            chunk_spans = pace.rescale_spans(chunk_spans, speed)

        word_timestamps = align_words(
            final_path, script_text, language=language, chunk_spans=chunk_spans
        )
        # The spans go back with the audio because the caller may filter it and
        # re-align: every preset is a uniform time transform, so the spans stay
        # usable once scaled by the duration the filter produced.
        return {
            "audio_path": final_path,
            "word_timestamps": word_timestamps,
            "chunk_spans": chunk_spans,
        }
