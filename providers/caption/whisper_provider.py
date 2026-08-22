from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import CaptionProvider

# "base" is fast and free-tier friendly; bump to "small"/"medium" later if
# caption accuracy needs to improve and the extra local compute is available.
MODEL_SIZE = "base"


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

        word_timestamps = [
            {"word": w["word"].strip(), "start": float(w["start"]), "end": float(w["end"])}
            for segment in result.get("segments", [])
            for w in segment.get("words", [])
        ]
        return {"word_timestamps": word_timestamps}
