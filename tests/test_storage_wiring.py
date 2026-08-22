"""Where a run actually writes.

paths.py was built to put everything under one platform data directory,
split by lifecycle, and it was tested thoroughly - in isolation. The
pipeline never called it. The manager defaulted to a relative "runs"
directory and nine agents and providers hardcoded their own "runs/..."
constant at import time, so a real run still scattered its output across
the working directory. `studio.py ls` listed nothing after a successful
run, `clean --orphans` had nothing to reason about, and launching from a
different directory quietly started a second empty library.

These tests assert the wiring rather than the layout: that the pieces with
no run id in their signature still land inside the project that is running.
"""

import os

import pytest

import paths


@pytest.fixture(autouse=True)
def _isolated(studio_home):
    """Every test here runs against a throwaway SANTA_STUDIO_HOME."""
    paths.clear_active_run()
    yield
    paths.clear_active_run()


# ---------------------------------------------------------------------------
# Run scoping
# ---------------------------------------------------------------------------


def test_providers_write_into_the_active_run(studio_home):
    paths.set_active_run("abcd1234-5678", "Why the sky is blue")

    voice = paths.scoped_dir("voice")

    assert voice.is_relative_to(paths.projects_dir())
    assert "why-the-sky-is-blue" in str(voice)
    assert voice.name == "voice"


def test_no_active_run_falls_back_to_scratch(studio_home):
    voice = paths.scoped_dir("voice")

    assert voice.is_relative_to(paths.tmp_dir())
    assert not voice.is_relative_to(paths.projects_dir())


def test_the_active_run_does_not_leak_between_threads(studio_home):
    """The web app drives each run on its own thread; two concurrent runs
    must not write into each other's folder."""
    import threading

    paths.set_active_run("aaaaaaaa-1111", "First topic")
    seen = {}

    def other_thread():
        paths.set_active_run("bbbbbbbb-2222", "Second topic")
        seen["theirs"] = str(paths.scoped_dir("voice"))

    thread = threading.Thread(target=other_thread)
    thread.start()
    thread.join()

    seen["ours"] = str(paths.scoped_dir("voice"))
    assert "first-topic" in seen["ours"]
    assert "second-topic" in seen["theirs"]


def test_scoped_dir_rejects_a_directory_it_does_not_own():
    with pytest.raises(ValueError):
        paths.scoped_dir("cache")


# ---------------------------------------------------------------------------
# The manager
# ---------------------------------------------------------------------------


def test_manager_stores_state_in_the_project_folder(studio_home):
    from manager import PipelineManager
    from state import PipelineState

    state = PipelineState(niche="science", user_topic="Tipu Sultan rockets")
    state.topic = "Tipu Sultan rockets"
    mgr = PipelineManager(state, {"ACTIVE_PROVIDERS": {}}, approval_handler=None)

    path = mgr._state_path()

    assert path.endswith("project.json")
    assert str(paths.projects_dir()) in path
    assert "tipu-sultan-rockets" in path


def test_manager_claims_the_run_so_providers_find_it(studio_home):
    from manager import PipelineManager
    from state import PipelineState

    state = PipelineState(niche="science", user_topic="A topic")
    state.topic = "A topic"
    mgr = PipelineManager(state, {"ACTIVE_PROVIDERS": {}}, approval_handler=None)
    mgr._claim_run()

    assert paths.active_run()[0] == state.run_id
    assert paths.scoped_dir("voice").is_relative_to(paths.projects_dir())


def test_an_explicit_runs_dir_is_still_honoured(studio_home, tmp_path):
    """Tests and older installs pass a directory; that must keep working and
    must not claim the run globally."""
    from manager import PipelineManager
    from state import PipelineState

    elsewhere = tmp_path / "somewhere"
    state = PipelineState(niche="science")
    mgr = PipelineManager(state, {"ACTIVE_PROVIDERS": {}}, None, runs_dir=str(elsewhere))
    mgr._claim_run()

    assert mgr._state_path().startswith(str(elsewhere))
    assert paths.active_run()[0] == ""


# ---------------------------------------------------------------------------
# Nothing writes into the checkout
# ---------------------------------------------------------------------------


def test_no_module_hardcodes_a_relative_runs_directory():
    """This is the regression that matters: a constant like
    ASSET_DIR = "runs/assets" evaluated at import time is relative to
    whatever directory the tool was launched from."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    offenders = []
    for directory in ("agents", "providers", "render", "clips"):
        for source in (root / directory).rglob("*.py"):
            text = source.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if '"runs/' in line or "'runs/" in line:
                    offenders.append(f"{source.relative_to(root)}:{number}")
    for name in ("manager.py", "timeline_builder.py", "graphics.py"):
        text = (root / name).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if '"runs/' in line or "'runs/" in line:
                offenders.append(f"{name}:{number}")

    assert not offenders, "hardcoded runs/ paths: " + ", ".join(offenders)


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_the_oauth_token_is_not_in_the_disposable_cache(studio_home, monkeypatch):
    """cache/ is documented as safe to delete; a token there means
    reclaiming disk signs you out of YouTube."""
    monkeypatch.delenv("YOUTUBE_TOKEN_FILE", raising=False)
    from providers.publish.youtube_provider import _token_file

    token = _token_file()

    assert str(paths.credentials_dir()) in token
    assert str(paths.cache_dir()) not in token


def test_a_token_written_by_an_older_build_is_moved_across(studio_home, monkeypatch):
    monkeypatch.delenv("YOUTUBE_TOKEN_FILE", raising=False)
    from providers.publish.youtube_provider import _migrate_legacy_token, _token_file

    legacy = paths.home() / "cache" / "youtube_token.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text('{"token": "old"}')

    target = _token_file()
    _migrate_legacy_token(target)

    assert os.path.exists(target)
    assert not legacy.exists()
