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

import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional

import paths
from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import VoiceProvider
from providers.voice.alignment import align_words
from providers.voice.chunking import chunk_script, stitch_audio_chunks

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chatterbox_runner.py")

# Loading the model and synthesising a few minutes of narration on a CPU is
# slow, and a run that is nearly finished should not be thrown away for being
# a little slower than expected.
TIMEOUT_SECONDS = int(os.getenv("CHATTERBOX_TIMEOUT", "3600"))


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

    def _synthesise(self, chunks: list[str], reference: str, language: str, out_dir: str) -> list[str]:
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
        })

        try:
            completed = subprocess.run(
                [python, RUNNER],
                input=request,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(
                f"Chatterbox did not finish within {TIMEOUT_SECONDS}s. Raise "
                "CHATTERBOX_TIMEOUT, or use a shorter script."
            ) from e

        stdout = (completed.stdout or "").strip()
        if not stdout:
            # stderr carries the real reason - a missing model download, an
            # out-of-memory kill - and losing it makes this impossible to
            # diagnose from a run log.
            tail = (completed.stderr or "").strip().splitlines()[-5:]
            raise RuntimeError(
                "Chatterbox produced no output. " + (" / ".join(tail) if tail else "")
            )

        try:
            result = json.loads(stdout)
        except ValueError as e:
            raise RuntimeError(f"Chatterbox returned unreadable output: {stdout[:200]}") from e

        if "error" in result:
            raise RuntimeError(f"Chatterbox failed: {result['error']}")

        files = result.get("files") or []
        if not files:
            raise RuntimeError("Chatterbox returned no audio.")
        return files

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
            chunk_files = self._synthesise(chunks, voice_sample_path, language, work_dir)

            output_dir = str(paths.scoped_dir("voice"))
            os.makedirs(output_dir, exist_ok=True)
            final_path, chunk_spans = stitch_audio_chunks(
                chunk_files,
                output_path=os.path.join(output_dir, "narration.wav"),
                pause_ms=250,
            )
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)

        word_timestamps = align_words(
            final_path, script_text, language=language, chunk_spans=chunk_spans
        )
        return {"audio_path": final_path, "word_timestamps": word_timestamps}
