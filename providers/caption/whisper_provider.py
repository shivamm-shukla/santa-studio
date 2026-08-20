from providers.base import CaptionProvider


class WhisperProvider(CaptionProvider):
    """OpenAI Whisper - open-source, local, word-level timestamps for captions."""

    def transcribe(self, audio_path: str) -> dict:
        # TODO: wire real local Whisper inference here
        return {
            "word_timestamps": [
                {"word": "stub", "start": 0.0, "end": 0.4},
                {"word": "caption", "start": 0.4, "end": 0.9},
            ]
        }
