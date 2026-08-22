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
