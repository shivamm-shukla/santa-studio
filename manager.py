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
    topic_agent,
    visual_agent,
    voice_agent,
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
]

STATE_SEQUENCE = ["IDLE"] + WORK_STATES + ["AWAITING_APPROVAL", "DONE"]

AGENT_FOR_STATE = {
    "TOPIC_SELECTION": topic_agent,
    "REFERENCE_ANALYSIS": reference_agent,
    "RESEARCHING": research_agent,
    "FACT_CHECKING": factcheck_agent,
    "SCRIPTING": script_agent,
    "VOICE_GENERATION": voice_agent,
    "VISUAL_SELECTION": visual_agent,
    "VIDEO_ASSEMBLY": assembler_agent,
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
        }
    if current == "VOICE_GENERATION":
        return {
            "script_text": state.script["script_text"],
            "voice_sample_path": state.voice_sample_path,
        }
    if current == "VISUAL_SELECTION":
        return {"scenes": state.script["scenes"]}
    if current == "VIDEO_ASSEMBLY":
        return {
            "audio_path": state.voice_output["audio_path"],
            "scene_assets": state.visual_output["scene_assets"],
            "script_text": state.script["script_text"],
            "run_id": state.run_id,
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
        "VOICE_GENERATION": lambda o: bool(o.get("audio_path")),
        "VISUAL_SELECTION": lambda o: bool(o.get("scene_assets")),
        "VIDEO_ASSEMBLY": lambda o: bool(o.get("video_path")),
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


class PipelineHalted(Exception):
    pass


class PipelineManager:
    def __init__(self, state: PipelineState, config: dict, approval_handler, runs_dir: str = "runs"):
        self.state = state
        self.config = config
        self.approval_handler = approval_handler
        self.runs_dir = runs_dir
        os.makedirs(runs_dir, exist_ok=True)

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

                idx = STATE_SEQUENCE.index(current)
                self.state.current_state = STATE_SEQUENCE[idx + 1]
                self._save()
                continue

            if current == "AWAITING_APPROVAL":
                payload = self.state.video_output

                def regenerate():
                    out = self._run_agent_with_retry("VIDEO_ASSEMBLY")
                    _store_output(self.state, "VIDEO_ASSEMBLY", out)
                    self._save()
                    return out

                _store_output(self.state, "VIDEO_ASSEMBLY", self._handle_gate(current, payload, regenerate))
                self.state.current_state = "DONE"
                self.state.log(current, "advanced")
                self._save()
                continue

        return self.state
