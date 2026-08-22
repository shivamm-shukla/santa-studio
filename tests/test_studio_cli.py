"""The storage commands.

`doctor` gets the most attention because it is the first thing a new install
runs, and a check that reports a problem without saying how to fix it is worse
than no check.
"""

import json

import pytest

import asset_cache
import paths
import studio


def run(argv, capsys) -> tuple[int, str]:
    code = studio.main(argv)
    return code, capsys.readouterr().out


def a_project(run_id="11112222-3333", topic="A test project", state="DONE"):
    directory = paths.project_dir(run_id, topic)
    (directory / "project.json").write_text(
        json.dumps({"run_id": run_id, "topic": topic, "current_state": state})
    )
    return directory


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def test_doctor_runs_and_reports_every_group(studio_home, capsys):
    code, out = run(["doctor"], capsys)
    for heading in ("Runtime", "Reasoning", "Media", "Publishing", "Storage"):
        assert heading in out
    assert code in (0, 1)


def test_doctor_tells_you_what_to_do_about_a_missing_llm_key(studio_home, capsys, monkeypatch):
    from providers.llm.router import KEY_ENV

    for env in KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    code, out = run(["doctor"], capsys)
    assert code == 1, "no LLM provider at all should be a failure, not a warning"
    assert "GEMINI_API_KEY" in out
    assert "free" in out


def test_doctor_names_the_package_to_install_for_youtube(studio_home, capsys):
    _, out = run(["doctor"], capsys)
    if "missing googleapiclient" in out:
        assert "pip install google-api-python-client" in out


def test_doctor_notices_an_old_runs_directory(studio_home, capsys, tmp_path, monkeypatch):
    legacy = tmp_path / "runs"
    legacy.mkdir()
    (legacy / "abc.json").write_text("{}")
    monkeypatch.chdir(tmp_path)

    _, out = run(["doctor"], capsys)
    assert "migrate" in out


def test_doctor_is_quiet_about_migration_when_there_is_nothing_to_migrate(
    studio_home, capsys, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    _, out = run(["doctor"], capsys)
    assert "Old runs/" not in out


# --------------------------------------------------------------------------
# where / ls
# --------------------------------------------------------------------------

def test_where_labels_each_directory_by_lifecycle(studio_home, capsys):
    _, out = run(["where"], capsys)
    assert "safe to delete" in out
    assert "secret" in out
    assert str(studio_home) in out


def test_ls_with_no_projects_says_so(studio_home, capsys):
    _, out = run(["ls"], capsys)
    assert "No projects yet" in out


def test_ls_shows_the_topic_and_state(studio_home, capsys):
    a_project(topic="How gravitational waves were detected", state="AWAITING_APPROVAL")
    _, out = run(["ls"], capsys)
    assert "gravitational waves" in out
    assert "AWAITING_APPROVAL" in out


# --------------------------------------------------------------------------
# rm
# --------------------------------------------------------------------------

def test_rm_deletes_one_project(studio_home, capsys):
    directory = a_project()
    code, _ = run(["rm", "11112222", "-y"], capsys)
    assert code == 0
    assert not directory.exists()


def test_rm_finds_a_project_by_topic_fragment(studio_home, capsys):
    directory = a_project(topic="Why the dollar is the global currency")
    run(["rm", "dollar", "-y"], capsys)
    assert not directory.exists()


def test_rm_refuses_an_ambiguous_match_rather_than_guessing(studio_home, capsys):
    first = a_project("aaaa1111-0000", "Tipu Sultan rockets")
    second = a_project("bbbb2222-0000", "Tipu Sultan army")
    code, out = run(["rm", "tipu", "-y"], capsys)
    assert code == 1
    assert "matches 2 projects" in out
    assert first.exists() and second.exists()


def test_rm_says_so_when_nothing_matches(studio_home, capsys):
    code, out = run(["rm", "no-such-thing", "-y"], capsys)
    assert code == 1
    assert "studio.py ls" in out


def test_rm_without_confirmation_deletes_nothing(studio_home, capsys, monkeypatch):
    directory = a_project()
    monkeypatch.setattr("builtins.input", lambda _: "n")
    run(["rm", "11112222"], capsys)
    assert directory.exists()


# --------------------------------------------------------------------------
# clean
# --------------------------------------------------------------------------

def test_clean_requires_a_choice(studio_home, capsys):
    code, out = run(["clean"], capsys)
    assert code == 1
    assert "--cache" in out and "--orphans" in out


def test_clean_cache_leaves_projects_alone(studio_home, capsys):
    directory = a_project()
    temporary = asset_cache.temp_path(".mp4")
    with open(temporary, "wb") as handle:
        handle.write(b"x" * 100)
    asset_cache.adopt(temporary, ".mp4", source_url="https://a")

    run(["clean", "--cache", "-y"], capsys)
    assert directory.exists()
    assert paths.usage()["directories"]["cache"]["bytes"] == 0


def test_clean_orphans_keeps_what_a_project_references(studio_home, capsys):
    temporary = asset_cache.temp_path(".mp4")
    with open(temporary, "wb") as handle:
        handle.write(b"kept" * 100)
    kept = asset_cache.adopt(temporary, ".mp4", source_url="https://a")

    directory = a_project()
    (directory / "timeline.json").write_text(json.dumps({"shots": [{"source": kept}]}))

    run(["clean", "--orphans", "-y"], capsys)
    import os

    assert os.path.exists(kept)


def test_clean_cache_spares_files_that_cannot_be_refetched(studio_home, capsys):
    """Regression: wiping the cache destroyed footage migrated from an old
    install, which has no recorded source URL and so cannot come back."""
    import os

    temporary = asset_cache.temp_path(".mp4")
    with open(temporary, "wb") as handle:
        handle.write(b"irreplaceable" * 100)
    stuck = asset_cache.adopt(temporary, ".mp4", source_url="", query="from an old install")

    temporary = asset_cache.temp_path(".mp4")
    with open(temporary, "wb") as handle:
        handle.write(b"downloadable" * 100)
    normal = asset_cache.adopt(temporary, ".mp4", source_url="https://example.com/a.mp4")

    code, out = run(["clean", "--cache", "-y"], capsys)
    assert code == 0
    assert "cannot be downloaded again" in out
    assert os.path.exists(stuck), "unfetchable footage was deleted"
    assert not os.path.exists(normal)


def test_clean_cache_force_deletes_everything(studio_home, capsys):
    import os

    temporary = asset_cache.temp_path(".mp4")
    with open(temporary, "wb") as handle:
        handle.write(b"irreplaceable" * 100)
    stuck = asset_cache.adopt(temporary, ".mp4", source_url="")

    run(["clean", "--cache", "--force", "-y"], capsys)
    assert not os.path.exists(stuck)


def test_the_index_survives_a_partial_wipe(studio_home, capsys):
    temporary = asset_cache.temp_path(".mp4")
    with open(temporary, "wb") as handle:
        handle.write(b"irreplaceable" * 100)
    asset_cache.adopt(temporary, ".mp4", source_url="")

    run(["clean", "--cache", "-y"], capsys)
    assert asset_cache.stats()["files"] == 1


# --------------------------------------------------------------------------
# gc
# --------------------------------------------------------------------------

def test_gc_keeps_the_most_recent(studio_home, capsys):
    for index in range(4):
        a_project(f"{index}{index}{index}{index}0000-0000", f"project {index}")
    run(["gc", "--keep", "2", "-y"], capsys)
    assert len(paths.list_projects()) == 2


def test_gc_does_nothing_when_there_are_fewer_than_the_limit(studio_home, capsys):
    a_project()
    code, out = run(["gc", "--keep", "10", "-y"], capsys)
    assert code == 0
    assert "nothing to remove" in out
    assert len(paths.list_projects()) == 1


# --------------------------------------------------------------------------
# migrate
# --------------------------------------------------------------------------

@pytest.fixture
def legacy_runs(tmp_path):
    """A directory laid out the way the old pipeline wrote one."""
    runs = tmp_path / "runs"
    (runs / "shorts").mkdir(parents=True)
    (runs / "thumbnails").mkdir(parents=True)
    (runs / "voice_output").mkdir(parents=True)
    (runs / "assets").mkdir(parents=True)

    run_id = "3ce37bad-014d-4f52-bfc0-d6584f3ef6e2"
    voice = runs / "voice_output" / "621080c4-unrelated-uuid.wav"
    voice.write_bytes(b"voice audio")
    asset = runs / "assets" / "some-clip.mp4"
    asset.write_bytes(b"video bytes")
    (runs / f"{run_id}_final.mp4").write_bytes(b"master video")
    (runs / "shorts" / f"{run_id}_short.mp4").write_bytes(b"short video")
    (runs / "thumbnails" / f"{run_id}_thumb_1.jpg").write_bytes(b"thumb")

    (runs / f"{run_id}.json").write_text(json.dumps({
        "run_id": run_id,
        "topic": "Tipu Sultan ke rockets",
        "current_state": "DONE",
        "video_output": {"video_path": f"runs/{run_id}_final.mp4"},
        "shorts_output": {"short_path": f"runs/shorts/{run_id}_short.mp4"},
        "voice_output": {"audio_path": str(voice)},
        "visual_output": {"scene_assets": [{"scene_index": 0, "asset_path": str(asset)}]},
    }))
    return runs


def test_migrate_moves_a_project_across(studio_home, capsys, legacy_runs):
    code, out = run(["migrate", "--source", str(legacy_runs)], capsys)
    assert code == 0
    projects = paths.list_projects()
    assert len(projects) == 1
    assert "tipu-sultan-ke-rockets" in projects[0].name
    assert (projects[0] / "output" / "master.mp4").exists()
    assert (projects[0] / "output" / "short.mp4").exists()
    assert (projects[0] / "voice" / "narration.wav").exists()


def test_migrate_rewrites_the_recorded_paths(studio_home, capsys, legacy_runs):
    """Regression: the first migration copied files but left the state pointing
    into ./runs, so deleting that directory broke every migrated project and
    the whole cache looked unreferenced."""
    import os

    run(["migrate", "--source", str(legacy_runs)], capsys)
    project = paths.list_projects()[0]
    state = json.loads((project / "project.json").read_text())

    for recorded in (
        state["video_output"]["video_path"],
        state["shorts_output"]["short_path"],
        state["voice_output"]["audio_path"],
        state["visual_output"]["scene_assets"][0]["asset_path"],
    ):
        assert os.path.isabs(recorded), f"{recorded} is still relative"
        assert os.path.exists(recorded), f"{recorded} does not exist"
        assert str(legacy_runs) not in recorded, f"{recorded} still points at the old directory"


def test_migrated_assets_are_not_mistaken_for_orphans(studio_home, capsys, legacy_runs):
    run(["migrate", "--source", str(legacy_runs)], capsys)
    assert asset_cache.orphans() == []


def test_migrate_leaves_the_old_directory_intact(studio_home, capsys, legacy_runs):
    run(["migrate", "--source", str(legacy_runs)], capsys)
    assert (legacy_runs / "3ce37bad-014d-4f52-bfc0-d6584f3ef6e2.json").exists()


def test_migrate_carries_voice_profiles_across(studio_home, capsys, legacy_runs):
    """Regression: a recorded voice sample is the one thing here that cannot be
    regenerated, and the first migration walked straight past the profiles."""
    profiles = legacy_runs / "voice_profiles"
    (profiles / "abc-123").mkdir(parents=True)
    (profiles / "abc-123" / "original.wav").write_bytes(b"recorded sample")
    (profiles / "profiles.json").write_text(json.dumps({
        "abc-123": {
            "name": "my voice",
            "original_path": str(profiles / "abc-123" / "original.wav"),
            "filtered_path": None,
            "filter_preset": None,
        }
    }))

    run(["migrate", "--source", str(legacy_runs)], capsys)

    import providers.voice.profiles as voice_profiles

    carried = voice_profiles.list_profiles()
    assert "abc-123" in carried
    assert carried["abc-123"]["name"] == "my voice"
    # and the sample itself came with it, at a path that resolves
    sample = voice_profiles.resolve_voice_path("abc-123")
    assert sample.startswith(str(studio_home))
    import os

    assert os.path.exists(sample)


def test_migrate_does_not_lose_abandoned_runs(studio_home, capsys, legacy_runs):
    """An abandoned run still holds a script someone may want back."""
    abandoned = legacy_runs / "abandoned"
    abandoned.mkdir()
    (abandoned / "dead-0001.json").write_text(json.dumps({
        "run_id": "dead-0001-aaaa",
        "topic": "A run that was given up on",
        "current_state": "VISUAL_SELECTION",
        "script": {"script_text": "work worth keeping"},
    }))

    run(["migrate", "--source", str(legacy_runs)], capsys)

    names = [p.name for p in paths.list_projects()]
    assert any("a-run-that-was-given-up-on" in name for name in names)


def test_an_abandoned_run_is_marked_as_such(studio_home, capsys, legacy_runs):
    abandoned = legacy_runs / "abandoned"
    abandoned.mkdir()
    (abandoned / "dead-0001.json").write_text(json.dumps({
        "run_id": "dead-0001-aaaa", "topic": "Given up", "current_state": "SCRIPTING",
    }))
    run(["migrate", "--source", str(legacy_runs)], capsys)

    project = [p for p in paths.list_projects() if "given-up" in p.name][0]
    state = json.loads((project / "project.json").read_text())
    assert any(entry.get("event") == "abandoned" for entry in state.get("history", []))


def test_an_empty_profiles_registry_is_not_reported_as_carried(studio_home, capsys, legacy_runs):
    profiles = legacy_runs / "voice_profiles"
    profiles.mkdir()
    (profiles / "profiles.json").write_text("{}")
    _, out = run(["migrate", "--source", str(legacy_runs)], capsys)
    assert "voice profile" not in out


def test_migrate_says_so_when_there_is_nothing_to_do(studio_home, capsys, tmp_path):
    empty = tmp_path / "empty-runs"
    empty.mkdir()
    code, out = run(["migrate", "--source", str(empty)], capsys)
    assert code == 0
    assert "Nothing to migrate" in out


def test_migrate_skips_an_unreadable_state_rather_than_stopping(studio_home, capsys, legacy_runs):
    (legacy_runs / "broken.json").write_text("{ not json")
    code, out = run(["migrate", "--source", str(legacy_runs)], capsys)
    assert code == 0
    assert "unreadable" in out
    assert len(paths.list_projects()) == 1


def test_migrate_reports_a_missing_source(studio_home, capsys, tmp_path):
    code, out = run(["migrate", "--source", str(tmp_path / "nope")], capsys)
    assert code == 1
    assert "No directory" in out


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

def test_export_produces_a_zip_without_credentials(studio_home, capsys, tmp_path, monkeypatch):
    import zipfile

    a_project()
    (paths.credentials_dir() / "youtube_token.json").write_text('{"secret": true}')
    monkeypatch.chdir(tmp_path)

    code, out = run(["export", "11112222"], capsys)
    assert code == 0
    archive = next(tmp_path.glob("*.zip"))
    names = zipfile.ZipFile(archive).namelist()
    assert any("project.json" in name for name in names)
    assert not any("youtube_token" in name for name in names)
