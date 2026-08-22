"""Multi-source ingestion engine for Clips track (YouTube, Direct Upload, Studio Run)."""

from __future__ import annotations

import json
import os
import re
from typing import Optional

import paths
from clips.models import ClipSource, SentenceSpan, TranscriptWord
from clips.transcript import words_to_sentences


def _cache_dir() -> str:
    directory = paths.home() / "cache" / "clips_ingest"
    os.makedirs(directory, exist_ok=True)
    return str(directory)


def ingest_from_studio_run(run_id_or_path: str) -> ClipSource:
    """Ingests a completed long-form video from Santa Studio's run directory."""
    if os.path.exists(run_id_or_path) and run_id_or_path.endswith(".json"):
        state_path = run_id_or_path
    else:
        project = paths.find_project(run_id_or_path)
        if project is None:
            raise FileNotFoundError(
                f"No project in the library matches {run_id_or_path!r}. "
                "Run `studio.py ls` to see what is there."
            )
        state_path = str(project / "project.json")

    if not os.path.exists(state_path):
        raise FileNotFoundError(f"Studio run file not found at {state_path!r}")

    with open(state_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    video_path = (data.get("video_output") or {}).get("video_path", "")
    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"Rendered video for run {run_id_or_path} not found on disk")

    raw_words = (data.get("voice_output") or {}).get("word_timestamps") or []
    words = [
        TranscriptWord(
            word=w.get("word", ""),
            start=float(w.get("start", 0.0)),
            end=float(w.get("end", 0.0)),
        )
        for w in raw_words
    ]
    sentences = words_to_sentences(words)

    # Get duration
    duration = 0.0
    if words:
        duration = words[-1].end
    elif os.path.exists(video_path):
        try:
            from moviepy import VideoFileClip
            with VideoFileClip(video_path) as clip:
                duration = float(clip.duration)
        except Exception:
            duration = 0.0

    return ClipSource(
        source_type="studio_run",
        video_path=video_path,
        title=data.get("topic") or "Studio Project",
        duration=duration,
        transcript=words,
        sentences=sentences,
        metadata={"run_id": data.get("run_id")},
    )


def ingest_from_upload(video_path: str, transcript_data: Optional[list] = None) -> ClipSource:
    """Ingests a local uploaded MP4 file, optionally running Whisper for transcript timings."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Uploaded video not found at {video_path!r}")

    words: list[TranscriptWord] = []
    if transcript_data:
        words = [
            TranscriptWord(
                word=w.get("word", ""),
                start=float(w.get("start", 0.0)),
                end=float(w.get("end", 0.0)),
            )
            for w in transcript_data
        ]
    else:
        # Transcribe with Whisper if available
        try:
            import whisper
            model = whisper.load_model("tiny")
            res = model.transcribe(video_path, word_timestamps=True)
            for segment in res.get("segments", []):
                for w in segment.get("words", []):
                    words.append(
                        TranscriptWord(
                            word=w.get("word", ""),
                            start=float(w.get("start", 0.0)),
                            end=float(w.get("end", 0.0)),
                        )
                    )
        except Exception:
            words = []

    sentences = words_to_sentences(words)

    duration = 0.0
    try:
        from moviepy import VideoFileClip
        with VideoFileClip(video_path) as clip:
            duration = float(clip.duration)
    except Exception:
        if words:
            duration = words[-1].end

    title = os.path.splitext(os.path.basename(video_path))[0]
    return ClipSource(
        source_type="upload",
        video_path=video_path,
        title=title,
        duration=duration,
        transcript=words,
        sentences=sentences,
    )


_VTT_CUE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)
_VTT_TAG = re.compile(r"<[^>]+>")


def _vtt_seconds(hours: str, minutes: str, seconds: str, millis: str) -> float:
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(millis) / 1000.0


def parse_subtitle_file(path: str) -> list[TranscriptWord]:
    """Word timings from a WebVTT/SRT subtitle track.

    The source's own subtitles beat re-transcribing it: they are already
    written down, they are free, and on a long video Whisper is minutes of
    CPU. Cue text is spread evenly across the cue, which is a much smaller
    approximation than spreading it across the whole file - a cue is a few
    seconds long.
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []

    words: list[TranscriptWord] = []
    index = 0
    while index < len(lines):
        match = _VTT_CUE.search(lines[index])
        if not match:
            index += 1
            continue

        start = _vtt_seconds(*match.groups()[:4])
        end = _vtt_seconds(*match.groups()[4:])
        index += 1

        text_lines = []
        while index < len(lines) and lines[index].strip() and not _VTT_CUE.search(lines[index]):
            text_lines.append(_VTT_TAG.sub("", lines[index]))
            index += 1

        tokens = " ".join(text_lines).split()
        # Auto-generated captions repeat the previous cue as a rolling
        # window; skip a cue that only restates what we already have.
        if not tokens or end <= start:
            continue
        recent = [w.word for w in words[-len(tokens):]]
        if recent == tokens:
            continue

        per_word = (end - start) / len(tokens)
        for position, token in enumerate(tokens):
            words.append(TranscriptWord(
                word=token,
                start=round(start + position * per_word, 2),
                end=round(start + (position + 1) * per_word, 2),
            ))

    return words


def _find_subtitles(cache_dir: str, video_id: str) -> str:
    """The best subtitle file yt-dlp wrote for this video, if any."""
    preferred = []
    for language in ("en", "hi"):
        for extension in ("vtt", "srt"):
            preferred.append(os.path.join(cache_dir, f"{video_id}.{language}.{extension}"))
    for candidate in preferred:
        if os.path.exists(candidate):
            return candidate
    return ""


def ingest_from_youtube(url: str) -> ClipSource:
    """Downloads a YouTube video and reads its subtitles, or transcribes it.

    Two bugs lived here. The subtitle options were set and the files
    downloaded, but nothing ever opened them - `words = []` was assigned and
    immediately discarded, so every ingest paid for a full Whisper pass over
    a transcript that was already sitting on disk. And the download path was
    assumed to be `<id>.mp4` while the format selector can fall back to
    anything, and a merged `bestvideo+bestaudio` is routinely `.mkv`, so the
    next line raised FileNotFoundError on a file that had downloaded fine.
    """
    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError("yt-dlp is required for YouTube ingest. Run: pip install yt-dlp") from e

    cache_dir = _cache_dir()
    ydl_opts = {
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        # Forces the merge container, so the path below is predictable.
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(cache_dir, "%(id)s.%(ext)s"),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "hi"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id")
        title = info.get("title", "YouTube Video")
        duration = float(info.get("duration") or 0.0)
        video_path = _downloaded_path(info, cache_dir, video_id)

    words = parse_subtitle_file(_find_subtitles(cache_dir, video_id))
    if words:
        source = ClipSource(
            source_type="youtube",
            video_path=video_path,
            title=title,
            duration=duration or (words[-1].end if words else 0.0),
            transcript=words,
            sentences=words_to_sentences(words),
        )
    else:
        # No subtitles published for this video - transcribe it ourselves.
        source = ingest_from_upload(video_path)
        source.source_type = "youtube"
        source.title = title
        if duration:
            source.duration = duration

    source.metadata = {"url": url, "youtube_id": video_id}
    return source


def _downloaded_path(info: dict, cache_dir: str, video_id: str) -> str:
    """Whatever yt-dlp actually wrote, rather than what we hoped it wrote."""
    for download in info.get("requested_downloads") or []:
        path = download.get("filepath") or download.get("_filename")
        if path and os.path.exists(path):
            return path

    direct = info.get("filepath") or info.get("_filename")
    if direct and os.path.exists(direct):
        return direct

    for extension in ("mp4", "mkv", "webm", "m4a"):
        candidate = os.path.join(cache_dir, f"{video_id}.{extension}")
        if os.path.exists(candidate):
            return candidate

    raise FileNotFoundError(
        f"yt-dlp reported success for {video_id!r} but no media file was found "
        f"in {cache_dir!r}."
    )
