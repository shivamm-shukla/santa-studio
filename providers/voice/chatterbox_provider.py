"""Chatterbox Voice Provider (Resemble AI).

MIT-licensed zero-shot voice cloning with multilingual support (including Hindi
and English) and paralinguistic tag support. Weights are open source and safe
for commercial monetization.
"""

from __future__ import annotations

import os
import tempfile
import threading
import uuid
from typing import Optional

import paths
from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import VoiceProvider
from providers.voice.alignment import align_words
from providers.voice.chunking import chunk_script, stitch_audio_chunks

_MODEL = None
_MODEL_LOCK = threading.Lock()


class ChatterboxProvider(VoiceProvider):
    """Chatterbox TTS - open-source, MIT license, zero-shot voice cloning.

    Supports multilingual synthesis (Hindi, English, etc.) from a reference sample.
    """

    def __init__(self, device: Optional[str] = None):
        self._device = device

    def _get_device(self) -> str:
        if self._device:
            return self._device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _get_tts(self, language: str = "en"):
        global _MODEL
        with _MODEL_LOCK:
            if _MODEL is not None:
                return _MODEL

            try:
                # Prefer Multilingual model for Hindi/Hinglish or standard Chatterbox
                if language in ("hi", "hinglish"):
                    try:
                        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
                        _MODEL = ChatterboxMultilingualTTS.from_pretrained(device=self._get_device())
                    except (ImportError, AttributeError):
                        from chatterbox.tts import ChatterboxTTS
                        _MODEL = ChatterboxTTS.from_pretrained(device=self._get_device())
                else:
                    try:
                        from chatterbox.tts_turbo import ChatterboxTurboTTS
                        _MODEL = ChatterboxTurboTTS.from_pretrained(device=self._get_device())
                    except (ImportError, AttributeError):
                        from chatterbox.tts import ChatterboxTTS
                        _MODEL = ChatterboxTTS.from_pretrained(device=self._get_device())
            except ImportError as e:
                raise RuntimeError(
                    "The chatterbox-tts package is not installed. Run: "
                    "pip install chatterbox-tts"
                ) from e

            return _MODEL

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
        tts = self._get_tts(language=language)

        chunks = chunk_script(script_text)
        if not chunks:
            chunks = [script_text]

        chunk_files = []
        try:
            import torchaudio as ta
        except ImportError:
            ta = None

        for chunk_text in chunks:
            handle, tmp_chunk_path = tempfile.mkstemp(suffix=".wav")
            os.close(handle)

            # Generate via chatterbox API
            # signature: generate(text, audio_prompt_path=..., language_id=...)
            kwargs = {"audio_prompt_path": voice_sample_path}
            if hasattr(tts, "generate"):
                try:
                    if "language_id" in tts.generate.__code__.co_varnames:
                        kwargs["language_id"] = "hi" if language in ("hi", "hinglish") else "en"
                except Exception:
                    pass

                wav = tts.generate(chunk_text, **kwargs)
                sr = getattr(tts, "sr", 24000)
                if ta is not None and hasattr(wav, "shape"):
                    ta.save(tmp_chunk_path, wav, sr)
                else:
                    import soundfile as sf
                    sf.write(tmp_chunk_path, wav, sr)
            elif hasattr(tts, "tts_to_file"):
                tts.tts_to_file(
                    text=chunk_text,
                    speaker_wav=voice_sample_path,
                    language=language,
                    file_path=tmp_chunk_path,
                )
            else:
                raise RuntimeError("Unsupported Chatterbox model interface.")

            chunk_files.append(tmp_chunk_path)

        output_dir = str(paths.home() / "tmp")
        os.makedirs(output_dir, exist_ok=True)
        final_output_path = os.path.join(output_dir, f"narration_{uuid.uuid4().hex[:8]}.wav")

        final_path, chunk_spans = stitch_audio_chunks(
            chunk_files, output_path=final_output_path, pause_ms=250
        )

        # Cleanup temporary chunk files
        for cf in chunk_files:
            try:
                os.remove(cf)
            except OSError:
                pass

        word_timestamps = align_words(
            final_path, script_text, language=language, chunk_spans=chunk_spans
        )

        return {"audio_path": final_path, "word_timestamps": word_timestamps}
