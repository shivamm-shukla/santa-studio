import os

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import CaptionProvider

# Which Whisper to load. "base" is the smallest there is, and on Hindi it is
# noticeably worse than the larger models - captions are the one part of the
# output a viewer reads word by word, so accuracy is worth the compute here.
# Override with WHISPER_MODEL=base on a machine that cannot spare it.
#   tiny ~75MB | base ~150MB | small ~500MB | medium ~1.5GB | large ~3GB
MODEL_SIZE = os.getenv("WHISPER_MODEL", "medium").strip() or "medium"


class WhisperProvider(CaptionProvider):
    """OpenAI Whisper - open-source, local, word-level timestamps for captions.

    Requires the `openai-whisper` package and a system `ffmpeg` install
    (audio decoding goes through ffmpeg regardless of input format). The
    model is loaded lazily and cached on the instance so repeated calls
    within a run don't reload it from disk each time.
    """

    def __init__(self):
        self._model = None

    def _get_model(self):
        ensure_ffmpeg_on_path()
        if self._model is None:
            try:
                import whisper
            except ImportError as e:
                raise RuntimeError(
                    "openai-whisper is not installed. Run: pip install openai-whisper"
                ) from e
            self._model = whisper.load_model(MODEL_SIZE)
        return self._model

    def transcribe(self, audio_path: str, language: str | None = None) -> dict:
        model = self._get_model()
        try:
            result = model.transcribe(
                audio_path, word_timestamps=True, language=language
            )
        except FileNotFoundError as e:
            raise RuntimeError(
                f"ffmpeg not found - Whisper needs it to decode audio. "
                f"Install ffmpeg and retry. ({e})"
            ) from e

        segments = [
            {"start": float(s["start"]), "end": float(s["end"]), "text": s.get("text", "")}
            for s in result.get("segments", [])
        ]
        word_timestamps = [
            {"word": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"])}
            for segment in result.get("segments", [])
            for w in segment.get("words", [])
        ]
        # Segments are returned alongside the words because aligning a
        # Hinglish script needs speech *boundaries* to anchor Latin-script
        # captions against Devanagari audio - the words Whisper heard are
        # in the wrong script to match against directly.
        return {"word_timestamps": word_timestamps, "segments": segments}
