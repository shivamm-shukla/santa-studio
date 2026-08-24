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


# ---------------------------------------------------------------------------
# Whether the chosen model will fit on the disk
# ---------------------------------------------------------------------------

import os
from collections import namedtuple

_Usage = namedtuple("_Usage", "total used free")


def _disk(monkeypatch, free_bytes):
    monkeypatch.setattr(
        whisper_provider.shutil, "disk_usage", lambda path: _Usage(0, 0, free_bytes)
    )


def _cached(monkeypatch, *names):
    monkeypatch.setattr(whisper_provider, "_already_here", lambda name: name in names)


def test_a_model_already_on_disk_is_used_whatever_the_free_space(monkeypatch):
    _cached(monkeypatch, "medium")
    _disk(monkeypatch, 10_000_000)

    assert whisper_provider._affordable_model("medium") == "medium"


def test_a_roomy_disk_gets_the_model_that_was_asked_for(monkeypatch):
    _cached(monkeypatch)
    _disk(monkeypatch, 50_000_000_000)

    assert whisper_provider._affordable_model("medium") == "medium"


def test_a_full_disk_steps_down_rather_than_filling_itself(monkeypatch):
    """The default is medium, and downloading it on a machine with a couple of
    gigabytes free finishes by filling the disk - mid-run, with a render to
    come."""
    _cached(monkeypatch)
    _disk(monkeypatch, 2_800_000_000)

    chosen = whisper_provider._affordable_model("medium")
    assert chosen != "medium"
    assert chosen in whisper_provider.LADDER


def test_stepping_down_prefers_a_model_that_is_already_here(monkeypatch):
    _cached(monkeypatch, "base")
    _disk(monkeypatch, 2_800_000_000)

    assert whisper_provider._affordable_model("medium") == "base"


def test_a_truncated_download_does_not_count_as_being_here(tmp_path, monkeypatch):
    """Whisper re-fetches those in full, which is the download we need room for."""
    monkeypatch.setattr(whisper_provider, "_cache_dir", lambda: str(tmp_path))
    (tmp_path / "medium.pt").write_bytes(b"0" * 1024)

    assert whisper_provider._already_here("medium") is False


def test_a_whole_file_does_count(tmp_path, monkeypatch):
    monkeypatch.setattr(whisper_provider, "_cache_dir", lambda: str(tmp_path))
    (tmp_path / "base.pt").write_bytes(b"0" * whisper_provider.MODEL_BYTES["base"])

    assert whisper_provider._already_here("base") is True


def test_a_disk_with_room_for_nothing_reports_whisper_s_own_failure(monkeypatch):
    """Rather than inventing a different error here."""
    _cached(monkeypatch)
    _disk(monkeypatch, 1_000)

    assert whisper_provider._affordable_model("medium") == "medium"
