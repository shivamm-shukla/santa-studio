import os
import uuid

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import VoiceProvider

OUTPUT_DIR = "runs/voice_output"


class GTTSProvider(VoiceProvider):
    """Google Translate TTS - free, no API key, no local model download.

    This is the default voice provider because it is the only one that
    works out of a plain `pip install -r requirements.txt`: XTTS needs the
    multi-GB `TTS` package installed by hand (see requirements.txt) before
    it can run at all.

    IMPORTANT - this does NOT clone a voice. gTTS has one fixed synthetic
    voice per language, so `voice_sample_path` is accepted and ignored, and
    a voice profile selected upstream only affects which sample would be
    used *if* the voice provider supported cloning. Switch
    ACTIVE_PROVIDERS["voice"] to "xtts" (after installing coqui-tts) for
    actual cloning; everything else in the pipeline is unchanged by the
    swap.

    Needs network access - the audio is synthesized by Google's endpoint.
    """

    def clone_and_generate(self, script_text: str, voice_sample_path: str) -> dict:
        if not script_text.strip():
            raise RuntimeError("Cannot synthesize speech from empty script text.")

        try:
            from gtts import gTTS
        except ImportError as e:
            raise RuntimeError(
                "The gtts package is not installed. Run: pip install gTTS"
            ) from e

        ensure_ffmpeg_on_path()
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        mp3_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}.mp3")
        gTTS(text=script_text, lang="en").save(mp3_path)

        # Everything downstream (filters, assembly) assumes wav, same as the
        # XTTS provider produces.
        from pydub import AudioSegment

        audio = AudioSegment.from_file(mp3_path)
        output_path = mp3_path.replace(".mp3", ".wav")
        audio.export(output_path, format="wav")
        os.remove(mp3_path)

        # Rough duration-based estimate, matching XTTSProvider - real word
        # timings come from the caption provider transcribing this audio in
        # agents/assembler_agent.py.
        duration = len(audio) / 1000.0
        words = script_text.split()
        word_timestamps = []
        if words:
            per_word = duration / len(words)
            for i, w in enumerate(words):
                word_timestamps.append(
                    {"word": w, "start": round(i * per_word, 2), "end": round((i + 1) * per_word, 2)}
                )

        return {"audio_path": output_path, "word_timestamps": word_timestamps}
