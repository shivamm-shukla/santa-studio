"""Orchestrator: drives the pipeline state machine, one agent per state,
validates output, persists state to JSON after every transition, and
pauses for human approval at gates controlled by config["REVIEW_MODE"].
"""

import os

from agents import (
    assembler_agent,
    factcheck_agent,
    reference_agent,
    research_agent,
    script_agent,
    thumbnail,
    topic_agent,
    visual_agent,
    voice_agent,
    youtube_publish,
)
from state import PipelineState, save_state

WORK_STATES = [
    "TOPIC_SELECTION",
    "REFERENCE_ANALYSIS",
    "RESEARCHING",
    "FACT_CHECKING",
    "SCRIPTING",
    "VOICE_GENERATION",
    "VISUAL_SELECTION",
    "VIDEO_ASSEMBLY",
    "THUMBNAIL",
    "YOUTUBE_PUBLISH",
]

# Gates are ordinary members of the sequence, so advancing past one uses
# the same index+1 step as advancing past a work state.
STATE_SEQUENCE = [
    "IDLE",
    "TOPIC_SELECTION",
    "REFERENCE_ANALYSIS",
    "RESEARCHING",
    "FACT_CHECKING",
    "SCRIPTING",
    "VOICE_GENERATION",
    "VISUAL_SELECTION",
    "VIDEO_ASSEMBLY",
    "AWAITING_APPROVAL",   # "is the video good?"
    "THUMBNAIL",
    "AWAITING_PUBLISH",    # "ready to publish?" - thumbnail choice + metadata
    "YOUTUBE_PUBLISH",
    "DONE",
]

# What a gate is reviewing: which state "regenerate" re-runs, and which
# PipelineState field holds the payload it hands back on approve/edit.
GATE_SOURCE = {
    "AWAITING_APPROVAL": ("VIDEO_ASSEMBLY", "video_output"),
    "AWAITING_PUBLISH": ("THUMBNAIL", "publish_metadata"),
}

# Uploading is opt-in: without a publish provider configured there is
# nothing to upload to, so a run ends at DONE with the finished file
# instead of halting on a gate it can never satisfy.
PUBLISH_STATES = ("AWAITING_PUBLISH", "YOUTUBE_PUBLISH")


def _next_state(current: str, config: dict) -> str:
    nxt = STATE_SEQUENCE[STATE_SEQUENCE.index(current) + 1]
    if nxt in PUBLISH_STATES and not config["ACTIVE_PROVIDERS"].get("publish"):
        return "DONE"
    return nxt

AGENT_FOR_STATE = {
    "TOPIC_SELECTION": topic_agent,
    "REFERENCE_ANALYSIS": reference_agent,
    "RESEARCHING": research_agent,
    "FACT_CHECKING": factcheck_agent,
    "SCRIPTING": script_agent,
    "VOICE_GENERATION": voice_agent,
    "VISUAL_SELECTION": visual_agent,
    "VIDEO_ASSEMBLY": assembler_agent,
    "THUMBNAIL": thumbnail,
    "YOUTUBE_PUBLISH": youtube_publish,
}

# Extra pauses only fired when REVIEW_MODE == "checkpoints". The final gate
# at AWAITING_APPROVAL always fires regardless of mode.
CHECKPOINT_STATES = {"RESEARCHING", "SCRIPTING"}


def _build_input(state: PipelineState, current: str) -> dict:
    if current == "TOPIC_SELECTION":
        return {
            "niche": state.niche,
            "preferences": state.preferences,
            "user_topic": state.user_topic,
        }
    if current == "REFERENCE_ANALYSIS":
        return {"urls": state.preferences.get("reference_urls", [])}
    if current == "RESEARCHING":
        return {"topic": state.topic, "reference_notes": state.reference_analysis}
    if current == "FACT_CHECKING":
        return {
            "research_summary": state.research["research_summary"],
            "sources": state.research["sources"],
        }
    if current == "SCRIPTING":
        return {
            "research_summary": state.research["research_summary"],
            "verified_claims": state.factcheck["verified_claims"],
            "target_length_minutes": state.target_length_minutes,
        }
    if current == "VOICE_GENERATION":
        return {
            "script_text": state.script["script_text"],
            "script_spoken": state.script.get("script_spoken"),
            "voice_profile_id": state.voice_profile_id,
            "voice_sample_path": state.voice_sample_path,
        }
    if current == "VISUAL_SELECTION":
        return {"scenes": state.script["scenes"]}
    if current == "VIDEO_ASSEMBLY":
        return {
            "audio_path": state.voice_output["audio_path"],
            "word_timestamps": state.voice_output.get("word_timestamps"),
            "scene_assets": state.visual_output["scene_assets"],
            "script_text": state.script["script_text"],
            "run_id": state.run_id,
        }
    if current == "THUMBNAIL":
        return {
            "topic": state.topic,
            "scenes": state.script["scenes"],
            "run_id": state.run_id,
        }
    if current == "YOUTUBE_PUBLISH":
        # Whatever the human left in publish_metadata at the gate is what
        # ships - the drafted values are only a starting point.
        return {
            "video_path": state.video_output["video_path"],
            **(state.publish_metadata or {}),
        }
    raise ValueError(f"No input builder for state {current}")


def _validate(current: str, output: dict) -> bool:
    if not isinstance(output, dict) or not output:
        return False
    checks = {
        "TOPIC_SELECTION": lambda o: bool(o.get("topics")),
        "REFERENCE_ANALYSIS": lambda o: all(o.get(k) for k in ("style_notes", "structure_notes", "angle_notes")),
        "RESEARCHING": lambda o: bool(o.get("research_summary")) and bool(o.get("sources")),
        "FACT_CHECKING": lambda o: isinstance(o.get("verified_claims"), list) and isinstance(o.get("flagged_claims"), list),
        "SCRIPTING": lambda o: bool(o.get("script_text")) and bool(o.get("scenes")),
        "VOICE_GENERATION": lambda o: bool(o.get("audio_path")) and os.path.exists(o["audio_path"]),
        "VISUAL_SELECTION": lambda o: bool(o.get("scene_assets")),
        "VIDEO_ASSEMBLY": lambda o: bool(o.get("video_path")),
        "THUMBNAIL": lambda o: bool(o.get("thumbnails")),
        "YOUTUBE_PUBLISH": lambda o: bool(o.get("video_url")),
    }
    return checks[current](output)


def _store_output(state: PipelineState, current: str, output: dict) -> None:
    if current == "TOPIC_SELECTION":
        # No approval gate at this stage in either review mode - auto-select
        # the first suggestion (or the user-provided topic, already the sole
        # entry in the list).
        state.topic = output["topics"][0]
    elif current == "REFERENCE_ANALYSIS":
        state.reference_analysis = output
    elif current == "RESEARCHING":
        state.research = output
    elif current == "FACT_CHECKING":
        state.factcheck = output
    elif current == "SCRIPTING":
        state.script = output
    elif current == "VOICE_GENERATION":
        state.voice_output = output
    elif current == "VISUAL_SELECTION":
        state.visual_output = output
    elif current == "VIDEO_ASSEMBLY":
        state.video_output = output
    elif current == "THUMBNAIL":
        state.thumbnails = output
    elif current == "YOUTUBE_PUBLISH":
        state.publish_output = output


class PipelineHalted(Exception):
    pass


class PipelineManager:
    def __init__(self, state: PipelineState, config: dict, approval_handler, runs_dir: str = "runs"):
        self.state = state
        self.config = config
        self.approval_handler = approval_handler
        self.runs_dir = runs_dir
        os.makedirs(runs_dir, exist_ok=True)
        # (checkpoint, payload) awaiting an external decision - only used by
        # step(), not by run(). Not persisted: step()-based callers (e.g. a
        # Streamlit session) keep the PipelineManager instance alive across
        # interactions rather than reconstructing it from JSON each time.
        self._pending = None

    def _state_path(self) -> str:
        return os.path.join(self.runs_dir, f"{self.state.run_id}.json")

    def _save(self) -> None:
        save_state(self.state, self._state_path())

    def _run_agent_with_retry(self, current: str):
        agent = AGENT_FOR_STATE[current]
        input_data = _build_input(self.state, current)

        result = agent.run(input_data, self.config)
        if result.get("success") and _validate(current, result.get("output")):
            return result["output"]

        self.state.log(current, "retried", detail=str(result.get("error")))
        if self.approval_handler:
            self.approval_handler.notify(f"{current}: agent failed validation, retrying once.")

        result = agent.run(input_data, self.config)
        if result.get("success") and _validate(current, result.get("output")):
            return result["output"]

        self.state.log(current, "error", detail=str(result.get("error")))
        self._save()
        raise PipelineHalted(
            f"Agent for {current} failed twice. Last error: {result.get('error')}. "
            f"State saved to {self._state_path()}"
        )

    def _gate_payload(self, checkpoint: str) -> dict:
        """What a gate shows the human.

        AWAITING_APPROVAL reviews the assembled video as-is. AWAITING_PUBLISH
        needs more than the thumbnails the previous state produced, so the
        publish agent drafts title/description/tags here - before the gate,
        so they can be edited at it rather than after.
        """
        if checkpoint == "AWAITING_PUBLISH":
            metadata = dict(self.state.publish_metadata or {})
            if not metadata.get("title"):
                metadata.update(youtube_publish.draft_metadata(self.state, self.config))
            thumbnails = (self.state.thumbnails or {}).get("thumbnails", [])
            metadata["thumbnails"] = thumbnails
            metadata.setdefault(
                "thumbnail_path", thumbnails[0]["path"] if thumbnails else ""
            )
            self.state.publish_metadata = metadata
            self._save()
            return metadata

        _, field = GATE_SOURCE[checkpoint]
        return getattr(self.state, field)

    def _handle_gate(self, checkpoint: str, payload: dict, on_regenerate) -> dict:
        while True:
            choice = self.approval_handler.request_approval(checkpoint, payload)
            self.state.log(checkpoint, choice)
            if choice == "approve":
                return payload
            if choice == "edit":
                payload = self.approval_handler.request_edit(checkpoint, payload)
                return payload
            if choice == "regenerate":
                payload = on_regenerate()

    def run(self) -> PipelineState:
        while self.state.current_state != "DONE":
            current = self.state.current_state

            if current == "IDLE":
                self.state.current_state = WORK_STATES[0]
                self.state.log(current, "advanced")
                self._save()
                continue

            if current in WORK_STATES:
                output = self._run_agent_with_retry(current)
                _store_output(self.state, current, output)
                self.state.log(current, "advanced")
                self._save()

                if self.config.get("REVIEW_MODE") == "checkpoints" and current in CHECKPOINT_STATES:
                    def regenerate(c=current):
                        out = self._run_agent_with_retry(c)
                        _store_output(self.state, c, out)
                        self._save()
                        return out

                    _store_output(self.state, current, self._handle_gate(current, output, regenerate))
                    self._save()

                self.state.current_state = _next_state(current, self.config)
                self._save()
                continue

            if current in GATE_SOURCE:
                source_state, field = GATE_SOURCE[current]
                payload = self._gate_payload(current)

                def regenerate(src=source_state, cp=current):
                    out = self._run_agent_with_retry(src)
                    _store_output(self.state, src, out)
                    self._save()
                    return self._gate_payload(cp)

                setattr(self.state, field, self._handle_gate(current, payload, regenerate))
                self.state.current_state = _next_state(current, self.config)
                self.state.log(current, "advanced")
                self._save()
                continue

        return self.state

    # -- step(): a non-blocking alternative to run(), for callers that can't
    # block on input() or long-polling (e.g. a Streamlit app, which reruns
    # its whole script per interaction rather than staying inside a loop).
    # Ignores self.approval_handler entirely - the caller supplies decisions
    # directly as arguments instead.

    def step(self, decision: str | None = None, edited_payload: dict | None = None) -> dict:
        """Advances the pipeline by exactly one unit of work, or - when a
        gate is pending - either reports it (decision=None) or resolves it
        (decision="approve"|"edit"|"regenerate"). Returns a dict describing
        what happened: {"type": "advanced"|"awaiting_approval"|"done", ...}.
        """
        if self._pending is not None:
            checkpoint, payload = self._pending
            if decision is None:
                return {"type": "awaiting_approval", "checkpoint": checkpoint, "payload": payload}
            return self._resolve_pending(checkpoint, payload, decision, edited_payload)

        current = self.state.current_state

        if current == "DONE":
            result = {"type": "done", "video_path": self.state.video_output["video_path"]}
            if self.state.publish_output:
                result["video_url"] = self.state.publish_output.get("video_url")
            return result

        if current == "IDLE":
            self.state.current_state = WORK_STATES[0]
            self.state.log(current, "advanced")
            self._save()
            return {"type": "advanced", "state": self.state.current_state}

        if current in WORK_STATES:
            output = self._run_agent_with_retry(current)
            _store_output(self.state, current, output)
            self.state.log(current, "advanced")
            self._save()

            if self.config.get("REVIEW_MODE") == "checkpoints" and current in CHECKPOINT_STATES:
                self._pending = (current, output)
                return {"type": "awaiting_approval", "checkpoint": current, "payload": output}

            self.state.current_state = _next_state(current, self.config)
            self._save()
            return {"type": "advanced", "state": self.state.current_state}

        if current in GATE_SOURCE:
            payload = self._gate_payload(current)
            self._pending = (current, payload)
            return {"type": "awaiting_approval", "checkpoint": current, "payload": payload}

        raise ValueError(f"step() doesn't know how to handle state {current!r}")

    def _resolve_pending(self, checkpoint: str, payload: dict, decision: str, edited_payload: dict | None) -> dict:
        self.state.log(checkpoint, decision)
        # Mid-run checkpoints gate the state they just ran; the dedicated
        # gates in GATE_SOURCE gate an earlier state and store elsewhere.
        target_state, field = GATE_SOURCE.get(checkpoint, (checkpoint, None))

        if decision == "regenerate":
            output = self._run_agent_with_retry(target_state)
            _store_output(self.state, target_state, output)
            self._save()
            payload = self._gate_payload(checkpoint) if field else output
            self._pending = (checkpoint, payload)
            return {"type": "awaiting_approval", "checkpoint": checkpoint, "payload": payload}

        if decision == "edit":
            updated = dict(payload)
            if edited_payload:
                updated.update(edited_payload)
            if field:
                setattr(self.state, field, updated)
            else:
                _store_output(self.state, target_state, updated)
        elif decision == "approve":
            pass
        else:
            raise ValueError(f"Unknown decision {decision!r}")

        self._pending = None
        self.state.current_state = _next_state(checkpoint, self.config)
        self.state.log(checkpoint, "advanced")
        self._save()
        return {"type": "advanced", "state": self.state.current_state}
