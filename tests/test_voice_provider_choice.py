"""Which voice a run is narrated in, and why choosing a profile has to matter.

gTTS cannot clone. It was the hardcoded default, so picking a voice profile in
the UI changed nothing audible: the profile was resolved, handed over, and
ignored, and every run came out in the same stock voice.
"""

import importlib

import config


def _reload(monkeypatch, env=None, has_chatterbox=False):
    monkeypatch.delenv("VOICE_PROVIDER", raising=False)
    if env:
        monkeypatch.setenv("VOICE_PROVIDER", env)
    reloaded = importlib.reload(config)
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: object() if (name == "chatterbox" and has_chatterbox) else None,
    )
    return reloaded


def test_a_cloning_provider_is_preferred_when_one_is_installed(monkeypatch):
    cfg = _reload(monkeypatch, has_chatterbox=True)
    assert cfg.build_config()["ACTIVE_PROVIDERS"]["voice"] == "chatterbox"


def test_a_machine_without_one_still_runs(monkeypatch):
    cfg = _reload(monkeypatch, has_chatterbox=False)
    assert cfg.build_config()["ACTIVE_PROVIDERS"]["voice"] == "gtts"


def test_an_explicit_choice_wins(monkeypatch):
    """XTTS clones too, but its weights forbid commercial use - so it is
    available to anyone who asks for it and never chosen automatically."""
    cfg = _reload(monkeypatch, env="xtts", has_chatterbox=True)
    assert cfg.build_config()["ACTIVE_PROVIDERS"]["voice"] == "xtts"


def test_xtts_is_never_selected_on_its_own(monkeypatch):
    """Constraint 2: only commercially safe licences by default."""
    cfg = _reload(monkeypatch, has_chatterbox=False)
    assert cfg.build_config()["ACTIVE_PROVIDERS"]["voice"] != "xtts"


def teardown_module():
    importlib.reload(config)
