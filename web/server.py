"""FastAPI web app - the fully branded 'front door' for Santa Studio.

Pure consumer of the existing backend: PipelineManager.step(), the agents,
and the providers are used exactly as CLI/Telegram/Streamlit already use
them. No pipeline logic lives here - only routing, a background-thread
driver for step(), and voice-profile CRUD.
"""

import asyncio
import json
import os
import queue
import sys
import threading
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config
import paths
import runlog
from clips import engine as clips_engine
from clips import publisher as clips_publisher
from manager import PipelineHalted, PipelineManager, WORK_STATES
from providers.publish import youtube_provider
from providers.voice.filters import PRESETS
from providers.voice.profiles import (
    apply_filter_to_profile,
    create_profile,
    delete_profile,
    list_profiles,
)
from state import (
    PipelineState,
    find_run,
    load_state,
    saved_clip_projects,
    saved_runs,
)

WEB_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Santa Studio")
app.mount("/static", StaticFiles(directory=os.path.join(WEB_DIR, "static")), name="static")
app.mount("/media", StaticFiles(directory=str(paths.projects_dir())), name="media")

# "The Room" - the 3D studio front end. Built separately (cd room && npm run
# build); served here when a build exists so it shares an origin with the API.
# In development it runs on its own Vite server, which proxies /api back here.
ROOM_DIST = os.path.join(os.path.dirname(WEB_DIR), "room", "dist")
if os.path.isdir(ROOM_DIST):
    app.mount("/room", StaticFiles(directory=ROOM_DIST, html=True), name="room")
templates = Jinja2Templates(directory=os.path.join(WEB_DIR, "templates"))

RUNS: dict[str, PipelineManager] = {}
STATUS: dict[str, dict] = {}


def _drive_run(run_id: str) -> None:
    mgr = RUNS.get(run_id)
    if not mgr:
        return
    try:
        while True:
            result = mgr.step()
            STATUS[run_id] = result
            if result["type"] in ("awaiting_approval", "done"):
                return
    except PipelineHalted as e:
        STATUS[run_id] = {"type": "error", "error": str(e)}
    except Exception as e:
        STATUS[run_id] = {"type": "error", "error": str(e)}


def _start_driving(run_id: str) -> None:
    threading.Thread(target=_drive_run, args=(run_id,), daemon=True).start()


class NewRunBody(BaseModel):
    niche: str
    user_topic: str | None = None
    voice_profile_id: str | None = None
    review_mode: str = "autonomous"
    target_length_minutes: int = 5


class DecisionBody(BaseModel):
    decision: str
    edited_text: str | None = None


class FilterBody(BaseModel):
    preset: str


def _list_run_summaries() -> list[dict]:
    return [
        {
            "run_id": data.get("run_id"),
            "niche": data.get("niche"),
            "topic": data.get("topic") or data.get("user_topic") or "",
            "current_state": data.get("current_state"),
        }
        for data in saved_runs()
    ]


# ---- Pages --------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"runs": _list_run_summaries(), "profiles": list_profiles()},
    )


@app.get("/run/{run_id}", response_class=HTMLResponse)
def run_page(request: Request, run_id: str):
    return templates.TemplateResponse(
        request, "run.html", {"run_id": run_id, "work_states": WORK_STATES}
    )


@app.get("/clips", response_class=HTMLResponse)
def clips_page(request: Request):
    # Only finished runs are worth offering as a clip source: a run still
    # mid-assembly has no video to cut.
    finished = [
        {"run_id": r.get("run_id"), "topic": r.get("topic"), "niche": r.get("niche")}
        for r in saved_runs()
        if r.get("current_state") == "DONE"
    ]
    return templates.TemplateResponse(
        request,
        "clips.html",
        {"projects": list_clip_projects(), "runs": finished},
    )


@app.get("/clips/{project_id}", response_class=HTMLResponse)
def clip_project_page(request: Request, project_id: str):
    return templates.TemplateResponse(
        request, "clip_project.html", {"project_id": project_id}
    )


@app.get("/voice-studio", response_class=HTMLResponse)
def voice_studio(request: Request):
    return templates.TemplateResponse(
        request,
        "voice_studio.html",
        {"profiles": list_profiles(), "presets": list(PRESETS.keys())},
    )


# ---- Run API --------------------------------------------------------------


def _config_for(state: PipelineState) -> dict:
    """Rebuilds the config a run was started with.

    Review mode and the voice fallback used to live only in the in-memory
    config, so a run resumed after a restart silently reverted to whatever
    the environment defaulted to - a checkpoints run came back autonomous,
    and a run with no voice profile came back pointed at a cloning provider
    with nothing to clone from. They are part of the run, so they are stored
    with it.
    """
    cfg = config.build_config()
    preferences = state.preferences or {}
    if preferences.get("review_mode"):
        cfg["REVIEW_MODE"] = preferences["review_mode"]
    if preferences.get("voice_provider"):
        cfg["ACTIVE_PROVIDERS"]["voice"] = preferences["voice_provider"]
    return cfg


@app.post("/api/runs")
def create_run(body: NewRunBody):
    preferences = {"review_mode": body.review_mode}
    if not body.voice_profile_id:
        # No profile means no sample to clone from, and a cloning provider
        # cannot run without one - fall back rather than halt at
        # VOICE_GENERATION.
        preferences["voice_provider"] = "gtts"

    state = PipelineState(
        niche=body.niche,
        user_topic=body.user_topic or None,
        voice_profile_id=body.voice_profile_id,
        target_length_minutes=body.target_length_minutes,
        preferences=preferences,
    )
    RUNS[state.run_id] = PipelineManager(state, _config_for(state), approval_handler=None)
    STATUS[state.run_id] = {"type": "advanced", "state": "IDLE"}
    _start_driving(state.run_id)
    return {"run_id": state.run_id}


@app.post("/api/runs/{run_id}/resume")
def resume_run(run_id: str):
    if run_id in RUNS:
        # Already active in this process (e.g. just created via POST
        # /api/runs) - resuming again would spin up a second concurrent
        # PipelineManager/thread for the same run_id, so no-op instead.
        return {"run_id": run_id}

    path = find_run(run_id)
    if path is None:
        raise HTTPException(404, "No such run")
    state = load_state(path)
    RUNS[run_id] = PipelineManager(state, _config_for(state), approval_handler=None)
    STATUS[run_id] = {"type": "advanced", "state": state.current_state}
    if state.current_state == "DONE":
        STATUS[run_id] = {"type": "done", "video_path": (state.video_output or {}).get("video_path", "")}
    else:
        _start_driving(run_id)
    return {"run_id": run_id}


@app.get("/api/runs/{run_id}/status")
def run_status(run_id: str):
    if run_id in STATUS:
        return STATUS[run_id]

    # RUNS/STATUS live in process memory, so a server restart orphans every
    # in-flight run and the page would otherwise poll a 404 forever. Report
    # what is on disk - but do NOT start driving it. A GET that silently
    # restarts a pipeline makes a run impossible to stop: every stray poll
    # from an open tab would resurrect it. Resuming stays an explicit POST.
    path = find_run(run_id)
    if path is None:
        raise HTTPException(404, "No such run")

    state = load_state(path)
    if state.current_state == "DONE":
        return {"type": "done", "video_path": (state.video_output or {}).get("video_path", "")}
    return {"type": "stalled", "state": state.current_state}


@app.post("/api/runs/{run_id}/decision")
def submit_decision(run_id: str, body: DecisionBody):
    mgr = RUNS.get(run_id)
    if not mgr:
        # A decision is an explicit action, so picking the run back up here
        # is what the caller asked for - unlike the polling GET above.
        if find_run(run_id) is None:
            raise HTTPException(404, "No such run")
        resume_run(run_id)
        mgr = RUNS[run_id]

    edited_payload = {"edited_text": body.edited_text} if body.edited_text else None
    try:
        result = mgr.step(decision=body.decision, edited_payload=edited_payload)
    except PipelineHalted as e:
        STATUS[run_id] = {"type": "error", "error": str(e)}
        return STATUS[run_id]
    except Exception as e:
        STATUS[run_id] = {"type": "error", "error": str(e)}
        return STATUS[run_id]

    STATUS[run_id] = result
    if result["type"] == "advanced":
        _start_driving(run_id)
    return result


# ---- Live activity ---------------------------------------------------------


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request):
    """Server-sent events: what every agent is doing, as they do it.

    SSE rather than a WebSocket because this is strictly one-way - the room
    watches, and answers gates through the ordinary decision endpoint - and
    because SSE reconnects on its own when a laptop sleeps.

    A browser that connects late is sent the buffered history first, so a
    desk shows the work already done instead of an empty screen.
    """

    async def stream():
        listener = runlog.subscribe(run_id)
        try:
            for event in runlog.history(run_id):
                yield f"data: {json.dumps(event)}\n\n"

            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.to_thread(listener.get, True, 15.0)
                except queue.Empty:
                    # A comment frame; keeps proxies from closing an idle
                    # connection during a long render.
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            runlog.unsubscribe(run_id, listener)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Clips API -------------------------------------------------------------
#
# Ingesting a video and rendering a bundle are both far too slow to answer a
# request on, exactly like a pipeline run - so they use the same shape: a
# background thread, a status dict, and the live feed for progress. A clips
# job publishes to runlog under its own job id, so /api/clips/{job}/events is
# the same stream the room already knows how to read.

CLIP_JOBS: dict[str, dict] = {}


class NewClipProjectBody(BaseModel):
    source_type: str          # "youtube" | "studio_run" | "upload"
    source_target: str        # a URL, a run id, or a path from /api/clips/upload
    target_count: int = 3
    render_previews: bool = True


class BundleBody(BaseModel):
    platforms: list[str] | None = None


class PublishClipBody(BaseModel):
    clip_id: str
    title: str | None = None
    description: str = ""
    tags: list[str] | None = None
    privacy_status: str = "private"
    dry_run: bool = False


def _clip_job(job_id: str, work) -> None:
    """Runs one clips job, recording its outcome and reporting as it goes."""
    CLIP_JOBS[job_id] = {"status": "running", "detail": ""}
    try:
        # SHORTS_EXTRACTION is the shorts desk in the room, which is the desk
        # this work belongs to - so a clips job appears there like any other.
        with runlog.bind(job_id, "SHORTS_EXTRACTION"):
            result = work()
        CLIP_JOBS[job_id] = {"status": "done", **result}
        runlog.publish(job_id, {"type": "done", **result})
    except Exception as e:
        CLIP_JOBS[job_id] = {"status": "error", "error": str(e)}
        runlog.publish(job_id, {"type": "error", "agent": "shorts", "text": str(e)})


@app.get("/api/clips/platforms")
def clip_platforms():
    """Every target a clip can be cut for, with the numbers behind each."""
    return clips_publisher.PLATFORM_PRESETS


@app.get("/api/clips")
def list_clip_projects():
    return [
        {
            "project_id": data.get("project_id"),
            "title": (data.get("source") or {}).get("title", ""),
            "source_type": (data.get("source") or {}).get("source_type", ""),
            "duration": (data.get("source") or {}).get("duration", 0.0),
            "candidates": len(data.get("candidates") or []),
        }
        for data in saved_clip_projects()
    ]


@app.post("/api/clips/upload")
async def upload_clip_source(file: UploadFile = File(...)):
    """Takes a video to cut clips from and returns the path to feed back in."""
    destination = paths.tmp_dir() / f"{uuid.uuid4().hex}_{os.path.basename(file.filename or 'upload.mp4')}"
    with open(destination, "wb") as handle:
        while chunk := await file.read(1 << 20):
            handle.write(chunk)
    return {"path": str(destination)}


@app.post("/api/clips")
def create_clip_project(body: NewClipProjectBody):
    if body.source_type not in ("youtube", "studio_run", "upload"):
        raise HTTPException(400, f"Unknown source_type {body.source_type!r}")
    if not body.source_target.strip():
        raise HTTPException(400, "source_target is required")

    job_id = uuid.uuid4().hex[:12]

    def work():
        project = clips_engine.create_clip_project(
            source_type=body.source_type,
            source_target=body.source_target.strip(),
            target_count=body.target_count,
            render_previews=body.render_previews,
        )
        return {"project_id": project.project_id}

    threading.Thread(target=_clip_job, args=(job_id, work), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/clips/jobs/{job_id}")
def clip_job_status(job_id: str):
    if job_id not in CLIP_JOBS:
        raise HTTPException(404, "No such job")
    return CLIP_JOBS[job_id]


@app.get("/api/clips/{project_id}")
def get_clip_project(project_id: str):
    project = clips_engine.load_project(project_id)
    if project is None:
        raise HTTPException(404, "No such clip project")

    return {
        "project_id": project.project_id,
        "selected_clip_id": project.selected_clip_id,
        "source": {
            "title": project.source.title,
            "source_type": project.source.source_type,
            "duration": project.source.duration,
            "has_video": bool(project.source.video_path) and os.path.exists(project.source.video_path),
        },
        "candidates": [
            {
                **clip.to_dict(),
                "has_preview": bool(clip.rendered_path) and os.path.exists(clip.rendered_path),
                "downloads": {
                    platform: f"/api/clips/{project_id}/download/{clip.clip_id}/{platform}"
                    for platform, path in (project.bundle.get(clip.clip_id) or {}).items()
                    if os.path.exists(path)
                },
            }
            for clip in project.candidates
        ],
    }


@app.post("/api/clips/{project_id}/bundle")
def bundle_clip_project(project_id: str, body: BundleBody):
    """Renders every candidate for every requested platform, in the background."""
    project = clips_engine.load_project(project_id)
    if project is None:
        raise HTTPException(404, "No such clip project")

    platforms = body.platforms or ["youtube_shorts", "instagram_reels", "twitter"]
    unknown = [p for p in platforms if p not in clips_publisher.PLATFORM_PRESETS]
    if unknown:
        raise HTTPException(400, f"Unknown platform(s): {unknown}")

    job_id = uuid.uuid4().hex[:12]

    def work():
        runlog.report(f"Rendering {len(project.candidates)} clip(s) for {', '.join(platforms)}")
        manifest = clips_publisher.package_clips_bundle(project, platforms=platforms)
        # package_clips_bundle records what it wrote on the project; saving
        # is what makes those files findable by a later request.
        clips_engine.save_project(project)
        rendered = sum(len(v) for v in project.bundle.values())
        runlog.report(f"{rendered} file(s) ready to download", progress=1.0)
        return {"project_id": project_id, "clips": len(manifest["clips"]), "files": rendered}

    threading.Thread(target=_clip_job, args=(job_id, work), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/clips/{project_id}/download/{clip_id}/{platform}")
def download_clip(project_id: str, clip_id: str, platform: str):
    """The rendered file for one clip on one platform, as a download.

    This is what "a downloadable clip for Instagram" actually means: the
    bundle wrote per-platform renders to disk and returned a manifest, and
    until now nothing served them.
    """
    project = clips_engine.load_project(project_id)
    if project is None:
        raise HTTPException(404, "No such clip project")

    path = (project.bundle.get(clip_id) or {}).get(platform)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Not rendered for that platform yet - build the bundle first")

    clip = project.clip(clip_id)
    stem = paths.slugify(clip.suggested_title or clip.hook_text or clip_id) if clip else clip_id
    return FileResponse(path, media_type="video/mp4", filename=f"{stem}_{platform}.mp4")


@app.get("/api/clips/{project_id}/preview/{clip_id}")
def preview_clip(project_id: str, clip_id: str):
    """The 9:16 preview render, played inline rather than downloaded."""
    project = clips_engine.load_project(project_id)
    if project is None:
        raise HTTPException(404, "No such clip project")
    clip = project.clip(clip_id)
    if clip is None or not clip.rendered_path or not os.path.exists(clip.rendered_path):
        raise HTTPException(404, "No preview for that clip")
    return FileResponse(clip.rendered_path, media_type="video/mp4")


@app.post("/api/clips/{project_id}/publish")
def publish_clip(project_id: str, body: PublishClipBody):
    """Uploads one clip to YouTube as a Short."""
    project = clips_engine.load_project(project_id)
    if project is None:
        raise HTTPException(404, "No such clip project")
    clip = project.clip(body.clip_id)
    if clip is None:
        raise HTTPException(404, "No such clip in that project")

    # Prefer the YouTube Shorts cut if a bundle was built; fall back to the
    # preview render. Publishing the wrong aspect ratio is worse than a 404.
    path = (project.bundle.get(clip.clip_id) or {}).get("youtube_shorts") or clip.rendered_path
    if not path or not os.path.exists(path):
        raise HTTPException(400, "Nothing rendered for this clip yet - build the bundle first")

    if not body.dry_run:
        status = youtube_provider.auth_status()
        if not status["connected"]:
            raise HTTPException(409, f"YouTube is not connected. {status['detail']}")

    try:
        return clips_publisher.publish_short_to_youtube(
            clip=clip,
            rendered_clip_path=path,
            title=body.title or clip.suggested_title or clip.hook_text,
            description=body.description,
            tags=body.tags,
            privacy_status=body.privacy_status,
            dry_run=body.dry_run,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/clips/{job_or_project}/events")
async def clip_events(job_or_project: str, request: Request):
    """The same live feed the room reads, for a clips job."""
    return await run_events(job_or_project, request)


# ---- Publishing ------------------------------------------------------------


# Set while the browser flow is open, so a UI can say "waiting for you in the
# browser" rather than looking as though nothing happened.
YOUTUBE_CONNECT: dict = {"running": False, "error": ""}


@app.get("/api/publish/youtube/status")
def youtube_status():
    return {
        **youtube_provider.auth_status(),
        "connecting": YOUTUBE_CONNECT["running"],
        "last_error": YOUTUBE_CONNECT["error"],
    }


@app.post("/api/publish/youtube/connect")
def youtube_connect():
    """Starts the OAuth flow.

    It opens a browser on the machine running the server and blocks until
    the user finishes, so it runs on a thread of its own and the caller
    polls status. This is a local studio: that machine is the user's.
    """
    if YOUTUBE_CONNECT["running"]:
        return {"started": False, "detail": "A connection attempt is already in progress."}

    def work():
        YOUTUBE_CONNECT.update(running=True, error="")
        try:
            youtube_provider.connect()
        except Exception as e:
            YOUTUBE_CONNECT["error"] = str(e)
        finally:
            YOUTUBE_CONNECT["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return {"started": True}


@app.post("/api/publish/youtube/disconnect")
def youtube_disconnect():
    return youtube_provider.disconnect()


# ---- Voice profile API -----------------------------------------------------


@app.get("/api/voice/presets")
def get_presets():
    return list(PRESETS.keys())


@app.get("/api/voice/profiles")
def get_profiles():
    return list_profiles()


@app.post("/api/voice/profiles")
async def upload_profile(name: str = Form(...), file: UploadFile = File(...)):
    import tempfile

    tmp_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}_{file.filename}")
    with open(tmp_path, "wb") as f:
        f.write(await file.read())
    try:
        return create_profile(name, tmp_path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


@app.post("/api/voice/profiles/{profile_id}/filter")
def filter_profile(profile_id: str, body: FilterBody):
    try:
        return apply_filter_to_profile(profile_id, body.preset)
    except KeyError:
        raise HTTPException(404, "No such profile")


@app.delete("/api/voice/profiles/{profile_id}")
def remove_profile(profile_id: str):
    delete_profile(profile_id)
    return {"ok": True}
