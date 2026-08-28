"""What the web app lets you tell the pipeline, and what it refuses to accept.

Two gaps this covers, both of the same shape - the backend could already do
the thing and no front end ever asked for it.

`REFERENCE_ANALYSIS` has read `preferences["reference_urls"]` since it
existed, and the dashboard had no field for them, so every run started through
the web app analysed nothing and learned its Style Profile from a default.

The voice sample analysis has always measured duration and said in its report
when a sample was too short to characterise a voice. The profile was created
anyway, so an unusable sample sat in the list looking exactly like a usable
one.
"""

import subprocess

import pytest

pytest.importorskip("fastapi")

import manager
from providers._ffmpeg_setup import ensure_ffmpeg_on_path
from providers.voice import repair


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import web.server as server

    with TestClient(server.app) as test_client:
        yield test_client


@pytest.fixture
def sample(tmp_path):
    """A tone of a given length, as a stand-in for a voice recording."""
    import shutil

    ensure_ffmpeg_on_path()
    ffmpeg = shutil.which("ffmpeg")

    def make(seconds: float):
        path = tmp_path / f"tone-{seconds}.wav"
        subprocess.run(
            [ffmpeg, "-v", "error", "-y", "-f", "lavfi",
             "-i", f"sine=frequency=220:duration={seconds}",
             "-ar", "24000", "-ac", "1", str(path)],
            check=True,
        )
        return path

    return make


# ---------------------------------------------------------------------------
# Reference videos and channels
# ---------------------------------------------------------------------------


def _start(client, **body):
    payload = {"niche": "industrial history", "target_length_minutes": 2}
    payload.update(body)
    return client.post("/api/runs", json=payload).json()["run_id"]


def test_reference_links_reach_the_agent_that_reads_them(client, studio_home):
    import web.server as server

    run_id = _start(client, reference_urls=[
        "https://youtube.com/watch?v=abc",
        "https://youtube.com/@channel",
    ])
    state = server.RUNS[run_id].state

    assert manager._build_input(state, "REFERENCE_ANALYSIS") == {
        "urls": ["https://youtube.com/watch?v=abc", "https://youtube.com/@channel"]
    }


def test_blank_rows_are_not_sent_as_references(client, studio_home):
    """The form always keeps an empty row on screen to type into."""
    import web.server as server

    run_id = _start(client, reference_urls=["https://youtube.com/watch?v=abc", "  ", ""])
    state = server.RUNS[run_id].state

    assert state.preferences["reference_urls"] == ["https://youtube.com/watch?v=abc"]


def test_a_run_with_no_references_carries_none(client, studio_home):
    import web.server as server

    run_id = _start(client)
    state = server.RUNS[run_id].state

    assert "reference_urls" not in state.preferences
    assert manager._build_input(state, "REFERENCE_ANALYSIS") == {"urls": []}


def test_the_board_offers_somewhere_to_put_them():
    """The brief is written on the Manager's board in the room now, not on a
    flat page beside it. Read as source rather than rendered, because the room
    is built by vite and this suite does not run node."""
    board = _room_file("ui/BoardPanel.jsx")

    assert "referenceUrls" in board, "no field to put a reference in"
    assert "structure and pacing" in board, "the board does not say what they are used for"


def _room_file(relative: str) -> str:
    """A file from the room's source.

    Three of these tests used to assert against rendered HTML from flat pages
    that no longer exist - the room does those jobs now. What they were really
    pinning is a contract between the backend and the interface, and that is
    worth keeping wherever the interface lives.
    """
    import pathlib

    return (pathlib.Path(__file__).resolve().parent.parent / "room" / "src" / relative).read_text()


# ---------------------------------------------------------------------------
# Voice samples: a floor, and deliberately no ceiling
# ---------------------------------------------------------------------------


def test_a_sample_too_short_to_clone_from_is_refused(client, sample, studio_home):
    response = client.post(
        "/api/voice/profiles",
        data={"name": "Too short"},
        files={"file": ("short.wav", sample(3).read_bytes(), "audio/wav")},
    )

    assert response.status_code == 400
    assert "8" in response.json()["detail"], "the message should say what is needed"


def test_a_long_enough_sample_is_accepted(client, sample, studio_home):
    response = client.post(
        "/api/voice/profiles",
        data={"name": "Long enough"},
        files={"file": ("long.wav", sample(12).read_bytes(), "audio/wav")},
    )

    assert response.status_code == 200


def test_there_is_no_upper_limit(client, sample, studio_home):
    """Longer only helps. The old form said "~6s" and enforced nothing at all."""
    response = client.post(
        "/api/voice/profiles",
        data={"name": "Long"},
        files={"file": ("long.wav", sample(40).read_bytes(), "audio/wav")},
    )

    assert response.status_code == 200


def test_the_booth_states_the_same_floor_the_analysis_judges_against():
    """Two numbers that can drift apart is how an interface ends up lying: the
    booth would invite a seven-second take and the checker would refuse it."""
    recorder = _room_file("studio/useRecorder.js")

    assert f"MIN_SECONDS = {int(repair.MIN_SECONDS)}" in recorder


# ---------------------------------------------------------------------------
# Living with a profile once it exists
# ---------------------------------------------------------------------------


def _profile(client, sample, name="Test voice"):
    return client.post(
        "/api/voice/profiles",
        data={"name": name},
        files={"file": ("long.wav", sample(12).read_bytes(), "audio/wav")},
    ).json()["profile_id"]


def test_a_mood_can_be_taken_off_again(client, sample, studio_home):
    """Applying one was a one-way door: every preset was reachable and plain
    was not, so trying one meant living with it or starting over."""
    profile_id = _profile(client, sample)

    client.post(f"/api/voice/profiles/{profile_id}/filter", json={"preset": "deep"})
    assert client.get(f"/api/voice/profiles/{profile_id}/audio/filtered").status_code == 200

    assert client.delete(f"/api/voice/profiles/{profile_id}/filter").status_code == 200
    assert client.get(f"/api/voice/profiles/{profile_id}/audio/filtered").status_code == 404


def test_clearing_a_mood_sends_narration_back_to_the_original(client, sample, studio_home):
    from providers.voice.profiles import resolve_voice_path

    profile_id = _profile(client, sample)
    client.post(f"/api/voice/profiles/{profile_id}/filter", json={"preset": "deep"})
    filtered = resolve_voice_path(profile_id)

    client.delete(f"/api/voice/profiles/{profile_id}/filter")

    assert resolve_voice_path(profile_id) != filtered


def test_audio_is_served_from_where_the_profile_actually_keeps_it(client, sample, studio_home):
    """The page used to build these URLs by stripping a "runs/" prefix, which
    stopped being where anything lived when storage moved out of the checkout."""
    profile_id = _profile(client, sample)

    assert client.get(f"/api/voice/profiles/{profile_id}/audio/original").status_code == 200


def test_asking_for_audio_a_profile_does_not_have_is_a_404(client, sample, studio_home):
    profile_id = _profile(client, sample)

    assert client.get(f"/api/voice/profiles/{profile_id}/audio/filtered").status_code == 404
    assert client.get(f"/api/voice/profiles/{profile_id}/audio/nonsense").status_code == 404


def test_every_mood_is_offered_on_the_rack():
    """They only ever rendered inside a profile card once, so somebody
    arriving was told nothing about what the studio could do."""
    voices = _room_file("studio/useVoices.js")
    moods = voices[voices.index("export const MOODS"):]

    assert moods.count('", "') >= 6, "the rack is not offering every mood"
