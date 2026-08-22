"""FastAPI web app - the fully branded 'front door' for Santa Studio.

Pure consumer of the existing backend: PipelineManager.step(), the agents,
and the providers are used exactly as CLI/Telegram/Streamlit already use
them. No pipeline logic lives here - only routing, a background-thread
driver for step(), and voice-profile CRUD.
"""

import glob
import json
import os
import sys
import threading
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config
from manager import PipelineHalted, PipelineManager, WORK_STATES
from providers.voice.filters import PRESETS
from providers.voice.profiles import (
    apply_filter_to_profile,
    create_profile,
    delete_profile,
    list_profiles,
)
from state import PipelineState, load_state

WEB_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="Santa Studio")
app.mount("/static", StaticFiles(directory=os.path.join(WEB_DIR, "static")), name="static")
app.mount("/media", StaticFiles(directory="runs"), name="media")
templates = Jinja2Templates(directory=os.path.join(WEB_DIR, "templates"))

RUNS: dict[str, PipelineManager] = {}
STATUS: dict[str, dict] = {}


def _drive_run(run_id: str) -> None:
    mgr = RUNS[run_id]
    try:
        while True:
            result = mgr.step()
            STATUS[run_id] = result
            if result["type"] in ("awaiting_approval", "done"):
                return
    except PipelineHalted as e:
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
    summaries = []
    for path in sorted(glob.glob("runs/*.json"), reverse=True):
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        summaries.append(
            {
                "run_id": data.get("run_id"),
                "niche": data.get("niche"),
                "current_state": data.get("current_state"),
            }
        )
    return summaries


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


@app.get("/voice-studio", response_class=HTMLResponse)
def voice_studio(request: Request):
    return templates.TemplateResponse(
        request,
        "voice_studio.html",
        {"profiles": list_profiles(), "presets": list(PRESETS.keys())},
    )


# ---- Run API --------------------------------------------------------------


@app.post("/api/runs")
def create_run(body: NewRunBody):
    cfg = config.build_config()
    cfg["REVIEW_MODE"] = body.review_mode
    if not body.voice_profile_id:
        # No profile means no sample to clone from, and the default voice
        # provider cannot run without one - fall back rather than halt at
        # VOICE_GENERATION.
        cfg["ACTIVE_PROVIDERS"]["voice"] = "gtts"
    state = PipelineState(
        niche=body.niche,
        user_topic=body.user_topic or None,
        voice_profile_id=body.voice_profile_id,
        target_length_minutes=body.target_length_minutes,
        preferences={},
    )
    RUNS[state.run_id] = PipelineManager(state, cfg, approval_handler=None)
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

    path = os.path.join("runs", f"{run_id}.json")
    if not os.path.exists(path):
        raise HTTPException(404, "No such run")
    state = load_state(path)
    RUNS[run_id] = PipelineManager(state, config.build_config(), approval_handler=None)
    STATUS[run_id] = {"type": "advanced", "state": state.current_state}
    if state.current_state == "DONE":
        STATUS[run_id] = {"type": "done", "video_path": state.video_output["video_path"]}
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
    path = os.path.join("runs", f"{run_id}.json")
    if not os.path.exists(path):
        raise HTTPException(404, "No such run")

    state = load_state(path)
    if state.current_state == "DONE":
        return {"type": "done", "video_path": state.video_output["video_path"]}
    return {"type": "stalled", "state": state.current_state}


@app.post("/api/runs/{run_id}/decision")
def submit_decision(run_id: str, body: DecisionBody):
    mgr = RUNS.get(run_id)
    if not mgr:
        # A decision is an explicit action, so picking the run back up here
        # is what the caller asked for - unlike the polling GET above.
        if not os.path.exists(os.path.join("runs", f"{run_id}.json")):
            raise HTTPException(404, "No such run")
        resume_run(run_id)
        mgr = RUNS[run_id]

    edited_payload = {"edited_text": body.edited_text} if body.edited_text else None
    try:
        result = mgr.step(decision=body.decision, edited_payload=edited_payload)
    except PipelineHalted as e:
        STATUS[run_id] = {"type": "error", "error": str(e)}
        return STATUS[run_id]

    STATUS[run_id] = result
    if result["type"] == "advanced":
        _start_driving(run_id)
    return result


# ---- Voice profile API -----------------------------------------------------


@app.get("/api/voice/presets")
def get_presets():
    return list(PRESETS.keys())


@app.get("/api/voice/profiles")
def get_profiles():
    return list_profiles()


@app.post("/api/voice/profiles")
async def upload_profile(name: str = Form(...), file: UploadFile = File(...)):
    tmp_path = os.path.join("/tmp", f"{uuid.uuid4()}_{file.filename}")
    with open(tmp_path, "wb") as f:
        f.write(await file.read())
    try:
        return create_profile(name, tmp_path)
    finally:
        os.remove(tmp_path)


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
