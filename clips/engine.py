"""Top-level Clips engine orchestrating ingestion, ranking, and vertical generation."""

from __future__ import annotations

import os
import uuid
from typing import List, Optional

import paths
import runlog
from clips.analyzer import rank_candidate_clips
from clips.ingest import (
    ingest_from_studio_run,
    ingest_from_upload,
    ingest_from_youtube,
)
from clips.models import CandidateClip, ClipProject, ClipSource
from clips.reframing import detect_subject_x, render_vertical_clip


def project_json_path(project_id: str) -> Optional[str]:
    """Where a stored clip project lives, or None if there is no such project."""
    directory = paths.find_project(project_id)
    if directory is None:
        return None
    candidate = directory / "project.json"
    return str(candidate) if candidate.exists() else None


def load_project(project_id: str) -> Optional[ClipProject]:
    path = project_json_path(project_id)
    if path is None:
        return None
    try:
        return ClipProject.load(path)
    except (OSError, ValueError, TypeError):
        return None


def save_project(project: ClipProject) -> str:
    """Writes a project back to the same file it was loaded from."""
    path = project_json_path(project.project_id)
    if path is None:
        path = str(
            paths.project_dir(project.project_id, project.source.title or "clips")
            / "project.json"
        )
    project.save(path)
    return path


def create_clip_project(
    source_type: str,
    source_target: str,
    target_count: int = 3,
    render_previews: bool = False,
) -> ClipProject:
    """Ingests a source video, analyzes viral windows, and builds a ClipProject."""
    if source_type == "youtube":
        runlog.report(f"Downloading {source_target}", progress=0.05)
        source = ingest_from_youtube(source_target)
    elif source_type == "studio_run":
        runlog.report(f"Opening studio run {source_target}", progress=0.05)
        source = ingest_from_studio_run(source_target)
    elif source_type == "upload":
        runlog.report(f"Reading {os.path.basename(source_target)}", progress=0.05)
        source = ingest_from_upload(source_target)
    else:
        raise ValueError(f"Unknown source_type: {source_type!r}. Supported: 'youtube', 'upload', 'studio_run'")

    runlog.report(
        f"{source.title or 'source'} - {source.duration:.0f}s, "
        f"{len(source.sentences)} sentence(s) transcribed",
        progress=0.45,
    )

    candidates = rank_candidate_clips(source, target_count=target_count)
    runlog.report(f"Ranked {len(candidates)} candidate moment(s)", progress=0.6)

    # Where to centre the 9:16 crop. CandidateClip.crop_x_offset defaulted to
    # 0.5 and nothing ever computed it, so "subject-aware reframing" was a
    # centre crop with a field for the answer it never worked out.
    if source.video_path and os.path.exists(source.video_path):
        for cand in candidates:
            cand.crop_x_offset = detect_subject_x(
                source.video_path, cand.start_time, cand.end_time
            )
        runlog.report("Worked out where to centre each 9:16 crop", progress=0.7)

    # A clip project is stored exactly like a generated one, so `studio ls`,
    # `rm`, `gc` and `export` all work on it without knowing the difference.
    project_id = uuid.uuid4().hex[:12]
    title = source.title or "clips"
    output = paths.output_dir(project_id, title)

    if render_previews and source.video_path and os.path.exists(source.video_path):
        for i, cand in enumerate(candidates, start=1):
            out_mp4 = str(output / f"{cand.clip_id}.mp4")
            try:
                cand.rendered_path = render_vertical_clip(
                    source_video_path=source.video_path,
                    start_time=cand.start_time,
                    end_time=cand.end_time,
                    output_path=out_mp4,
                    crop_x_center_ratio=cand.crop_x_offset,
                )
                runlog.report(
                    f"Preview {i}/{len(candidates)}: {cand.suggested_title or cand.hook_text[:60]}",
                    progress=0.7 + 0.25 * (i / len(candidates)),
                )
            except Exception as e:
                cand.rendered_path = None
                runlog.report(f"Preview {i} failed: {e}")

    project = ClipProject(
        project_id=project_id,
        source=source,
        candidates=candidates,
        selected_clip_id=candidates[0].clip_id if candidates else None,
    )

    project.save(str(paths.project_dir(project_id, title) / "project.json"))
    runlog.report(f"Clip project {project_id} ready", progress=1.0)

    return project
