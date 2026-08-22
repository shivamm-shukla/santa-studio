"""PipelineState schema and JSON persistence."""

import json
import os
import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone


@dataclass
class PipelineState:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_state: str = "IDLE"
    niche: str = ""
    preferences: dict = field(default_factory=dict)
    user_topic: str | None = None
    voice_sample_path: str = ""
    voice_profile_id: str | None = None
    target_length_minutes: int = 5

    topic: str | None = None
    reference_analysis: dict | None = None
    research: dict | None = None
    factcheck: dict | None = None
    script: dict | None = None
    voice_output: dict | None = None
    visual_output: dict | None = None
    video_output: dict | None = None
    shorts_output: dict | None = None
    thumbnails: dict | None = None
    # Title/description/tags plus the chosen thumbnail. Drafted before the
    # publish gate; whatever the human leaves here is what actually ships.
    publish_metadata: dict | None = None
    publish_output: dict | None = None

    history: list = field(default_factory=list)

    def log(self, state: str, event: str, detail: str = "") -> None:
        self.history.append(
            {
                "state": state,
                "event": event,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )


def save_state(state: PipelineState, path: str) -> None:
    dirname = os.path.dirname(path)
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    temp_path = f"{path}.tmp.{uuid.uuid4().hex[:8]}"
    try:
        with open(temp_path, "w") as f:
            json.dump(asdict(state), f, indent=2, default=str)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def load_state(path: str) -> PipelineState:
    with open(path) as f:
        data = json.load(f)
    known = {f.name for f in fields(PipelineState)}
    filtered = {k: v for k, v in data.items() if k in known}
    return PipelineState(**filtered)


# --------------------------------------------------------------------------
# Finding saved runs
# --------------------------------------------------------------------------

def saved_runs(unfinished_only: bool = False) -> list[dict]:
    """Every project's stored state, newest first.

    All four frontends need this and all four used to glob "runs/*.json"
    for themselves, which is how they each ended up looking somewhere the
    pipeline had stopped writing. One implementation, reading the storage
    layout, so they cannot drift apart again.
    """
    import paths

    found = []
    for directory in paths.list_projects():
        path = directory / "project.json"
        if not path.exists():
            continue
        try:
            with open(path) as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError):
            continue
        if unfinished_only and data.get("current_state") in ("DONE", None):
            continue
        data["_path"] = str(path)
        found.append(data)
    return found


def find_run(run_id: str) -> str | None:
    """The state file for a run id (or id fragment), or None."""
    import paths

    directory = paths.find_project(run_id)
    if directory is None:
        return None
    path = directory / "project.json"
    return str(path) if path.exists() else None
