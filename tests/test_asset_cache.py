"""The content-addressed cache: dedupe, eviction, and knowing what is still needed."""

import json
import os

import pytest

import asset_cache
import paths


def store(content: bytes, url: str = "", query: str = "", extension: str = ".mp4") -> str:
    temporary = asset_cache.temp_path(extension)
    with open(temporary, "wb") as handle:
        handle.write(content)
    return asset_cache.adopt(temporary, extension, source_url=url, query=query)


# --------------------------------------------------------------------------
# Addressing
# --------------------------------------------------------------------------

def test_identical_bytes_from_different_urls_are_stored_once(studio_home):
    first = store(b"same content", url="https://a.example/one.mp4", query="one")
    second = store(b"same content", url="https://b.example/two.mp4", query="two")
    assert first == second
    assert asset_cache.stats()["files"] == 1


def test_different_bytes_get_different_files(studio_home):
    assert store(b"aaa", url="https://a") != store(b"bbb", url="https://b")
    assert asset_cache.stats()["files"] == 2


def test_a_url_seen_before_is_answered_without_a_download(studio_home):
    path = store(b"payload", url="https://example.com/clip.mp4")
    assert asset_cache.by_url("https://example.com/clip.mp4") == path


def test_an_unknown_url_is_a_miss(studio_home):
    assert asset_cache.by_url("https://example.com/never-seen.mp4") is None


def test_a_url_whose_file_has_been_deleted_is_a_miss(studio_home):
    path = store(b"payload", url="https://example.com/clip.mp4")
    os.remove(path)
    assert asset_cache.by_url("https://example.com/clip.mp4") is None
    # and the stale index entry is dropped rather than lingering
    assert asset_cache.stats()["files"] == 0


def test_temp_paths_are_unique(studio_home):
    # Concurrent scene fetches used to collide on a shared temporary name and
    # corrupt each other's downloads.
    assert len({asset_cache.temp_path(".mp4") for _ in range(50)}) == 50


def test_the_temp_file_is_removed_after_adoption(studio_home):
    temporary = asset_cache.temp_path(".mp4")
    with open(temporary, "wb") as handle:
        handle.write(b"x")
    asset_cache.adopt(temporary, ".mp4")
    assert not os.path.exists(temporary)


# --------------------------------------------------------------------------
# Knowing what is referenced
# --------------------------------------------------------------------------

def test_assets_a_project_points_at_are_not_orphans(studio_home):
    kept = store(b"in use", url="https://a", query="kept")
    store(b"not in use", url="https://b", query="dropped")

    project = paths.project_dir("11112222-3333", "A project")
    (project / "timeline.json").write_text(json.dumps({"shots": [{"source": kept}]}))

    orphans = asset_cache.orphans()
    assert [entry["query"] for entry in orphans] == ["dropped"]


def test_dropping_orphans_leaves_referenced_files_alone(studio_home):
    kept = store(b"in use", url="https://a")
    doomed = store(b"not in use", url="https://b")
    project = paths.project_dir("11112222-3333", "A project")
    (project / "project.json").write_text(json.dumps({"visual_output": {
        "scene_assets": [{"asset_path": kept}]}}))

    report = asset_cache.drop_orphans()
    assert report["removed"] == 1
    assert os.path.exists(kept)
    assert not os.path.exists(doomed)


def test_a_project_deleted_by_hand_stops_protecting_its_assets(studio_home):
    # References are read from the projects themselves, so a directory removed
    # outside the tool cannot leave a phantom claim keeping files alive.
    import shutil

    asset = store(b"content", url="https://a")
    project = paths.project_dir("11112222-3333", "A project")
    (project / "timeline.json").write_text(json.dumps({"shots": [{"source": asset}]}))
    assert asset_cache.orphans() == []

    shutil.rmtree(project)
    assert len(asset_cache.orphans()) == 1


def test_an_unreadable_project_file_does_not_break_the_scan(studio_home):
    store(b"content", url="https://a")
    project = paths.project_dir("11112222-3333", "A project")
    (project / "timeline.json").write_text("{ not json at all")
    assert isinstance(asset_cache.orphans(), list)


# --------------------------------------------------------------------------
# Eviction
# --------------------------------------------------------------------------

def test_eviction_drops_least_recently_used_first(studio_home):
    old = store(b"o" * 1000, url="https://old")
    asset_cache.touch(asset_cache.hash_file(old))
    new = store(b"n" * 1000, url="https://new")
    asset_cache.touch(asset_cache.hash_file(new))

    asset_cache.evict(max_bytes=1000)
    assert os.path.exists(new)
    assert not os.path.exists(old)


def test_eviction_stops_once_it_is_under_the_ceiling(studio_home):
    for i in range(5):
        store(bytes([i]) * 1000, url=f"https://{i}")
    asset_cache.evict(max_bytes=3000)
    assert asset_cache.stats()["bytes"] <= 3000


def test_protected_assets_survive_eviction(studio_home):
    # An in-flight run must not have its own footage deleted out from under it.
    protected = store(b"p" * 5000, url="https://protected")
    for i in range(4):
        store(bytes([i]) * 5000, url=f"https://filler{i}")

    asset_cache.evict(max_bytes=1000, protect={asset_cache.hash_file(protected)})
    assert os.path.exists(protected)


def test_eviction_reports_what_it_freed(studio_home):
    for i in range(3):
        store(bytes([i]) * 1000, url=f"https://{i}")
    report = asset_cache.evict(max_bytes=0)
    assert report["removed"] == 3
    assert report["freed"] == 3000
    assert "KB" in report["freed_human"] or "B" in report["freed_human"]


def test_nothing_is_evicted_when_the_cache_already_fits(studio_home):
    store(b"small", url="https://a")
    assert asset_cache.evict(max_bytes=asset_cache.DEFAULT_MAX_BYTES)["removed"] == 0


# --------------------------------------------------------------------------
# Repair
# --------------------------------------------------------------------------

def test_reindex_rebuilds_the_index_from_the_files(studio_home):
    # The files are the truth; the index is a convenience that can be rebuilt.
    store(b"one", url="https://a")
    store(b"two", url="https://b")

    os.remove(paths.cache_index())
    assert asset_cache.stats()["files"] == 0

    assert asset_cache.reindex()["indexed"] == 2
    assert asset_cache.stats()["files"] == 2


def test_reindex_ignores_files_that_are_not_content_addressed(studio_home):
    stray = paths.cache_dir("assets") / "a-human-named-file.mp4"
    stray.write_bytes(b"x")
    store(b"proper", url="https://a")
    assert asset_cache.reindex()["indexed"] == 1
    assert stray.exists(), "a stray file should be left alone, not deleted"
