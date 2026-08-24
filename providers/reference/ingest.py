"""Reference video ingestion: extracts structural metadata and transcripts via yt-dlp.

Never downloads full video files unless explicitly asked - extracts metadata,
subtitles, and structural pacing markers with minimal bandwidth and zero token cost.
"""

from __future__ import annotations

import json
import re
from typing import Optional

import requests

# Subtitle formats we can read, best first. json3 is already segmented into
# words; the others need unpicking.
_READABLE_FORMATS = ("json3", "srv1", "vtt")

_TIMESTAMP = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->")
_TAG = re.compile(r"<[^>]+>")


def _slugify(text: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower()).strip('-')
    return cleaned[:40] or "reference"


def _parse_json3(body: str) -> str:
    events = json.loads(body).get("events") or []
    words = []
    for event in events:
        for seg in event.get("segs") or []:
            text = (seg.get("utf8") or "").strip()
            if text:
                words.append(text)
    return " ".join(words)


def _parse_srv1(body: str) -> str:
    return " ".join(
        _TAG.sub("", chunk).strip()
        for chunk in re.findall(r"<text[^>]*>(.*?)</text>", body, re.DOTALL)
    )


def _parse_vtt(body: str) -> str:
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line == "WEBVTT" or _TIMESTAMP.match(line):
            continue
        if line.startswith(("NOTE", "Kind:", "Language:")) or line.isdigit():
            continue
        cleaned = _TAG.sub("", line).strip()
        # Rolling auto-captions repeat the previous line as they scroll.
        if cleaned and cleaned != (lines[-1] if lines else None):
            lines.append(cleaned)
    return " ".join(lines)


_PARSERS = {"json3": _parse_json3, "srv1": _parse_srv1, "vtt": _parse_vtt}


def _fetch_transcript(info: dict) -> str:
    """The spoken text of a reference video, or "" if there is none to had.

    yt-dlp hands back subtitle *tracks* - a language, a format, and a URL -
    not the words. Fetching that URL is the whole job, and skipping it is how
    this returned an empty transcript for every reference it was ever given.
    Manual subtitles are preferred over auto-generated ones; English and Hindi
    over whatever else is on offer.
    """
    manual = info.get("subtitles") or {}
    automatic = info.get("automatic_captions") or {}

    for tracks in (manual, automatic):
        if not tracks:
            continue
        languages = [lang for lang in ("en", "hi") if tracks.get(lang)]
        languages += [lang for lang in tracks if lang not in languages]

        for lang in languages:
            for fmt in _READABLE_FORMATS:
                track = next(
                    (t for t in tracks[lang] if t.get("ext") == fmt and t.get("url")),
                    None,
                )
                if not track:
                    continue
                try:
                    response = requests.get(track["url"], timeout=20)
                    response.raise_for_status()
                    text = _PARSERS[fmt](response.text)
                except Exception:
                    continue
                if text.strip():
                    return text.strip()
    return ""


def ingest_reference(url: str) -> dict:
    """Ingests metadata and transcript from a reference URL."""
    if not url or not url.strip():
        return {}

    url = url.strip()

    # Try yt-dlp if available
    try:
        import yt_dlp

        ydl_opts = {
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": ["en", "hi"],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info:
                title = info.get("title", "")
                channel = info.get("uploader") or info.get("channel") or _slugify(title)
                duration = float(info.get("duration") or 0.0)
                description = info.get("description", "")
                tags = info.get("tags") or []

                transcript_text = _fetch_transcript(info)

                # The word count feeds the words-per-minute the whole style
                # profile is built from, so falling back to the description
                # does not merely lose detail - it measures the wrong thing
                # entirely. Better to leave it at zero and let the analyser
                # use its default than to claim a 20-minute video was narrated
                # at the speed of its description.
                words = len(transcript_text.split())
                return {
                    "url": url,
                    "channel": channel,
                    "channel_slug": _slugify(channel),
                    "title": title,
                    "duration": duration,
                    "transcript": transcript_text,
                    "description": description[:1000],
                    "word_count": words,
                    "tags": tags[:10],
                    "method": "yt-dlp",
                }
    except Exception:
        pass

    # Fallback structure parser
    channel_guess = "reference_channel"
    if "youtube.com" in url or "youtu.be" in url:
        match = re.search(r'(@[a-zA-Z0-9_\-]+)', url)
        if match:
            channel_guess = match.group(1).lstrip('@')
        else:
            match = re.search(r'(?:v=|/)([a-zA-Z0-9_-]{11})', url)
            if match:
                channel_guess = f"yt_{match.group(1)}"

    return {
        "url": url,
        "channel": channel_guess,
        "channel_slug": _slugify(channel_guess),
        "title": channel_guess,
        "duration": 600.0,
        "transcript": "",
        "description": "",
        "word_count": 1500,
        "tags": [],
        "method": "heuristic",
    }
