"""Storage layout: naming, lookup, and the lifecycle split."""

import paths


def test_home_honours_the_override(studio_home):
    assert paths.home() == studio_home


def test_tree_is_created_with_every_lifecycle_directory(studio_home):
    paths.ensure_tree()
    for leaf in ("projects", "library/voices", "library/styles", "cache/assets",
                 "cache/music", "cache/models", "cache/llm", "config/credentials", "tmp"):
        assert (studio_home / leaf).is_dir(), f"{leaf} was not created"


def test_project_name_is_readable_and_sorts_by_date():
    name = paths.project_name("3ce37bad-014d-4f52", "Tipu Sultan ke rockets")
    assert name.startswith("2")            # ISO date first, so listings are chronological
    assert "tipu-sultan-ke-rockets" in name
    assert name.endswith("_3ce37bad")


def test_devanagari_topics_survive_as_readable_names():
    # The pipeline's own output language is Hinglish, so a topic arriving in
    # Devanagari is routine rather than exotic. Dropping non-ASCII outright
    # would name every one of these "untitled".
    slug = paths.slugify("टीपू सुल्तान के रॉकेट")
    assert slug != "untitled"
    assert slug.isascii()
    assert "tipu" in slug


def test_slugify_falls_back_rather_than_producing_an_empty_name():
    assert paths.slugify("") == "untitled"
    assert paths.slugify("   ") == "untitled"
    assert paths.slugify("!!!???") == "untitled"


def test_project_is_found_by_id_even_after_the_topic_changes(studio_home):
    run_id = "aabbccdd-1111-2222"
    first = paths.project_dir(run_id, "An early working title")
    # A topic can be edited at a review gate long after the directory exists,
    # so the id has to remain the key.
    again = paths.project_dir(run_id, "A completely different topic")
    assert again == first
    assert paths.find_project(run_id) == first


def test_project_directory_has_its_subfolders(studio_home):
    project = paths.project_dir("ffeeddcc-0000", "Gravitational waves")
    assert (project / "voice").is_dir()
    assert (project / "output").is_dir()


def test_projects_list_newest_first(studio_home):
    paths.project_dir("11111111-a", "alpha")
    paths.project_dir("22222222-b", "beta")
    listed = paths.list_projects()
    assert len(listed) == 2
    assert listed == sorted(listed, key=lambda p: p.name, reverse=True)


def test_cached_assets_are_sharded_by_digest(studio_home):
    digest = "a1b2c3d4" * 8
    path = paths.cached_asset(digest, ".mp4")
    assert path.parent.parent.name == digest[:2]
    assert path.parent.name == digest[2:4]
    assert path.name == f"{digest}.mp4"


def test_same_digest_always_resolves_to_one_file(studio_home):
    # This is what makes the cache dedupe: one clip pulled for three projects
    # is stored once.
    digest = "beef" * 16
    assert paths.cached_asset(digest, "mp4") == paths.cached_asset(digest, ".mp4")


def test_usage_labels_directories_by_lifecycle(studio_home):
    report = paths.usage()["directories"]
    assert report["projects"]["lifecycle"] == "precious"
    assert report["library"]["lifecycle"] == "precious"
    assert report["cache"]["lifecycle"] == "disposable"
    assert report["tmp"]["lifecycle"] == "disposable"
    assert report["config"]["lifecycle"] == "secret"


def test_secrets_live_outside_the_project_tree(studio_home):
    # `export` has to be able to exclude credentials by construction rather
    # than by remembering to skip them.
    credentials = paths.credentials_dir()
    assert paths.projects_dir() not in credentials.parents


def test_clear_tmp_empties_scratch_only(studio_home):
    (paths.tmp_dir() / "scratch.txt").write_text("x")
    keeper = paths.projects_dir() / "keep.txt"
    keeper.write_text("x")
    paths.clear_tmp()
    assert not any(paths.tmp_dir().iterdir())
    assert keeper.exists()


# ---------------------------------------------------------------------------
# Which projects gc is allowed to delete
# ---------------------------------------------------------------------------

import json
import os
import time


def _project(root, name, state="DONE", age_seconds=0.0):
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    state_file = directory / "project.json"
    state_file.write_text(json.dumps({"current_state": state}))
    when = time.time() - age_seconds
    os.utime(state_file, (when, when))
    os.utime(directory, (when, when))
    return directory


def test_projects_are_ordered_by_when_they_were_written(tmp_path, monkeypatch):
    """Sorted by name it is only newest-first across days and alphabetical
    within one - which is how gc kept ten morning runs and deleted an
    afternoon one that was still going."""
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import importlib

    import paths as paths_module
    importlib.reload(paths_module)
    root = paths_module.projects_dir()

    _project(root, "2026-08-25_aaa-first-alphabetically", age_seconds=9000)
    newest = _project(root, "2026-08-25_zzz-last-alphabetically", age_seconds=5)

    assert paths_module.list_projects()[0] == newest


def test_a_run_written_to_moments_ago_is_in_flight(tmp_path, monkeypatch):
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import importlib

    import paths as paths_module
    importlib.reload(paths_module)

    project = _project(paths_module.projects_dir(), "live", state="VOICE_GENERATION", age_seconds=5)
    assert paths_module.in_flight(project) is True


def test_a_finished_run_is_not_in_flight_however_recent(tmp_path, monkeypatch):
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import importlib

    import paths as paths_module
    importlib.reload(paths_module)

    project = _project(paths_module.projects_dir(), "done", state="DONE", age_seconds=5)
    assert paths_module.in_flight(project) is False


def test_an_old_unfinished_run_is_not_in_flight(tmp_path, monkeypatch):
    """Abandoned halfway yesterday; nobody is holding it open."""
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import importlib

    import paths as paths_module
    importlib.reload(paths_module)

    project = _project(paths_module.projects_dir(), "stale", state="SCRIPTING", age_seconds=86_400)
    assert paths_module.in_flight(project) is False


def test_a_project_with_no_state_file_is_not_in_flight(tmp_path, monkeypatch):
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import importlib

    import paths as paths_module
    importlib.reload(paths_module)

    empty = paths_module.projects_dir() / "empty"
    empty.mkdir(parents=True)
    assert paths_module.in_flight(empty) is False


def test_an_unreadable_state_written_moments_ago_is_left_alone(tmp_path, monkeypatch):
    """Half-written JSON means something is writing it right now."""
    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    import importlib

    import paths as paths_module
    importlib.reload(paths_module)

    project = paths_module.projects_dir() / "mid-write"
    project.mkdir(parents=True)
    (project / "project.json").write_text('{"current_state": "VOI')

    assert paths_module.in_flight(project) is True
