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
        state_path = f"runs/{run_id_or_path}.json"

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


def ingest_from_youtube(url: str) -> ClipSource:
    """Downloads YouTube video and extracts subtitles using yt-dlp."""
    try:
        import yt_dlp
    except ImportError as e:
        raise RuntimeError("yt-dlp is required for YouTube ingest. Run: pip install yt-dlp") from e

    cache_dir = _cache_dir()
    ydl_opts = {
        "format": "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": os.path.join(cache_dir, "%(id)s.%(ext)s"),
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["en", "hi"],
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id")
        title = info.get("title", "YouTube Video")
        duration = float(info.get("duration", 0.0))
        video_path = os.path.join(cache_dir, f"{video_id}.mp4")

    # Load / align words
    words = []
    # If transcript wasn't loaded from yt-dlp subtitle, fall back to upload flow transcription
    source = ingest_from_upload(video_path)
    source.source_type = "youtube"
    source.title = title
    source.metadata = {"url": url, "youtube_id": video_id}
    return source
