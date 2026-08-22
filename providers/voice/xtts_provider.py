import os
import threading
import uuid

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import VoiceProvider

OUTPUT_DIR = "runs/voice_output"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"

# Loading XTTS costs ~1.9GB of weights and tens of seconds, and
# registry.get_provider() builds a fresh provider for every agent call - so
# the model is cached on the module, not the instance, or every run would
# pay that cost again.
_MODEL = None
_MODEL_LOCK = threading.Lock()


class XTTSProvider(VoiceProvider):
    """Coqui XTTS-v2 - local, free, clones a voice from ~6s of sample audio.

    LICENSE NOTE: XTTS-v2 ships under Coqui's CPML (Coqui Public Model
    License), which restricts *commercial* use. A monetized YouTube channel
    is commercial use, not personal use - before this runs against real
    revenue, either budget for Coqui's commercial license or switch this
    provider to a permissively-licensed alternative (e.g. Piper TTS, MIT)
    via config.ACTIVE_PROVIDERS["voice"]. This provider is swappable
    either way, so the decision doesn't block anything upstream.

    Coqui's loader demands interactive agreement to that license on first
    use, which would hang any non-interactive caller (the Telegram bot, the
    web server). COQUI_TOS_AGREED=1 in .env records the agreement instead;
    without it this provider refuses to load rather than blocking forever.

    Heavy local dependency (`coqui-tts` + torch + a ~1.9GB model download on
    first use) - expect this to run on a machine with real compute. On CPU,
    synthesis runs at roughly real-time or slower.
    """

    def _get_tts(self):
        global _MODEL
        with _MODEL_LOCK:
            if _MODEL is not None:
                return _MODEL

            if os.getenv("COQUI_TOS_AGREED") != "1":
                raise RuntimeError(
                    "XTTS-v2 is licensed under the Coqui Public Model License "
                    "(non-commercial). Read it at "
                    "https://coqui.ai/cpml, then set COQUI_TOS_AGREED=1 in .env "
                    "to record your agreement. Use the 'gtts' voice provider "
                    "instead if you'd rather not."
                )

            try:
                from TTS.api import TTS
            except ImportError as e:
                raise RuntimeError(
                    "The coqui-tts package is not installed. Run: "
                    "pip install 'coqui-tts[codec]'"
                ) from e

            _MODEL = TTS(MODEL_NAME)
            return _MODEL

    def clone_and_generate(
        self, script_text: str, voice_sample_path: str, language: str = "en"
    ) -> dict:
        if not script_text.strip():
            raise RuntimeError("Cannot synthesize speech from empty script text.")
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
            language=language,
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
