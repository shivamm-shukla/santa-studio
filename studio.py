"""Command line for looking after the studio's storage.

    python studio.py doctor              is this machine ready to run anything
    python studio.py where               every path, with its size
    python studio.py ls                  projects: date, topic, state, size
    python studio.py rm <project>        delete one project
    python studio.py clean --cache       drop everything regenerable
    python studio.py clean --orphans     drop cache nothing references
    python studio.py gc --keep 10        keep the N most recent projects
    python studio.py export <project>    zip a project, without credentials
    python studio.py migrate             move an old runs/ directory across

`doctor` is the one that matters for a fresh install. Everything the studio
needs is either optional or has a free tier, so the useful question is not
"does this work" but "what will not work yet, and what do I do about it" - so
every check that fails prints the fix next to it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

import paths

# Terminal colour, skipped when the output is being piped somewhere.
_TTY = sys.stdout.isatty()


def _paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text


def ok(text):    return _paint(text, "32")
def warn(text):  return _paint(text, "33")
def bad(text):   return _paint(text, "31")
def dim(text):   return _paint(text, "2")
def bold(text):  return _paint(text, "1")


PASS, WARN, FAIL = "pass", "warn", "fail"
_MARK = {PASS: ok("  ok  "), WARN: warn(" warn "), FAIL: bad(" fail ")}


# --------------------------------------------------------------------------
# doctor
# --------------------------------------------------------------------------

def _check_python() -> tuple[str, str, str]:
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info < (3, 11):
        return FAIL, f"Python {version}", "Python 3.11 or newer is required."
    return PASS, f"Python {version}", ""


def _check_ffmpeg() -> tuple[str, str, str]:
    try:
        from providers._ffmpeg_setup import ensure_ffmpeg_on_path

        ensure_ffmpeg_on_path()
        found = shutil.which("ffmpeg")
        if not found:
            raise RuntimeError("not on PATH after setup")
        return PASS, "FFmpeg", dim(found)
    except Exception as e:
        return FAIL, "FFmpeg", f"{e}. Run: pip install static-ffmpeg"


def _check_imports() -> list[tuple[str, str, str]]:
    """Optional-but-important libraries, each with what it costs to skip."""
    wanted = [
        ("moviepy", "video rendering", "pip install -r requirements.txt", True),
        ("pydub", "audio mixing", "pip install -r requirements.txt", True),
        ("PIL", "thumbnails and motion", "pip install -r requirements.txt", True),
        ("anyascii", "readable names for Hindi topics", "pip install anyascii", False),
        ("whisper", "caption timing for English", "pip install openai-whisper", False),
        ("torch", "local voice models", "pip install torch", False),
        ("googleapiclient", "YouTube publishing",
         "pip install google-api-python-client google-auth-oauthlib", False),
    ]
    results = []
    for module, purpose, fix, required in wanted:
        try:
            __import__(module)
            results.append((PASS, purpose, dim(module)))
        except ImportError:
            results.append((FAIL if required else WARN, purpose, f"missing {module} - {fix}"))
    return results


def _check_fonts() -> tuple[str, str, str]:
    try:
        from render import fonts

        report = fonts.describe()
    except Exception as e:
        return WARN, "Fonts", f"could not be checked: {e}"

    if not report["latin"]:
        return WARN, "Fonts", "no font found; captions will use whatever the drawing library picks"
    if not report["can_render_hindi"]:
        return (
            WARN,
            "Fonts",
            "no Devanagari font - Hindi captions will render as boxes. "
            "Install fonts-noto-devanagari (Debian/Ubuntu) or noto-fonts (Arch).",
        )
    return PASS, "Fonts", dim("Latin and Devanagari available")


def _check_llm() -> list[tuple[str, str, str]]:
    from providers.llm.router import KEY_ENV, configured_providers

    configured = configured_providers()
    if not configured:
        return [(
            FAIL, "LLM providers",
            "none configured. Set at least one of "
            + ", ".join(KEY_ENV.values())
            + " in .env - all four are free.",
        )]

    results = [(PASS, "LLM providers", dim(", ".join(configured)))]
    try:
        from providers.llm.budget import BudgetLedger

        for name, usage in BudgetLedger().report().items():
            if name not in configured or not usage["limit"]:
                continue
            if usage["exhausted"]:
                results.append((
                    WARN, f"  {name} quota",
                    f"{usage['used']}/{usage['limit']} used today - will be skipped until tomorrow",
                ))
            elif usage["used"]:
                results.append((PASS, f"  {name} quota",
                                dim(f"{usage['used']}/{usage['limit']} used today")))
    except Exception:
        pass
    return results


def _check_media_keys() -> list[tuple[str, str, str]]:
    keys = [
        ("PEXELS_API_KEY", "Pexels stock footage", "pexels.com/api"),
        ("PIXABAY_API_KEY", "Pixabay stock footage and music", "pixabay.com/api/docs"),
    ]
    results = []
    for env, purpose, where in keys:
        if os.getenv(env):
            results.append((PASS, purpose, dim("configured")))
        else:
            results.append((WARN, purpose, f"{env} not set - free key at {where}"))
    if not os.getenv("PEXELS_API_KEY") and not os.getenv("PIXABAY_API_KEY"):
        results.append((
            WARN, "  visuals",
            "with neither key, only Wikimedia Commons is available",
        ))
    return results


def _check_youtube() -> tuple[str, str, str]:
    credentials = os.getenv("YOUTUBE_CREDENTIALS_FILE", "client_secret.json")
    token = paths.credentials_dir() / "youtube_token.json"
    if not os.path.exists(credentials):
        return (
            WARN, "YouTube publishing",
            f"no OAuth client at {credentials}. Publishing is opt-in; see the README "
            "for the Google Cloud setup.",
        )
    if not token.exists():
        return WARN, "YouTube publishing", "client secret found, but no token yet - first upload will open a browser"
    return PASS, "YouTube publishing", dim("authorised")


def _check_storage() -> list[tuple[str, str, str]]:
    report = paths.usage()
    results = [(PASS, "Storage", dim(report["home"]))]

    try:
        free = shutil.disk_usage(report["home"]).free
    except OSError:
        free = None

    if free is not None:
        if free < 2 * 1024 ** 3:
            results.append((FAIL, "  free space", f"{paths.human_size(free)} left - renders will fail"))
        elif free < 10 * 1024 ** 3:
            results.append((WARN, "  free space", f"{paths.human_size(free)} left"))
        else:
            results.append((PASS, "  free space", dim(paths.human_size(free))))

    results.append((PASS, "  in use", dim(
        f"{report['total_human']} across {len(paths.list_projects())} projects"
    )))
    return results


def _check_legacy_runs() -> tuple[str, str, str] | None:
    """A leftover runs/ directory means an install from before the move."""
    legacy = os.path.join(os.getcwd(), "runs")
    if not os.path.isdir(legacy):
        return None
    states = [f for f in os.listdir(legacy) if f.endswith(".json")]
    if not states:
        return None
    return (
        WARN, "Old runs/ directory",
        f"{len(states)} project(s) still in ./runs. Run: python studio.py migrate",
    )


def command_doctor(args) -> int:
    print(bold("\nSanta Studio - environment check\n"))

    groups: list[tuple[str, list]] = [
        ("Runtime", [_check_python(), _check_ffmpeg(), _check_fonts()] + _check_imports()),
        ("Reasoning", _check_llm()),
        ("Media", _check_media_keys()),
        ("Publishing", [_check_youtube()]),
        ("Storage", _check_storage()),
    ]
    legacy = _check_legacy_runs()
    if legacy:
        groups.append(("Migration", [legacy]))

    failures = warnings = 0
    for title, checks in groups:
        print(bold(title))
        for status, label, detail in checks:
            failures += status == FAIL
            warnings += status == WARN
            print(f" [{_MARK[status]}] {label:<34} {detail}")
        print()

    if failures:
        print(bad(f"{failures} problem(s) will stop a run.  ") + dim("Fix those first."))
        return 1
    if warnings:
        print(warn(f"{warnings} thing(s) are missing but optional.  ")
              + dim("A run will work with reduced quality."))
        return 0
    print(ok("Everything checks out."))
    return 0


# --------------------------------------------------------------------------
# where / ls
# --------------------------------------------------------------------------

def command_where(args) -> int:
    report = paths.usage()
    print(bold("\nSanta Studio storage"))
    print(dim("  override with SANTA_STUDIO_HOME\n"))
    print(f"  {bold(report['home'])}\n")

    label = {"precious": ok("keep"), "disposable": warn("safe to delete"), "secret": bad("secret")}
    for name, entry in report["directories"].items():
        print(f"  {name:<10} {entry['human']:>10}   {label[entry['lifecycle']]}")
    print(f"\n  {'total':<10} {report['total_human']:>10}\n")
    return 0


def _load_project(directory) -> dict:
    for name in ("project.json", "state.json"):
        path = directory / name
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


def command_ls(args) -> int:
    projects = paths.list_projects()
    if not projects:
        print(dim("\nNo projects yet.\n"))
        return 0

    print(bold(f"\n{'date':<12}{'topic':<44}{'state':<20}{'size':>10}"))
    print(dim("-" * 86))
    for directory in projects:
        state = _load_project(directory)
        date = directory.name[:10]
        topic = (state.get("topic") or state.get("user_topic") or directory.name[11:-9]) or "-"
        current = state.get("current_state", "-")
        size = paths.human_size(paths._dir_size(directory))
        print(f"{date:<12}{topic[:42]:<44}{current:<20}{size:>10}")
        if args.paths:
            print(dim(f"            {directory}"))
    print()
    return 0


# --------------------------------------------------------------------------
# rm / clean / gc
# --------------------------------------------------------------------------

def _resolve_project(needle: str):
    """Finds a project by id fragment, directory name, or topic fragment."""
    candidates = paths.list_projects()
    exact = [p for p in candidates if p.name == needle]
    if exact:
        return exact[0]
    partial = [p for p in candidates if needle.lower() in p.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        print(bad(f"{needle!r} matches {len(partial)} projects:"))
        for match in partial:
            print(f"  {match.name}")
        return None
    print(bad(f"No project matching {needle!r}. Run: python studio.py ls"))
    return None


def _confirm(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def command_rm(args) -> int:
    project = _resolve_project(args.project)
    if project is None:
        return 1
    size = paths.human_size(paths._dir_size(project))
    print(f"\n  {bold(project.name)}  ({size})")
    if not _confirm("Delete this project and everything in it?", args.yes):
        print(dim("Nothing was deleted.\n"))
        return 0
    shutil.rmtree(project)
    print(ok(f"Deleted {project.name} ({size} freed)\n"))
    return 0


def command_clean(args) -> int:
    import asset_cache

    if not args.cache and not args.orphans:
        print(bad("Choose --cache (everything regenerable) or --orphans "
                  "(only what no project references)."))
        return 1

    if args.orphans:
        found = asset_cache.orphans()
        total = sum(entry["bytes"] for entry in found)
        print(f"\n  {len(found)} orphaned file(s), {paths.human_size(total)}")
        if not found:
            print()
            return 0
        if not _confirm("Delete them?", args.yes):
            print(dim("Nothing was deleted.\n"))
            return 0
        print(ok(f"  freed {asset_cache.drop_orphans()['freed_human']}\n"))
        return 0

    report = paths.usage()["directories"]
    total = report["cache"]["bytes"] + report["tmp"]["bytes"]
    stuck = asset_cache.unfetchable()

    print(f"\n  cache and tmp hold {paths.human_size(total)}")

    if stuck and not args.force:
        stuck_bytes = sum(entry["bytes"] for entry in stuck)
        print(bad(f"\n  {len(stuck)} file(s), {paths.human_size(stuck_bytes)}, cannot be "
                  "downloaded again."))
        print(dim("  These came from an older install that never recorded where its\n"
                  "  footage came from, so deleting them loses them for good. Projects\n"
                  "  that use them would re-render with blank cards."))
        print(dim("\n  Skipping those. Pass --force to delete them too.\n"))

    keep = set() if args.force else {entry["digest"] for entry in stuck}
    if not _confirm("Delete the rest?" if keep else "Delete it?", args.yes):
        print(dim("Nothing was deleted.\n"))
        return 0

    freed = _wipe_disposable(keep)
    paths.ensure_tree()
    print(ok(f"  freed {paths.human_size(freed)}\n"))
    return 0


def _wipe_disposable(keep_digests: set) -> int:
    """Empties cache/ and tmp/, sparing files whose digests are in `keep`.

    The index goes with everything else and is rebuilt from what survived,
    rather than being preserved and left describing files that are no longer
    there. When nothing is spared there is nothing to rebuild, so a full wipe
    really does leave the directory empty.
    """
    import asset_cache as cache

    freed = 0
    for name in paths.DISPOSABLE:
        root = paths.home() / name
        if not root.exists():
            continue
        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if os.path.splitext(filename)[0] in keep_digests:
                    continue
                full = os.path.join(dirpath, filename)
                try:
                    freed += os.path.getsize(full)
                    os.remove(full)
                except OSError:
                    pass

    if keep_digests:
        cache.reindex()
    return freed


def command_gc(args) -> int:
    projects = paths.list_projects()
    doomed = projects[args.keep:]
    if not doomed:
        print(dim(f"\n{len(projects)} project(s); nothing to remove.\n"))
        return 0

    total = sum(paths._dir_size(p) for p in doomed)
    print(f"\n  keeping the {args.keep} most recent, removing {len(doomed)}:")
    for project in doomed:
        print(f"    {project.name}")
    print(f"\n  {paths.human_size(total)} would be freed")
    if not _confirm("Delete them?", args.yes):
        print(dim("Nothing was deleted.\n"))
        return 0
    for project in doomed:
        shutil.rmtree(project, ignore_errors=True)
    print(ok(f"  freed {paths.human_size(total)}\n"))
    return 0


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

def command_export(args) -> int:
    project = _resolve_project(args.project)
    if project is None:
        return 1
    destination = args.output or f"{project.name}.zip"
    # Credentials live outside the project tree, so excluding them is a
    # property of the layout rather than something to remember here.
    archive = shutil.make_archive(
        destination[:-4] if destination.endswith(".zip") else destination,
        "zip",
        root_dir=project.parent,
        base_dir=project.name,
    )
    print(ok(f"\n  {archive}  ({paths.human_size(os.path.getsize(archive))})\n"))
    return 0


# --------------------------------------------------------------------------
# migrate
# --------------------------------------------------------------------------

def _migrate_voice_profiles(legacy: str) -> int:
    """Carries cloned voice profiles into the library.

    These are the one genuinely irreplaceable thing in an old install - a
    recorded sample cannot be regenerated - and the first version of this
    command walked straight past them.
    """
    source = os.path.join(legacy, "voice_profiles")
    registry = os.path.join(source, "profiles.json")
    if not os.path.exists(registry):
        return 0

    try:
        profiles = json.loads(open(registry).read())
    except (OSError, json.JSONDecodeError):
        return 0
    if not profiles:
        return 0

    destination = paths.voices_dir()
    carried = 0
    for profile_id, profile in profiles.items():
        folder = os.path.join(source, profile_id)
        if os.path.isdir(folder):
            shutil.copytree(folder, destination / profile_id, dirs_exist_ok=True)
        # Samples are recorded under their old absolute paths; repoint them.
        for key in ("original_path", "filtered_path"):
            old = profile.get(key)
            if old:
                profile[key] = str(destination / profile_id / os.path.basename(old))
        carried += 1

    merged = {}
    target = destination / "profiles.json"
    if target.exists():
        try:
            merged = json.loads(target.read_text())
        except (OSError, json.JSONDecodeError):
            merged = {}
    merged.update(profiles)
    target.write_text(json.dumps(merged, indent=2))
    return carried


# Media the old layout kept but never referenced from a run's state - the
# stills a thumbnail was built from, generated music beds. Small, but leaving
# them behind means the old directory can never quite be deleted.
_SWEEP_DIRS = ("assets", "music")
_SWEEP_EXTENSIONS = {".mp4", ".mov", ".webm", ".jpg", ".jpeg", ".png", ".webp", ".wav", ".mp3"}


def _sweep_leftover_media(legacy: str) -> int:
    """Adopts any media in the old directory that no run pointed at.

    Migration walks each run's recorded scene assets, which misses everything
    fetched for a purpose the state never wrote down. Sweeping afterwards means
    "the old directory is safe to delete" is actually true.
    """
    import asset_cache

    swept = 0
    for folder in _SWEEP_DIRS:
        source = os.path.join(legacy, folder)
        if not os.path.isdir(source):
            continue
        kind = "music" if folder == "music" else "assets"
        for filename in sorted(os.listdir(source)):
            full = os.path.join(source, filename)
            extension = os.path.splitext(filename)[1].lower()
            if not os.path.isfile(full) or extension not in _SWEEP_EXTENSIONS:
                continue
            temporary = asset_cache.temp_path(extension)
            try:
                shutil.copy2(full, temporary)
                asset_cache.adopt(temporary, extension, kind=kind, source_url="",
                                  query=os.path.splitext(filename)[0][:60])
                swept += 1
            except OSError:
                continue
    return swept


def command_migrate(args) -> int:
    """Moves an old ./runs directory into the current layout.

    Which file belongs to which run is reconstructed from the paths the state
    files already record, so nothing has to be guessed. Anything that cannot be
    attributed is left where it is and reported rather than deleted.
    """
    import asset_cache

    legacy = os.path.abspath(args.source)
    if not os.path.isdir(legacy):
        print(bad(f"No directory at {legacy}"))
        return 1

    # Abandoned runs are still someone's work - a script they may want back -
    # so they come across too rather than being silently left behind.
    states = [(os.path.join(legacy, f), False)
              for f in sorted(os.listdir(legacy)) if f.endswith(".json")]
    abandoned = os.path.join(legacy, "abandoned")
    if os.path.isdir(abandoned):
        states += [(os.path.join(abandoned, f), True)
                   for f in sorted(os.listdir(abandoned)) if f.endswith(".json")]

    profiles_moved = _migrate_voice_profiles(legacy)

    if not states:
        if profiles_moved:
            print(ok(f"\n  carried {profiles_moved} voice profile(s) across\n"))
            return 0
        print(dim(f"\nNothing to migrate in {legacy}\n"))
        return 0

    print(bold(f"\nMigrating {len(states)} project(s) from {legacy}"))
    print(dim("  files are copied, not moved - the old directory is left intact\n"))
    if profiles_moved:
        print(f"  {ok('done')} {profiles_moved} voice profile(s)")

    moved_assets = 0
    for source, was_abandoned in states:
        filename = os.path.basename(source)
        try:
            state = json.loads(open(source).read())
        except (OSError, json.JSONDecodeError):
            print(f"  {warn('skip')} {filename} (unreadable)")
            continue

        run_id = state.get("run_id") or os.path.splitext(filename)[0]
        topic = state.get("topic") or state.get("user_topic") or ""
        project = paths.project_dir(run_id, topic)

        def carry(source_path: str, into) -> str:
            """Copies a file across and returns its new path, or ''."""
            if not source_path:
                return ""
            full = source_path if os.path.isabs(source_path) else os.path.join(os.getcwd(), source_path)
            if not os.path.exists(full):
                return ""
            into.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(full, into)
            return str(into)

        outputs = project / "output"
        outputs.mkdir(parents=True, exist_ok=True)

        # Every recorded path has to be rewritten as the file moves. Leaving
        # the old ones in place would mean the migrated project still pointed
        # into ./runs - so deleting that directory would break it, and the
        # cache would look entirely unreferenced and be eligible for `clean
        # --orphans` while every project still needed it.
        master = carry(os.path.join(legacy, f"{run_id}_final.mp4"), outputs / "master.mp4")
        if master and state.get("video_output"):
            state["video_output"]["video_path"] = master

        short = carry(os.path.join(legacy, "shorts", f"{run_id}_short.mp4"), outputs / "short.mp4")
        if short and state.get("shorts_output"):
            state["shorts_output"]["short_path"] = short

        thumbnails = os.path.join(legacy, "thumbnails")
        moved_thumbs = {}
        if os.path.isdir(thumbnails):
            for thumb in sorted(os.listdir(thumbnails)):
                if not thumb.startswith(run_id):
                    continue
                new = carry(os.path.join(thumbnails, thumb), outputs / thumb.replace(f"{run_id}_", ""))
                if new:
                    moved_thumbs[os.path.join(thumbnails, thumb)] = new
        for entry in (state.get("thumbnails") or {}).get("thumbnails", []):
            replacement = moved_thumbs.get(entry.get("path", ""))
            if replacement:
                entry["path"] = replacement

        voice = (state.get("voice_output") or {}).get("audio_path", "")
        new_voice = carry(voice, project / "voice" / "narration.wav")
        if new_voice:
            state["voice_output"]["audio_path"] = new_voice

        # Downloaded footage goes to the shared cache, where it dedupes across
        # every project that used the same clip, and the project is repointed
        # at the content-addressed copy.
        for scene in (state.get("visual_output") or {}).get("scene_assets", []):
            asset = scene.get("asset_path", "")
            if not asset or not os.path.exists(asset):
                continue
            extension = os.path.splitext(asset)[1] or ".mp4"
            temporary = asset_cache.temp_path(extension)
            shutil.copy2(asset, temporary)
            scene["asset_path"] = asset_cache.adopt(
                temporary, extension, source_url="", query=topic
            )
            moved_assets += 1

        if was_abandoned:
            state.setdefault("history", []).append({
                "state": state.get("current_state", "?"),
                "event": "abandoned",
                "detail": "carried over from runs/abandoned during migration",
            })

        (project / "project.json").write_text(json.dumps(state, indent=2))
        print(f"  {ok('done')} {project.name}" + (dim("  (abandoned)") if was_abandoned else ""))

    swept = _sweep_leftover_media(legacy)
    if swept:
        print(f"  {ok('done')} {swept} leftover media file(s)")

    print(f"\n  {moved_assets + swept} asset(s) added to the cache")
    print(dim(f"  the original {legacy} is untouched; delete it once you have checked\n"))
    return 0


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio.py",
        description="Look after Santa Studio's projects, cache and configuration.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="check this machine is ready to run").set_defaults(func=command_doctor)
    sub.add_parser("where", help="print every path with its size").set_defaults(func=command_where)

    listing = sub.add_parser("ls", help="list projects")
    listing.add_argument("--paths", action="store_true", help="also print each directory")
    listing.set_defaults(func=command_ls)

    remove = sub.add_parser("rm", help="delete one project")
    remove.add_argument("project", help="id fragment, directory name, or topic fragment")
    remove.add_argument("-y", "--yes", action="store_true", help="do not ask")
    remove.set_defaults(func=command_rm)

    clean = sub.add_parser("clean", help="delete regenerable files")
    clean.add_argument("--cache", action="store_true", help="everything in cache/ and tmp/")
    clean.add_argument("--orphans", action="store_true", help="only what no project references")
    clean.add_argument("--force", action="store_true",
                       help="also delete cached files that cannot be downloaded again")
    clean.add_argument("-y", "--yes", action="store_true", help="do not ask")
    clean.set_defaults(func=command_clean)

    collect = sub.add_parser("gc", help="keep only the most recent projects")
    collect.add_argument("--keep", type=int, default=10, help="how many to keep (default 10)")
    collect.add_argument("-y", "--yes", action="store_true", help="do not ask")
    collect.set_defaults(func=command_gc)

    export = sub.add_parser("export", help="zip a project, credentials excluded")
    export.add_argument("project")
    export.add_argument("-o", "--output", help="destination zip")
    export.set_defaults(func=command_export)

    migrate = sub.add_parser("migrate", help="move an old runs/ directory into the current layout")
    migrate.add_argument("--source", default="runs", help="the old directory (default ./runs)")
    migrate.set_defaults(func=command_migrate)

    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
