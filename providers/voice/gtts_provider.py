import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import VoiceProvider

OUTPUT_DIR = "runs/voice_output"

# gTTS synthesises its internal chunks one HTTP request at a time, so a
# multi-minute script spends most of the stage waiting on round-trips.
# Splitting the script ourselves and requesting the pieces concurrently
# turns that wait into one round-trip's worth. Capped to stay well under
# the rate at which the endpoint starts refusing requests.
MAX_PARALLEL_CHUNKS = 8
# Long enough that sentence rhythm survives, short enough to parallelise.
TARGET_CHUNK_CHARS = 200


def _split_for_synthesis(text: str) -> list[str]:
    """Splits a script into chunks on sentence boundaries.

    Splitting mid-sentence would put an audible seam in the middle of a
    phrase when the pieces are concatenated, so chunks only ever end where
    a sentence does.
    """
    sentences = [s.strip() for s in re.split(r"(?<=[.!?\u0964])\s+", text) if s.strip()]
    if not sentences:
        return [text]

    chunks, current = [], ""
    for sentence in sentences:
        if current and len(current) + len(sentence) + 1 > TARGET_CHUNK_CHARS:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


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

    def clone_and_generate(
        self, script_text: str, voice_sample_path: str, language: str = "en"
    ) -> dict:
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

        from pydub import AudioSegment

        chunks = _split_for_synthesis(script_text)
        run_dir = os.path.join(OUTPUT_DIR, str(uuid.uuid4()))
        os.makedirs(run_dir, exist_ok=True)

        def synth(indexed_chunk):
            i, chunk = indexed_chunk
            part_path = os.path.join(run_dir, f"{i:04d}.mp3")
            gTTS(text=chunk, lang=language).save(part_path)
            return part_path

        try:
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHUNKS) as pool:
                # map() preserves order, so the pieces concatenate in
                # the order they were spoken.
                parts = list(pool.map(synth, enumerate(chunks)))

            audio = AudioSegment.empty()
            for part in parts:
                audio += AudioSegment.from_file(part)
        finally:
            for name in os.listdir(run_dir):
                os.remove(os.path.join(run_dir, name))
            os.rmdir(run_dir)

        # Everything downstream (filters, assembly) assumes wav, same as the
        # XTTS provider produces.
        output_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}.wav")
        audio.export(output_path, format="wav")

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
