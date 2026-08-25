"""Work finished inside a stage, kept so a retry does not repeat it.

A stage is the unit the pipeline saves at, and some stages are long. The
research swarm makes three parallel LLM calls and a set of grounding requests;
when its output fails validation the manager runs the whole agent again, and
every one of those calls is spent a second time on a free tier that is counted
in requests per day. The same is true when a parked run resumes.

So a stage can write down the parts of itself that succeeded. This is
deliberately small: a key, a JSON value, and a directory that belongs to the
run, cleared when the run finishes. It is not a cache - two different runs
never share an entry, and nothing here survives the project it was written
under.

Silent about failure on purpose. A checkpoint that cannot be written is a
missed saving, not a reason to lose a stage.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import paths
import runlog

DIRECTORY = "checkpoints"


def _run_id() -> str:
    bound = runlog.current()
    return bound[0] if bound else ""


def _directory(create: bool = False) -> Path | None:
    """Where this run's checkpoints live, or None when no run is bound.

    No run bound means a unit test or a one-off script, and writing a
    checkpoint into somebody's project from there would be worse than not
    saving one at all.
    """
    run_id = _run_id()
    if not run_id:
        return None
    try:
        directory = paths.project_dir(run_id, create=create) / DIRECTORY
        if create:
            directory.mkdir(parents=True, exist_ok=True)
        return directory
    except Exception:
        return None


def _path(directory: Path, key: str) -> Path:
    """A filename that cannot collide and cannot escape the directory."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]
    return directory / f"{digest}.json"


def load(key: str):
    """What was saved under `key` in this run, or None."""
    directory = _directory()
    if directory is None:
        return None
    try:
        return json.loads(_path(directory, key).read_text())["value"]
    except Exception:
        return None


def save(key: str, value) -> None:
    """Remembers `value` for the rest of this run."""
    directory = _directory(create=True)
    if directory is None:
        return
    try:
        _path(directory, key).write_text(json.dumps({"key": key, "value": value}))
    except Exception:
        pass


def clear() -> None:
    """Throws away this run's checkpoints, once they cannot help any more."""
    directory = _directory()
    if directory is None:
        return
    shutil.rmtree(directory, ignore_errors=True)
