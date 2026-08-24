"""Whether a run publishes, and what it takes to make that true.

The state machine has had YOUTUBE_PUBLISH in it from the beginning, guarded
by `ACTIVE_PROVIDERS["publish"]`, which was a hardcoded None. Nothing a user
could do in any frontend changed it, so the last two states of the pipeline
were unreachable by construction. These cover the thing that changes that.
"""

import importlib

import pytest

import config
import manager as manager_module
from state import PipelineState


@pytest.fixture
def fresh_config(monkeypatch):
    monkeypatch.delenv("PUBLISH_TARGET", raising=False)
    return importlib.reload(config)


def _connected(monkeypatch, value: bool):
    monkeypatch.setattr(
        "providers.publish.youtube_provider.auth_status",
        lambda: {"connected": value, "detail": ""},
    )


# ---- resolving the target --------------------------------------------------


def test_no_account_means_no_upload(fresh_config, monkeypatch):
    _connected(monkeypatch, False)
    assert fresh_config.build_config()["ACTIVE_PROVIDERS"]["publish"] is None


def test_connecting_an_account_is_what_turns_publishing_on(fresh_config, monkeypatch):
    """Connecting is the user-facing action; nothing else should be required."""
    _connected(monkeypatch, True)
    assert fresh_config.build_config()["ACTIVE_PROVIDERS"]["publish"] == "youtube"


def test_publishing_can_be_held_off_with_an_account_connected(monkeypatch):
    monkeypatch.setenv("PUBLISH_TARGET", "none")
    reloaded = importlib.reload(config)
    _connected(monkeypatch, True)
    assert reloaded.build_config()["ACTIVE_PROVIDERS"]["publish"] is None
    importlib.reload(config)


def test_a_broken_google_install_does_not_break_a_run(fresh_config, monkeypatch):
    """Publishing is optional, so its dependencies must be too."""
    def explode():
        raise ImportError("google-auth-oauthlib is not installed")

    monkeypatch.setattr("providers.publish.youtube_provider.auth_status", explode)
    assert fresh_config.build_config()["ACTIVE_PROVIDERS"]["publish"] is None


# ---- what the state machine does with it -----------------------------------


def test_a_run_ends_at_done_when_nothing_can_be_uploaded_to():
    """Rather than halting on a gate it could never satisfy.

    Only the two publish states are skipped. "Is the video good?" is asked
    either way, because that gate is about the cut, not about uploading.
    """
    config_without_publish = {"ACTIVE_PROVIDERS": {"publish": None}}
    assert manager_module._next_state("SHORTS_EXTRACTION", config_without_publish) == "AWAITING_APPROVAL"
    assert manager_module._next_state("THUMBNAIL", config_without_publish) == "DONE"


def test_a_run_reaches_the_publish_gate_once_an_account_is_connected():
    config_with_publish = {"ACTIVE_PROVIDERS": {"publish": "youtube"}}
    assert manager_module._next_state("SHORTS_EXTRACTION", config_with_publish) == "AWAITING_APPROVAL"
    assert manager_module._next_state("THUMBNAIL", config_with_publish) == "AWAITING_PUBLISH"
    assert manager_module._next_state("AWAITING_PUBLISH", config_with_publish) == "YOUTUBE_PUBLISH"


def test_the_publish_gate_shows_what_is_about_to_be_uploaded():
    """The gate is the last point a human sees the metadata before it ships."""
    state = PipelineState(niche="history", topic="Rockets")
    view = manager_module._gate_view(
        state,
        "AWAITING_PUBLISH",
        {"title": "The Rockets That Beat An Empire", "tags": ["a", "b"], "thumbnails": [{"path": "x"}]},
    )
    assert view["stage"] == "AWAITING_PUBLISH"
    assert "The Rockets That Beat An Empire" in view["body"]
    assert "2 tags" in view["body"]
    assert [o["id"] for o in view["options"]] == ["approve", "regenerate"]


# ---- the provider ----------------------------------------------------------


def test_an_upload_never_opens_a_browser_by_itself(monkeypatch, tmp_path):
    """A pipeline runs on a background thread, often unattended.

    run_local_server would block that thread and open a consent screen on
    the server, so an unconnected upload has to fail with an instruction.
    """
    from providers.publish.youtube_provider import YouTubeProvider

    monkeypatch.setenv("YOUTUBE_TOKEN_FILE", str(tmp_path / "no-token.json"))
    provider = YouTubeProvider(dry_run=False)

    with pytest.raises(RuntimeError) as excinfo:
        provider._get_authenticated_service()
    assert "studio youtube connect" in str(excinfo.value)


def test_a_dry_run_needs_no_credentials_at_all():
    from providers.publish.youtube_provider import YouTubeProvider

    result = YouTubeProvider(dry_run=True).upload(
        video_path="/nonexistent.mp4", title="T", description="", tags=[]
    )
    assert result["dry_run"] is True
    assert result["video_id"]
