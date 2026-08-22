"""The four frontends, which had no tests at all.

All four listed runs by globbing "runs/*.json" for themselves. When the
pipeline moved to the storage layout every one of them kept looking at a
directory nothing writes to any more, so the dashboard, /runs in the bot,
the CLI's resume prompt and the Streamlit picker would all have shown an
empty list. They share one implementation now, and this is what holds it
in place.
"""

import pytest

import paths
from state import PipelineState, find_run, save_state, saved_runs


def _write_run(topic, current_state="SCRIPTING", niche="science"):
    state = PipelineState(niche=niche, user_topic=topic)
    state.topic = topic
    state.current_state = current_state
    save_state(state, str(paths.state_file(state.run_id, topic)))
    return state


# ---------------------------------------------------------------------------
# The shared listing
# ---------------------------------------------------------------------------


def test_saved_runs_finds_what_the_pipeline_wrote(studio_home):
    _write_run("Why the sky is blue")
    _write_run("Tipu Sultan rockets")

    found = saved_runs()

    topics = {d["topic"] for d in found}
    assert topics == {"Why the sky is blue", "Tipu Sultan rockets"}
    assert all(d["_path"].endswith("project.json") for d in found)


def test_unfinished_only_excludes_completed_runs(studio_home):
    _write_run("Finished one", current_state="DONE")
    _write_run("Still going", current_state="VOICE_GENERATION")

    assert [d["topic"] for d in saved_runs(unfinished_only=True)] == ["Still going"]
    assert len(saved_runs()) == 2


def test_find_run_accepts_an_id_fragment(studio_home):
    state = _write_run("Some topic")

    assert find_run(state.run_id) is not None
    assert find_run(state.run_id[:8]) is not None
    assert find_run("nosuchrun") is None


def test_a_corrupt_project_file_is_skipped_not_fatal(studio_home):
    _write_run("Good run")
    broken = paths.projects_dir() / "2026-01-01_broken_ffffffff"
    broken.mkdir(parents=True)
    (broken / "project.json").write_text("{ not json")

    assert [d["topic"] for d in saved_runs()] == ["Good run"]


# ---------------------------------------------------------------------------
# The web app
# ---------------------------------------------------------------------------


@pytest.fixture
def client(studio_home):
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    import importlib

    import web.server

    importlib.reload(web.server)
    return fastapi_testclient.TestClient(web.server.app)


def test_dashboard_lists_runs_from_the_library(client, studio_home):
    _write_run("Why the sky is blue")

    response = client.get("/")

    assert response.status_code == 200
    assert "Why the sky is blue" in response.text or "science" in response.text


def test_pages_render(client):
    assert client.get("/").status_code == 200
    assert client.get("/voice-studio").status_code == 200


def test_unknown_run_is_a_404_not_a_crash(client):
    assert client.get("/api/runs/deadbeef/status").status_code == 404
    assert client.post("/api/runs/deadbeef/resume").status_code == 404


def test_status_of_a_finished_run_survives_a_restart(client, studio_home):
    """RUNS lives in process memory; a restart must not orphan the page."""
    state = _write_run("Done already", current_state="DONE")

    body = client.get(f"/api/runs/{state.run_id}/status").json()

    assert body["type"] == "done"


def test_polling_status_does_not_restart_a_run(client, studio_home):
    """A GET that resumes a pipeline makes a run impossible to stop."""
    import web.server

    state = _write_run("In progress", current_state="RESEARCHING")

    body = client.get(f"/api/runs/{state.run_id}/status").json()

    assert body["type"] == "stalled"
    assert state.run_id not in web.server.RUNS


# ---------------------------------------------------------------------------
# Run settings survive a resume
# ---------------------------------------------------------------------------


def test_resume_keeps_the_review_mode_the_run_started_with(studio_home):
    from web.server import _config_for

    state = PipelineState(niche="x", preferences={"review_mode": "checkpoints"})

    assert _config_for(state)["REVIEW_MODE"] == "checkpoints"


def test_resume_keeps_the_voice_fallback(studio_home):
    """A run started without a voice profile must not come back pointed at a
    cloning provider with nothing to clone from."""
    from web.server import _config_for

    state = PipelineState(niche="x", preferences={"voice_provider": "gtts"})

    assert _config_for(state)["ACTIVE_PROVIDERS"]["voice"] == "gtts"


def test_creating_a_run_records_its_settings(client, studio_home):
    response = client.post("/api/runs", json={
        "niche": "science",
        "user_topic": "Why the sky is blue",
        "review_mode": "checkpoints",
    })

    assert response.status_code == 200
    run_id = response.json()["run_id"]

    import web.server

    preferences = web.server.RUNS[run_id].state.preferences
    assert preferences["review_mode"] == "checkpoints"
    assert preferences["voice_provider"] == "gtts"
