import random

from providers.base import VoiceProvider


class XTTSProvider(VoiceProvider):
    """Coqui XTTS-v2 - local, free, clones a voice from ~6s of sample audio.

    LICENSE NOTE: XTTS-v2 ships under Coqui's CPML (Coqui Public Model
    License), which restricts *commercial* use. A monetized YouTube channel
    is commercial use, not personal use - before wiring the real model in
    Phase 1, either budget for Coqui's commercial license or default to a
    permissively-licensed local alternative (e.g. Piper TTS, MIT) until
    revenue justifies the paid license. This provider is swappable via
    config.ACTIVE_PROVIDERS["voice"] either way, so the decision doesn't
    block anything upstream.
    """

    def clone_and_generate(self, script_text: str, voice_sample_path: str) -> dict:
        # TODO: wire real XTTS-v2 local inference here
        word_count = len(script_text.split())
        word_timestamps = [
            {"word": w, "start": round(i * 0.4, 2), "end": round(i * 0.4 + 0.35, 2)}
            for i, w in enumerate(script_text.split())
        ]
        return {
            "audio_path": f"runs/stub_audio_{random.randint(1000, 9999)}.wav",
            "word_timestamps": word_timestamps[: min(word_count, 50)],
        }
