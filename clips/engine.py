"""Top-level Clips engine orchestrating ingestion, ranking, and vertical generation."""

from __future__ import annotations

import os
import uuid
from typing import List, Optional

from clips.analyzer import rank_candidate_clips
from clips.ingest import (
    ingest_from_studio_run,
    ingest_from_upload,
    ingest_from_youtube,
)
from clips.models import CandidateClip, ClipProject, ClipSource
from clips.reframing import render_vertical_clip


def create_clip_project(
    source_type: str,
    source_target: str,
    target_count: int = 3,
    render_previews: bool = False,
) -> ClipProject:
    """Ingests a source video, analyzes viral windows, and builds a ClipProject."""
    if source_type == "youtube":
        source = ingest_from_youtube(source_target)
    elif source_type == "studio_run":
        source = ingest_from_studio_run(source_target)
    elif source_type == "upload":
        source = ingest_from_upload(source_target)
    else:
        raise ValueError(f"Unknown source_type: {source_type!r}. Supported: 'youtube', 'upload', 'studio_run'")

    candidates = rank_candidate_clips(source, target_count=target_count)

    project_id = f"clip_proj_{uuid.uuid4().hex[:8]}"
    os.makedirs("runs/clips", exist_ok=True)

    if render_previews and source.video_path and os.path.exists(source.video_path):
        for cand in candidates:
            out_mp4 = f"runs/clips/{project_id}_{cand.clip_id}.mp4"
            try:
                cand.rendered_path = render_vertical_clip(
                    source_video_path=source.video_path,
                    start_time=cand.start_time,
                    end_time=cand.end_time,
                    output_path=out_mp4,
                    crop_x_center_ratio=cand.crop_x_offset,
                )
            except Exception:
                cand.rendered_path = None

    project = ClipProject(
        project_id=project_id,
        source=source,
        candidates=candidates,
        selected_clip_id=candidates[0].clip_id if candidates else None,
    )

    project_json_path = f"runs/clips/{project_id}.json"
    project.save(project_json_path)

    return project
