"""Data structures for Clips track: Ingest, Candidate Selection, and Vertical Craft."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class TranscriptWord:
    word: str
    start: float
    end: float


@dataclass
class SentenceSpan:
    text: str
    start: float
    end: float
    words: List[TranscriptWord] = field(default_factory=list)


@dataclass
class ClipSource:
    source_type: str  # "youtube", "upload", "studio_run"
    video_path: str
    title: str = ""
    duration: float = 0.0
    transcript: List[TranscriptWord] = field(default_factory=list)
    sentences: List[SentenceSpan] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class CandidateClip:
    clip_id: str
    start_time: float
    end_time: float
    duration: float
    hook_text: str
    full_text: str
    score: float
    reasons: List[str] = field(default_factory=list)
    suggested_title: str = ""
    crop_x_offset: float = 0.5  # 0.0 (left) to 1.0 (right), 0.5 is center
    rendered_path: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClipProject:
    project_id: str
    source: ClipSource
    candidates: List[CandidateClip] = field(default_factory=list)
    selected_clip_id: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
