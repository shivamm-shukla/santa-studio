"""The Clips HTTP surface.

Phase C1-C3 built ingest, ranking, the editor and publishing, and every one
of them was reachable only from a test or the CLI. These drive the API the
way a browser does, because that is the only thing that proves the engine is
actually wired to anything.
"""

import json
import os
import time

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

import paths  # noqa: E402
from clips import engine as clips_engine  # noqa: E402
from clips.models import CandidateClip, ClipProject, ClipSource  # noqa: E402
from clips.publisher import PLATFORM_PRESETS  # noqa: E402
from state import saved_clip_projects, saved_runs  # noqa: E402
from web.server import app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app)


def _make_project(tmp_path, project_id="clipproj0001", rendered=True):
    """A stored clip project with one candidate and a real file on disk."""
    video = tmp_path / "source.mp4"
    video.write_bytes(b"not really an mp4, but it exists")

    preview = tmp_path / "preview.mp4"
    preview.write_bytes(b"preview bytes")

    project = ClipProject(
        project_id=project_id,
        source=ClipSource(
            source_type="youtube",
            video_path=str(video),
            title="A Source Video",
            duration=600.0,
        ),
        candidates=[
            CandidateClip(
                clip_id="clip1",
                start_time=12.0,
                end_time=45.0,
                duration=33.0,
                hook_text="The part that stops a scroll",
                full_text="The part that stops a scroll, and what came after it.",
                score=0.91,
                suggested_title="The Part That Stops A Scroll",
                rendered_path=str(preview) if rendered else None,
            )
        ],
        selected_clip_id="clip1",
    )
    clips_engine.save_project(project)
    return project


# ---- storage ---------------------------------------------------------------


def test_a_clip_project_is_not_reported_as_a_run(tmp_path):
    """A clip project is stored exactly like a generated one.

    That is deliberate - `studio ls`, `rm` and `gc` work on both - but it
    means the dashboard listed every clip project as a run with no id, no
    topic and no state until the two kinds said which they were.
    """
    _make_project(tmp_path)
    assert saved_runs() == []
    assert [p["project_id"] for p in saved_clip_projects()] == ["clipproj0001"]


def test_a_project_survives_a_round_trip(tmp_path):
    """It had save() and no load(), so nothing could be reopened."""
    original = _make_project(tmp_path)
    reloaded = clips_engine.load_project(original.project_id)

    assert reloaded is not None
    assert reloaded.project_id == original.project_id
    assert reloaded.source.title == "A Source Video"
    assert [c.clip_id for c in reloaded.candidates] == ["clip1"]
    assert reloaded.candidates[0].duration == 33.0
    assert reloaded.clip("clip1").suggested_title == "The Part That Stops A Scroll"
    assert reloaded.clip("nope") is None


def test_loading_a_project_that_does_not_exist_is_not_an_error():
    assert clips_engine.load_project("nosuchproject") is None


# ---- platforms -------------------------------------------------------------


def test_twitter_is_a_target(client):
    """The product needs Instagram and Twitter; only one of them existed."""
    platforms = client.get("/api/clips/platforms").json()
    assert "twitter" in platforms
    assert "instagram_reels" in platforms
    assert "youtube_shorts" in platforms


def test_twitter_has_a_cap_of_its_own(client):
    """2:20 matches neither neighbour, so Twitter cannot share their render.

    A cut long enough for TikTok is refused by Twitter; one cut for Reels
    throws away 50 seconds Twitter would have taken.
    """
    assert PLATFORM_PRESETS["twitter"]["max_duration"] == 140.0
    assert PLATFORM_PRESETS["instagram_reels"]["max_duration"] < 140.0 < PLATFORM_PRESETS["tiktok"]["max_duration"]


# ---- the API ---------------------------------------------------------------


def test_listing_and_reading_a_project(client, tmp_path):
    _make_project(tmp_path)

    listed = client.get("/api/clips").json()
    assert [p["project_id"] for p in listed] == ["clipproj0001"]
    assert listed[0]["title"] == "A Source Video"

    detail = client.get("/api/clips/clipproj0001").json()
    assert detail["source"]["duration"] == 600.0
    assert len(detail["candidates"]) == 1
    assert detail["candidates"][0]["has_preview"] is True
    # Nothing bundled yet, so there is nothing to offer as a download.
    assert detail["candidates"][0]["downloads"] == {}


def test_reading_a_missing_project_is_a_404(client):
    assert client.get("/api/clips/nosuchproject").status_code == 404


def test_creating_a_project_rejects_an_unknown_source(client):
    res = client.post("/api/clips", json={"source_type": "vimeo", "source_target": "x"})
    assert res.status_code == 400


def test_creating_a_project_rejects_an_empty_target(client):
    res = client.post("/api/clips", json={"source_type": "youtube", "source_target": "  "})
    assert res.status_code == 400


def test_creating_a_project_runs_in_the_background(client, monkeypatch, tmp_path):
    """Ingest downloads and transcribes a video, so it cannot answer a request."""
    made = {}

    def fake_create(source_type, source_target, target_count, render_previews):
        made["args"] = (source_type, source_target, target_count, render_previews)
        return _make_project(tmp_path, project_id="backgroundproj")

    monkeypatch.setattr(clips_engine, "create_clip_project", fake_create)

    res = client.post("/api/clips", json={
        "source_type": "youtube",
        "source_target": "https://youtu.be/abc",
        "target_count": 2,
    })
    job_id = res.json()["job_id"]

    for _ in range(100):
        status = client.get(f"/api/clips/jobs/{job_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "done", status
    assert status["project_id"] == "backgroundproj"
    assert made["args"] == ("youtube", "https://youtu.be/abc", 2, True)


def test_a_failing_job_reports_why(client, monkeypatch):
    def explode(**kwargs):
        raise RuntimeError("yt-dlp could not reach that URL")

    monkeypatch.setattr(clips_engine, "create_clip_project", explode)
    job_id = client.post("/api/clips", json={
        "source_type": "youtube", "source_target": "https://youtu.be/bad",
    }).json()["job_id"]

    for _ in range(100):
        status = client.get(f"/api/clips/jobs/{job_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)

    assert status["status"] == "error"
    assert "yt-dlp" in status["error"]


# ---- downloads -------------------------------------------------------------


def test_a_clip_cannot_be_downloaded_before_it_is_rendered(client, tmp_path):
    _make_project(tmp_path)
    res = client.get("/api/clips/clipproj0001/download/clip1/instagram_reels")
    assert res.status_code == 404
    assert "bundle" in res.json()["detail"]


def test_a_bundled_clip_is_downloadable_per_platform(client, tmp_path, monkeypatch):
    """The whole point of a bundle: one file per target, served to a browser."""
    project = _make_project(tmp_path)

    rendered = {}

    def fake_render(source_video_path, start_time, end_time, output_path, **kwargs):
        # A real render is FFmpeg over a real video; what matters here is
        # that each platform gets its own file at its own size.
        with open(output_path, "wb") as handle:
            handle.write(f"{kwargs.get('width')}x{kwargs.get('height')}".encode())
        rendered[output_path] = kwargs
        return output_path

    monkeypatch.setattr("clips.publisher.render_vertical_clip", fake_render)

    job_id = client.post(
        "/api/clips/clipproj0001/bundle",
        json={"platforms": ["instagram_reels", "twitter"]},
    ).json()["job_id"]

    for _ in range(200):
        status = client.get(f"/api/clips/jobs/{job_id}").json()
        if status["status"] != "running":
            break
        time.sleep(0.05)
    assert status["status"] == "done", status
    assert status["files"] == 2

    for platform in ("instagram_reels", "twitter"):
        res = client.get(f"/api/clips/clipproj0001/download/clip1/{platform}")
        assert res.status_code == 200, platform
        assert res.headers["content-type"] == "video/mp4"
        # A file the user saves should be named after the clip, not "clip1".
        assert platform in res.headers["content-disposition"]

    # The bundle is recorded on the project, so it survives the request.
    reopened = clips_engine.load_project("clipproj0001")
    assert set(reopened.bundle["clip1"]) == {"instagram_reels", "twitter"}


def test_bundling_rejects_an_unknown_platform(client, tmp_path):
    _make_project(tmp_path)
    res = client.post("/api/clips/clipproj0001/bundle", json={"platforms": ["myspace"]})
    assert res.status_code == 400


def test_a_preview_is_served_inline(client, tmp_path):
    _make_project(tmp_path)
    res = client.get("/api/clips/clipproj0001/preview/clip1")
    assert res.status_code == 200
    assert res.content == b"preview bytes"


# ---- publishing ------------------------------------------------------------


def test_publishing_a_clip_dry_runs_without_credentials(client, tmp_path):
    _make_project(tmp_path)
    res = client.post("/api/clips/clipproj0001/publish", json={
        "clip_id": "clip1", "dry_run": True,
    })
    assert res.status_code == 200
    body = res.json()
    assert body["dry_run"] is True
    assert body["video_url"].startswith("https://www.youtube.com/watch?v=")


def test_publishing_for_real_refuses_when_youtube_is_not_connected(client, tmp_path, monkeypatch):
    """Better a clear 409 than an OAuth browser opening on the server."""
    _make_project(tmp_path)
    monkeypatch.setattr(
        "providers.publish.youtube_provider.auth_status",
        lambda: {"connected": False, "detail": "Not connected yet."},
    )
    res = client.post("/api/clips/clipproj0001/publish", json={"clip_id": "clip1"})
    assert res.status_code == 409
    assert "not connected" in res.json()["detail"].lower()


def test_publishing_an_unrendered_clip_is_refused(client, tmp_path):
    _make_project(tmp_path, project_id="norender", rendered=False)
    res = client.post("/api/clips/norender/publish", json={
        "clip_id": "clip1", "dry_run": True,
    })
    assert res.status_code == 400


def test_youtube_status_never_starts_a_flow(client):
    """Reading status must not block or open a browser."""
    status = client.get("/api/publish/youtube/status").json()
    assert status["connected"] is False
    assert "detail" in status
    assert status["connecting"] is False
