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
from agents import youtube_publish
from state import PipelineState


@pytest.fixture
def fresh_config(monkeypatch):
    """config, re-read from the environment this test controls and nothing else.

    Clearing the variable was not enough on its own: reloading config runs
    load_dotenv() again, which puts whatever is in the developer's own .env
    straight back. So a machine with PUBLISH_TARGET set in .env - which is
    exactly what someone does when they want their own runs to stop uploading
    - failed a test about what connecting an account does.
    """
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
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
    assert manager_module._next_state("VIDEO_ASSEMBLY", config_without_publish) == "AWAITING_APPROVAL"
    assert manager_module._next_state("AWAITING_APPROVAL", config_without_publish) == "THUMBNAIL"
    assert manager_module._next_state("THUMBNAIL", config_without_publish) == "DONE"


def test_a_run_reaches_the_publish_gate_once_an_account_is_connected():
    config_with_publish = {"ACTIVE_PROVIDERS": {"publish": "youtube"}}
    assert manager_module._next_state("VIDEO_ASSEMBLY", config_with_publish) == "AWAITING_APPROVAL"
    assert manager_module._next_state("THUMBNAIL", config_with_publish) == "AWAITING_PUBLISH"
    assert manager_module._next_state("AWAITING_PUBLISH", config_with_publish) == "YOUTUBE_PUBLISH"


def test_shorts_are_still_cut_for_a_run_with_nowhere_to_publish():
    """Shorts sit after publishing in the sequence now.

    The skip for the publish states used to end the run at DONE rather than
    walk past them, so a run that asked for shorts and had no YouTube account
    attached silently got none - and nothing said so.
    """
    nowhere = {"ACTIVE_PROVIDERS": {"publish": None}}
    asked = {"shorts": True}

    assert manager_module._next_state("THUMBNAIL", nowhere, asked) == "SHORTS_EXTRACTION"
    assert manager_module._next_state("SHORTS_EXTRACTION", nowhere, asked) == "DONE"


def test_a_run_that_did_not_ask_for_shorts_walks_past_them():
    connected = {"ACTIVE_PROVIDERS": {"publish": "youtube"}}

    assert manager_module._next_state("YOUTUBE_PUBLISH", connected, {}) == "DONE"
    assert manager_module._next_state("YOUTUBE_PUBLISH", connected, {"shorts": True}) == "SHORTS_EXTRACTION"


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


# --------------------------------------------------------------------------
# Chapters in the description
# --------------------------------------------------------------------------

def _state_with_timeline(tmp_path, chapters):
    import json

    from state import PipelineState

    path = tmp_path / "timeline.json"
    path.write_text(json.dumps({"meta": {"chapters": chapters}}))

    state = PipelineState(topic="Containers")
    state.video_output = {"timeline_path": str(path)}
    return state


def test_the_sections_become_the_timestamps_youtube_renders(tmp_path):
    """YouTube turns a list like this into a clickable chapter strip.

    The numbers exist because the timeline measured them against the
    finished audio; nothing was carrying them into the description.
    """
    state = _state_with_timeline(tmp_path, [
        {"title": "The box", "at": 0.0},
        {"title": "What it cost", "at": 184.5},
        {"title": "After", "at": 602.0},
    ])

    assert youtube_publish._chapter_list(state) == (
        "0:00 The box\n3:04 What it cost\n10:02 After"
    )


def test_a_video_with_too_few_sections_gets_no_chapter_list(tmp_path):
    """Under three, YouTube shows the lines as plain text nobody can click."""
    state = _state_with_timeline(tmp_path, [
        {"title": "One", "at": 0.0},
        {"title": "Two", "at": 60.0},
    ])

    assert youtube_publish._chapter_list(state) == ""


def test_a_video_that_does_not_start_on_a_section_gets_an_opening_entry(tmp_path):
    """YouTube ignores the whole block unless it starts at 0:00.

    Relabelling the first section as 0:00 when it really starts later would
    put the wrong name on the video's opening, so the opening gets its own
    entry rather than borrowing the next one's.
    """
    state = _state_with_timeline(tmp_path, [
        {"title": "One", "at": 40.0},
        {"title": "Two", "at": 60.0},
        {"title": "Three", "at": 120.0},
    ])

    assert youtube_publish._chapter_list(state) == (
        "0:00 Intro\n0:40 One\n1:00 Two\n2:00 Three"
    )


def test_marks_that_do_not_increase_are_dropped_rather_than_shipped(tmp_path):
    """YouTube ignores the whole block, not the offending line."""
    state = _state_with_timeline(tmp_path, [
        {"title": "One", "at": 0.0},
        {"title": "Two", "at": 120.0},
        {"title": "Three", "at": 120.0},
    ])

    assert youtube_publish._chapter_list(state) == ""


def test_a_run_with_no_timeline_on_disk_simply_has_no_chapters():
    from state import PipelineState

    state = PipelineState(topic="Containers")
    assert youtube_publish._chapter_list(state) == ""

    state.video_output = {"timeline_path": "/nowhere/timeline.json"}
    assert youtube_publish._chapter_list(state) == ""


def test_the_chapters_and_the_sources_both_reach_the_description(tmp_path):
    state = _state_with_timeline(tmp_path, [
        {"title": "The box", "at": 0.0},
        {"title": "What it cost", "at": 184.5},
        {"title": "After", "at": 602.0},
    ])
    state.research = {"sources": [{"title": "A source", "url": "https://example.test/a"}]}

    description = youtube_publish._describe("What happened, and why.", state)

    assert "What happened, and why." in description
    assert "3:04 What it cost" in description
    assert "https://example.test/a" in description


def test_a_video_past_an_hour_gets_timestamps_youtube_can_parse(tmp_path):
    """"62:30" is not a longer video's minute count, it is malformed.

    One bad line makes YouTube drop the whole chapter block rather than
    the line.
    """
    state = _state_with_timeline(tmp_path, [
        {"title": "One", "at": 0.0},
        {"title": "Two", "at": 1800.0},
        {"title": "Three", "at": 3750.0},
    ])

    assert youtube_publish._chapter_list(state) == (
        "0:00 One\n30:00 Two\n1:02:30 Three"
    )
