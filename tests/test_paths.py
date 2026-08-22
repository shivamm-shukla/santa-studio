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
