"""A live feed of what the pipeline is actually doing, one channel per run.

The room draws a person at a desk for every state in `manager.STATE_SEQUENCE`
and shows their work on their laptop. For that screen to be worth focusing on,
it has to carry what the agent is really doing right now - not a plausible
animation of it. This module is the channel that carries it.

Two halves:

  - Agents call `report()` while they work. They do not know a run id; the
    manager binds one for the duration of the call, so an agent stays a
    function of its input and its output, exactly as the rest of the pipeline
    assumes.
  - The web layer calls `subscribe()` and streams what arrives.

The wire vocabulary is the one `room/src/net/events.js` already defines, so a
published event needs no translation before it reaches the scene.

Nothing here is persisted. A live feed that survives a restart would be a log,
and the run's own `history` already is one; this is for watching, and a run's
durable record is on disk either way.
"""

from __future__ import annotations

import itertools
import queue
import threading
import time

# Enough to replay the interesting part of a run to a browser that connects
# late, and small enough that an abandoned run cannot grow without bound.
MAX_HISTORY = 400

# Which desk in the room a backend state belongs to. The room keeps the same
# mapping in `room/src/sim/agents.js`; both sides are derived from
# `manager.AGENT_FOR_STATE`, and `tests/test_runlog.py` asserts they agree.
AGENT_FOR_STATE = {
    "TOPIC_SELECTION": "topic",
    "REFERENCE_ANALYSIS": "reference",
    "RESEARCHING": "research",
    "FACT_CHECKING": "factcheck",
    "SCRIPTING": "script",
    "VOICE_GENERATION": "voice",
    "VISUAL_SELECTION": "visual",
    "VIDEO_ASSEMBLY": "assembler",
    "SHORTS_EXTRACTION": "shorts",
    "THUMBNAIL": "thumbnail",
    "YOUTUBE_PUBLISH": "publish",
}

_lock = threading.Lock()
_history: dict[str, list] = {}
_subscribers: dict[str, list[queue.Queue]] = {}
_counter = itertools.count(1)

# The run and state whose agent is currently executing, per thread. A pipeline
# is driven on its own thread, so two runs in one process do not collide.
_active = threading.local()


def agent_for(state: str) -> str | None:
    return AGENT_FOR_STATE.get(state)


# ---- Publishing ------------------------------------------------------------


def publish(run_id: str, event: dict) -> dict:
    """Sends one event to every listener on this run, and remembers it."""
    if not run_id:
        return event
    stamped = dict(event)
    stamped["seq"] = next(_counter)
    stamped["ts"] = time.time()

    with _lock:
        entries = _history.setdefault(run_id, [])
        entries.append(stamped)
        if len(entries) > MAX_HISTORY:
            # Keep the tail. The head of a long run is the part a late viewer
            # is least likely to care about.
            del entries[: len(entries) - MAX_HISTORY]
        listeners = list(_subscribers.get(run_id, ()))

    for listener in listeners:
        try:
            listener.put_nowait(stamped)
        except queue.Full:
            # A listener that cannot keep up is a browser that has gone away
            # or stalled. Dropping its events is correct: the run must not
            # slow down for a spectator.
            pass
    return stamped


def stage(run_id: str, state: str) -> None:
    publish(run_id, {"type": "stage", "state": state})


def assign(run_id: str, state: str, email: dict | None = None) -> None:
    agent = agent_for(state)
    if agent:
        publish(run_id, {"type": "assign", "agent": agent, "state": state, "email": email})


def start(run_id: str, state: str) -> None:
    agent = agent_for(state)
    if agent:
        publish(run_id, {"type": "start", "agent": agent, "state": state})


def finish(run_id: str, state: str) -> None:
    agent = agent_for(state)
    if agent:
        publish(run_id, {"type": "finish", "agent": agent, "state": state})


def failed(run_id: str, state: str, text: str) -> None:
    agent = agent_for(state)
    publish(run_id, {"type": "error", "agent": agent, "state": state, "text": text})


def gate(run_id: str, checkpoint: str, payload: dict) -> None:
    publish(run_id, {"type": "gate", "checkpoint": checkpoint, "gate": payload})


def close_gate(run_id: str) -> None:
    publish(run_id, {"type": "close"})


def done(run_id: str, video_path: str = "") -> None:
    publish(run_id, {"type": "done", "video_path": video_path})


# ---- What an agent calls ---------------------------------------------------


class bind:
    """Marks the run and state an agent is executing under.

    Used as a context manager around the agent call, so `report()` inside the
    agent needs no arguments it would otherwise have to thread through every
    helper it calls.
    """

    def __init__(self, run_id: str, state: str):
        self.run_id = run_id
        self.state = state
        self._previous = None

    def __enter__(self):
        self._previous = getattr(_active, "current", None)
        _active.current = (self.run_id, self.state)
        return self

    def __exit__(self, *exc):
        _active.current = self._previous
        return False


def current() -> tuple[str, str] | None:
    return getattr(_active, "current", None)


def report(text: str, progress: float | None = None) -> None:
    """One line of an agent's real work, for that agent's laptop screen.

    A no-op when nothing is bound, which is what makes it safe to call from
    an agent under unit test, from the CLI, and from a Telegram run alike.
    """
    active = current()
    if not active:
        return
    run_id, state = active
    agent = agent_for(state)
    if not agent:
        return
    event = {"type": "line", "agent": agent, "state": state, "text": str(text)}
    if progress is not None:
        event["progress"] = max(0.0, min(1.0, float(progress)))
    publish(run_id, event)


# ---- Listening -------------------------------------------------------------


def history(run_id: str) -> list:
    with _lock:
        return list(_history.get(run_id, ()))


def subscribe(run_id: str, maxsize: int = 256) -> queue.Queue:
    listener: queue.Queue = queue.Queue(maxsize=maxsize)
    with _lock:
        _subscribers.setdefault(run_id, []).append(listener)
    return listener


def unsubscribe(run_id: str, listener: queue.Queue) -> None:
    with _lock:
        listeners = _subscribers.get(run_id)
        if not listeners:
            return
        try:
            listeners.remove(listener)
        except ValueError:
            pass
        if not listeners:
            _subscribers.pop(run_id, None)


def forget(run_id: str) -> None:
    """Drops a finished run's buffer once nothing is watching it."""
    with _lock:
        if not _subscribers.get(run_id):
            _history.pop(run_id, None)
