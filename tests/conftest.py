"""Shared fixtures.

Every test runs against a throwaway SANTA_STUDIO_HOME. This used to be
opt-in - a test had to request the `studio_home` fixture - which meant any
test that reached storage without asking for it wrote into the developer's
real library. Now it is autouse, so the isolation the docstring always
claimed is actually true.

The same applies to the relevance check on generated visuals. It is on
whenever a Gemini key is in the environment, and something in the suite
imports `config`, which loads `.env` for every test that runs after it - so a
few provider tests started making live calls against the owner's quota and
failing on whatever came back. It is switched off here and turned on by the
tests that mean to exercise it.
"""

import importlib

import pytest


@pytest.fixture(autouse=True)
def no_live_relevance_calls(monkeypatch):
    monkeypatch.setenv("VISUAL_RELEVANCE_CHECK", "false")


@pytest.fixture(autouse=True)
def studio_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import paths

    importlib.reload(paths)
    paths.ensure_tree()
    paths.clear_active_run()
    yield tmp_path.resolve()
    paths.clear_active_run()
