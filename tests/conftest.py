"""Shared fixtures.

Every test that touches storage runs against a throwaway SANTA_STUDIO_HOME, so
a test run can never write into the real library.
"""

import importlib

import pytest


@pytest.fixture
def studio_home(tmp_path, monkeypatch):
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import paths

    importlib.reload(paths)
    paths.ensure_tree()
    return tmp_path.resolve()
