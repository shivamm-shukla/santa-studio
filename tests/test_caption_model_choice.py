"""Which Whisper gets loaded, and why it is configurable.

Captions are the one part of the output a viewer reads word by word, so the
smallest model is a poor default - but it is the right one on a machine that
cannot spare the compute, which is why this is an environment variable rather
than a constant.
"""

import importlib

import providers.caption.whisper_provider as whisper_provider


def test_the_default_is_not_the_smallest_model(monkeypatch):
    monkeypatch.delenv("WHISPER_MODEL", raising=False)
    reloaded = importlib.reload(whisper_provider)
    assert reloaded.MODEL_SIZE == "medium"


def test_a_smaller_model_can_be_asked_for(monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "base")
    reloaded = importlib.reload(whisper_provider)
    assert reloaded.MODEL_SIZE == "base"


def test_an_empty_setting_falls_back_rather_than_loading_nothing(monkeypatch):
    monkeypatch.setenv("WHISPER_MODEL", "   ")
    reloaded = importlib.reload(whisper_provider)
    assert reloaded.MODEL_SIZE == "medium"


def teardown_module():
    """Leave the module as the rest of the suite expects to find it."""
    importlib.reload(whisper_provider)
