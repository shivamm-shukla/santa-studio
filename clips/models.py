"""Data structures for Clips track: Ingest, Candidate Selection, and Vertical Craft."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import List, Optional

# A clip project is stored exactly like a generated one - same folder, same
# project.json - so `studio ls`, `rm`, `gc` and `export` work on it without
# knowing the difference. That is worth keeping, but it means the two kinds
# of project are indistinguishable on disk unless they say which they are.
# Without this, every clip project appeared in the dashboard's run list as a
# row with no id, no topic and no state.
KIND = "clips"


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
    # Where package_clips_bundle put each platform's render, keyed
    # clip_id -> platform -> path. Held on the project so a bundle survives
    # the request that built it and can be listed and served later.
    bundle: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["kind"] = KIND
        return data

    def clip(self, clip_id: str) -> Optional[CandidateClip]:
        return next((c for c in self.candidates if c.clip_id == clip_id), None)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "ClipProject":
        raw_source = data.get("source") or {}
        source = ClipSource(
            source_type=raw_source.get("source_type", "upload"),
            video_path=raw_source.get("video_path", ""),
            title=raw_source.get("title", ""),
            duration=float(raw_source.get("duration") or 0.0),
            transcript=[TranscriptWord(**w) for w in raw_source.get("transcript") or []],
            sentences=[
                SentenceSpan(
                    text=s.get("text", ""),
                    start=float(s.get("start") or 0.0),
                    end=float(s.get("end") or 0.0),
                    words=[TranscriptWord(**w) for w in s.get("words") or []],
                )
                for s in raw_source.get("sentences") or []
            ],
            metadata=raw_source.get("metadata") or {},
        )
        known = set(CandidateClip.__dataclass_fields__)
        candidates = [
            CandidateClip(**{k: v for k, v in c.items() if k in known})
            for c in data.get("candidates") or []
        ]
        return cls(
            project_id=data.get("project_id", ""),
            source=source,
            candidates=candidates,
            selected_clip_id=data.get("selected_clip_id"),
            bundle=data.get("bundle") or {},
        )

    @classmethod
    def load(cls, path: str) -> "ClipProject":
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
