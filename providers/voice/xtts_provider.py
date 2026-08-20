import os
import uuid

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import VoiceProvider

OUTPUT_DIR = "runs/voice_output"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


class XTTSProvider(VoiceProvider):
    """Coqui XTTS-v2 - local, free, clones a voice from ~6s of sample audio.

    LICENSE NOTE: XTTS-v2 ships under Coqui's CPML (Coqui Public Model
    License), which restricts *commercial* use. A monetized YouTube channel
    is commercial use, not personal use - before this runs against real
    revenue, either budget for Coqui's commercial license or switch this
    provider to a permissively-licensed alternative (e.g. Piper TTS, MIT)
    via config.ACTIVE_PROVIDERS["voice"]. This provider is swappable
    either way, so the decision doesn't block anything upstream.

    Heavy local dependency (`TTS` package + torch + a multi-GB model
    download on first use) - expect this to run on a machine with real
    compute (ideally a GPU), not a lightweight sandbox.
    """

    def __init__(self):
        self._tts = None

    def _get_tts(self):
        if self._tts is None:
            try:
                from TTS.api import TTS
            except ImportError as e:
                raise RuntimeError(
                    "The TTS package is not installed. Run: pip install TTS"
                ) from e
            self._tts = TTS(MODEL_NAME)
        return self._tts

    def clone_and_generate(self, script_text: str, voice_sample_path: str) -> dict:
        if not voice_sample_path or not os.path.exists(voice_sample_path):
            raise RuntimeError(
                f"Voice sample not found at {voice_sample_path!r} - a real "
                "sample (~6s of clean speech) is required to clone a voice."
            )

        ensure_ffmpeg_on_path()
        tts = self._get_tts()

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        output_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}.wav")
        tts.tts_to_file(
            text=script_text,
            speaker_wav=voice_sample_path,
            language="en",
            file_path=output_path,
        )

        # Real word-level timestamps come from the caption provider
        # transcribing the actual generated audio (see agents/assembler_agent.py)
        # - XTTS itself doesn't emit reliable alignment, so this is a rough
        # duration-based estimate, good enough for any caller that only
        # needs an approximate pacing signal.
        from pydub import AudioSegment

        duration = len(AudioSegment.from_file(output_path)) / 1000.0
        words = script_text.split()
        word_timestamps = []
        if words:
            per_word = duration / len(words)
            for i, w in enumerate(words):
                word_timestamps.append(
                    {"word": w, "start": round(i * per_word, 2), "end": round((i + 1) * per_word, 2)}
                )

        return {"audio_path": output_path, "word_timestamps": word_timestamps}
