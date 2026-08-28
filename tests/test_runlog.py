"""The live activity feed the room draws its desks from.

The room is a picture of the state machine, so the thing worth asserting is
that the two agree: every state a run passes through has a desk to appear on,
and a real `PipelineManager` actually publishes work for it.
"""

import json
import re
import pathlib

import pytest

import manager as manager_module
import runlog
from manager import PipelineManager
from state import PipelineState

ROOM_AGENTS_JS = pathlib.Path(__file__).resolve().parents[1] / "room" / "src" / "agents.js"


@pytest.fixture(autouse=True)
def clean_bus():
    runlog._history.clear()
    runlog._subscribers.clear()
    yield
    runlog._history.clear()
    runlog._subscribers.clear()


def test_every_agent_state_has_a_desk():
    """A state with no desk would run with nothing on screen to show it."""
    assert set(runlog.AGENT_FOR_STATE) == set(manager_module.AGENT_FOR_STATE)


def test_the_room_and_the_backend_name_the_same_desks():
    """Both sides map backend state -> desk id, and they must not drift.

    The room owns its copy so the scene can be developed without a server;
    that is exactly why it needs a test holding it to the backend's.
    """
    source = ROOM_AGENTS_JS.read_text()
    pairs = dict(re.findall(r'id:\s*"(\w+)",[^\n]*?state:\s*"(\w+)"', source))
    room_map = {state: agent for agent, state in pairs.items()}
    assert room_map == runlog.AGENT_FOR_STATE


def test_report_is_a_no_op_when_nothing_is_bound():
    """Agents call report() under unit test and from the CLI too."""
    runlog.report("this goes nowhere")
    assert runlog.history("anything") == []


def test_report_reaches_the_bound_run_only():
    with runlog.bind("run-a", "RESEARCHING"):
        runlog.report("found 4 sources", progress=0.5)

    events = runlog.history("run-a")
    assert [e["type"] for e in events] == ["line"]
    assert events[0]["agent"] == "research"
    assert events[0]["text"] == "found 4 sources"
    assert events[0]["progress"] == 0.5
    assert runlog.history("run-b") == []


def test_a_subscriber_receives_what_is_published_after_it_joined():
    listener = runlog.subscribe("run-c")
    runlog.stage("run-c", "SCRIPTING")
    assert listener.get_nowait()["state"] == "SCRIPTING"
    runlog.unsubscribe("run-c", listener)


def test_history_is_bounded():
    for i in range(runlog.MAX_HISTORY + 50):
        runlog.publish("run-d", {"type": "line", "text": str(i)})
    kept = runlog.history("run-d")
    assert len(kept) == runlog.MAX_HISTORY
    # The tail is what survives - a late viewer wants the recent work.
    assert kept[-1]["text"] == str(runlog.MAX_HISTORY + 49)


def test_a_real_run_broadcasts_each_agent_starting_and_finishing(monkeypatch, tmp_path):
    """Drives PipelineManager itself rather than calling runlog directly.

    A capability is not done when its module works, it is done when a run
    produces it - so this asserts against the orchestrator.
    """
    recorded = []

    class StubAgent:
        def __init__(self, output):
            self.output = output

        def run(self, input_data, config):
            runlog.report("working on it", progress=0.5)
            return {"success": True, "output": self.output, "error": None}

    monkeypatch.setattr(manager_module, "AGENT_FOR_STATE", {
        "TOPIC_SELECTION": StubAgent({"topics": ["A topic"]}),
    })
    monkeypatch.setattr(manager_module, "WORK_STATES", ["TOPIC_SELECTION"])
    monkeypatch.setattr(manager_module, "STATE_SEQUENCE", ["IDLE", "TOPIC_SELECTION", "DONE"])
    monkeypatch.setattr(manager_module, "_validate", lambda state, output: True)

    state = PipelineState(niche="test")
    mgr = PipelineManager(state, {"REVIEW_MODE": "autonomous"}, approval_handler=None,
                          runs_dir=str(tmp_path))
    listener = runlog.subscribe(state.run_id)

    mgr.step()   # IDLE -> TOPIC_SELECTION
    mgr.step()   # runs the agent

    while not listener.empty():
        recorded.append(listener.get_nowait())

    kinds = [e["type"] for e in recorded]
    assert "assign" in kinds, "the room never sees the task land on the desk"
    assert "start" in kinds
    assert "line" in kinds, "the agent's own work never reached its screen"
    assert "finish" in kinds

    assign = next(e for e in recorded if e["type"] == "assign")
    assert assign["agent"] == "topic"
    assert assign["email"]["from"] == "Manager"
    assert assign["email"]["subject"]

    line = next(e for e in recorded if e["type"] == "line")
    assert line["agent"] == "topic"
    assert line["text"] == "working on it"

    runlog.unsubscribe(state.run_id, listener)


def test_events_are_json_serialisable():
    """They go out over SSE, so anything unserialisable breaks the stream."""
    with runlog.bind("run-e", "VIDEO_ASSEMBLY"):
        runlog.report("rendering", progress=0.4)
    runlog.gate("run-e", "AWAITING_APPROVAL", {"title": "ok", "options": []})
    for event in runlog.history("run-e"):
        json.dumps(event)
