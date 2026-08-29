import contextlib
import io
import os
import re
import shutil

from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.base import CaptionProvider

# Which Whisper to load. "base" is the smallest there is, and on Hindi it is
# noticeably worse than the larger models - captions are the one part of the
# output a viewer reads word by word, so accuracy is worth the compute here.
# Override with WHISPER_MODEL=base on a machine that cannot spare it.
MODEL_SIZE = os.getenv("WHISPER_MODEL", "medium").strip() or "medium"

# Roughly what each weight file costs on disk. Used to decide whether asking
# for one is affordable, not to verify a download.
MODEL_BYTES = {
    "tiny": 75_000_000,
    "base": 145_000_000,
    "small": 480_000_000,
    "medium": 1_500_000_000,
    "large": 3_000_000_000,
}

# Smallest first, so stepping down from an unaffordable model is a walk left.
LADDER = ("tiny", "base", "small", "medium", "large")

# Left free after a download. A pipeline that has just filled the disk fetching
# a caption model still has a video to render, and rendering is where the space
# actually goes.
DISK_HEADROOM = 2_000_000_000


# The timestamps Whisper prints ahead of each segment it decodes, e.g.
# "[00:12.480 --> 00:16.320]  and then". The end of the last one is how far
# into the audio it has actually got.
HEARD = re.compile(r"-->\s+(?:(\d+):)?(\d{1,2}):(\d{2}(?:\.\d+)?)\]")


def _clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _audio_seconds(path: str) -> float:
    """How long the file is, or 0 if that cannot be read cheaply.

    Only the header is touched. A duration nobody can read costs the progress
    line its fraction, not its existence.
    """
    try:
        import soundfile

        info = soundfile.info(path)
        return float(info.frames) / float(info.samplerate)
    except Exception:
        return 0.0


class _HeardSoFar(io.TextIOBase):
    """Whisper's running commentary, turned into a line on the desk.

    Transcribing ten minutes of narration on a CPU takes minutes, and the
    room used to show one line - "Aligning captions against the finished
    audio" - for the whole of it. There is no callback to hook: `verbose=True`
    makes Whisper print each segment as it decodes it, so this stands in for
    stdout, reads the timestamps back out, and says how far in it has got.

    Deliberately quiet: a segment is a couple of seconds of audio, and a line
    per segment would be a hundred lines of scroll. One per twentieth of the
    file is enough to see it moving.
    """

    STEP = 0.05

    def __init__(self, duration: float):
        self._duration = duration
        self._buffer = ""
        self._reported = 0.0

    def write(self, text: str) -> int:
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._read(line)
        return len(text)

    def _read(self, line: str) -> None:
        found = HEARD.search(line)
        if not found:
            return
        hours, minutes, seconds = found.groups()
        heard = int(hours or 0) * 3600 + int(minutes) * 60 + float(seconds)

        if not self._duration:
            # No duration to measure against: say where it has reached, which
            # still separates a slow transcription from a stuck one.
            self._report(f"Captioning - heard {_clock(heard)} so far", None)
            return

        fraction = min(1.0, heard / self._duration)
        if fraction < self._reported + self.STEP:
            return
        self._reported = fraction
        self._report(
            f"Captioning {_clock(heard)} of {_clock(self._duration)} of narration",
            # The tail of the voice stage: the audio is already made, and this
            # is the last thing standing between it and a finished timeline.
            0.8 + 0.15 * fraction,
        )

    def _report(self, text: str, progress) -> None:
        try:
            import runlog

            runlog.report(text, progress=progress)
        except Exception:
            pass


def _cache_dir() -> str:
    root = os.getenv("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(root, "whisper")


def _already_here(name: str) -> bool:
    """Whether this model is on disk and looks whole.

    Size rather than checksum: hashing a gigabyte and a half to answer a
    question about disk space costs more than the question is worth. It does
    catch the case that matters, which is a download interrupted partway -
    Whisper re-fetches those in full, and a re-fetch is exactly what this is
    trying to find room for.
    """
    path = os.path.join(_cache_dir(), f"{name}.pt")
    try:
        return os.path.getsize(path) >= MODEL_BYTES.get(name, 0) * 0.9
    except OSError:
        return False


def _affordable_model(preferred: str) -> str:
    """The best model that is either already here or has room to arrive.

    The default is `medium`, and on a machine with a couple of gigabytes free
    that is a download which finishes by filling the disk - mid-run, with a
    render still to come. Rather than fail, this steps down the ladder to
    whatever does fit, since worse captions are a better outcome than no video
    and no free space.
    """
    if _already_here(preferred):
        return preferred

    try:
        free = shutil.disk_usage(_cache_dir() if os.path.isdir(_cache_dir()) else os.path.expanduser("~")).free
    except OSError:
        return preferred

    if free >= MODEL_BYTES.get(preferred, 0) + DISK_HEADROOM:
        return preferred

    smaller = LADDER[: LADDER.index(preferred)] if preferred in LADDER else LADDER

    # Anything already on disk beats anything that would have to arrive. We
    # are only here because disk is the thing in short supply, so spending
    # half a gigabyte on a slightly better model than the one already sitting
    # in the cache is the wrong trade.
    for name in reversed(smaller):
        if _already_here(name):
            return name

    for name in reversed(smaller):
        if free >= MODEL_BYTES[name] + DISK_HEADROOM:
            return name

    # Nothing fits. Ask for what was wanted and let Whisper's own failure be
    # the one reported, rather than inventing a different one here.
    return preferred


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
            chosen = _affordable_model(MODEL_SIZE)
            if chosen != MODEL_SIZE:
                try:
                    import runlog

                    runlog.report(
                        f"Not enough disk for the {MODEL_SIZE} caption model; "
                        f"using {chosen} instead"
                    )
                except Exception:
                    pass
            self._model = whisper.load_model(chosen)
        return self._model

    def transcribe(self, audio_path: str, language: str | None = None) -> dict:
        model = self._get_model()
        try:
            # verbose=True is not chatter for its own sake: it is the only
            # progress this model reports, and _HeardSoFar is standing in for
            # stdout to catch it. It also turns Whisper's own tqdm bar off,
            # which was writing carriage returns into the run's log.
            with contextlib.redirect_stdout(_HeardSoFar(_audio_seconds(audio_path))):
                result = model.transcribe(
                    audio_path, word_timestamps=True, language=language, verbose=True
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
