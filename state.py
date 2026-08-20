"""PipelineState schema and JSON persistence."""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class PipelineState:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    current_state: str = "IDLE"
    niche: str = ""
    preferences: dict = field(default_factory=dict)
    user_topic: str | None = None
    voice_sample_path: str = ""

    topic: str | None = None
    reference_analysis: dict | None = None
    research: dict | None = None
    factcheck: dict | None = None
    script: dict | None = None
    voice_output: dict | None = None
    visual_output: dict | None = None
    video_output: dict | None = None

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
    with open(path, "w") as f:
        json.dump(asdict(state), f, indent=2, default=str)


def load_state(path: str) -> PipelineState:
    with open(path) as f:
        data = json.load(f)
    return PipelineState(**data)
