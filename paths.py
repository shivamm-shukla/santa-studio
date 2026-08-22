"""Every path the studio writes to, resolved in one place.

Nothing else in the codebase should build a storage path by hand. Before this
module, a dozen files each hardcoded their own relative directory
(``ASSET_DIR = "runs/assets"`` and friends) at import time, which meant the
whole library was implicitly relative to whatever directory you happened to
launch from - start the web app from somewhere else and it would quietly begin
a second, empty library there.

Layout is split by *lifecycle*, not by file type, so it is obvious what is safe
to delete:

    projects/   your work            - precious
    library/    voices, styles       - precious, reused across projects
    cache/      downloads, models    - disposable, regenerates on demand
    config/     credentials          - secret, never in a shared archive
    tmp/        scratch              - cleared on startup

Resolution order for the base directory:

    1. $SANTA_STUDIO_HOME              explicit override, always wins
    2. platform convention             XDG / Application Support / LOCALAPPDATA
    3. never the current directory

Paths are resolved through functions rather than module-level constants so that
a test (or a caller that sets SANTA_STUDIO_HOME late) gets the directory that is
configured *now*, not the one that happened to be configured at import time.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
import unicodedata
from datetime import date
from pathlib import Path

APP_NAME = "santa-studio"

# Subdirectories that must exist before anything writes into them. Grouped by
# lifecycle - see the module docstring.
_TREE = (
    "projects",
    "library/voices",
    "library/styles",
    "cache/assets",
    "cache/music",
    "cache/models",
    "cache/llm",
    "config/credentials",
    "tmp",
)

# What `clean` is allowed to remove without asking, and what it must never
# touch. Kept here rather than in the CLI so the rule lives next to the layout
# it describes.
DISPOSABLE = ("cache", "tmp")
PRECIOUS = ("projects", "library")
SECRET = ("config",)


def _platform_default() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "SantaStudio"
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
        return Path(base) / "SantaStudio"
    # Linux, BSD, and anything else POSIX-ish.
    base = os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def home() -> Path:
    """The studio's base directory. Created on first call."""
    override = os.environ.get("SANTA_STUDIO_HOME")
    root = Path(override).expanduser() if override else _platform_default()
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_tree() -> Path:
    """Creates the full directory tree and returns the base directory."""
    root = home()
    for leaf in _TREE:
        (root / leaf).mkdir(parents=True, exist_ok=True)
    return root


# --------------------------------------------------------------------------
# Top-level directories
# --------------------------------------------------------------------------

def projects_dir() -> Path:
    return ensure_tree() / "projects"


def voices_dir() -> Path:
    return ensure_tree() / "library" / "voices"


def styles_dir() -> Path:
    return ensure_tree() / "library" / "styles"


def cache_dir(kind: str = "") -> Path:
    """``cache_dir("assets")`` -> the asset cache. No argument -> cache root."""
    root = ensure_tree() / "cache"
    if not kind:
        return root
    if kind not in {"assets", "music", "models", "llm"}:
        raise ValueError(f"Unknown cache kind {kind!r}")
    return root / kind


def config_dir() -> Path:
    return ensure_tree() / "config"


def credentials_dir() -> Path:
    """Secrets live here and nowhere else, so `export` can exclude them by
    construction rather than by remembering to."""
    return ensure_tree() / "config" / "credentials"


def tmp_dir() -> Path:
    return ensure_tree() / "tmp"


def clear_tmp() -> None:
    """Empties the scratch directory. Safe to call at startup."""
    scratch = tmp_dir()
    for child in scratch.iterdir():
        try:
            shutil.rmtree(child) if child.is_dir() else child.unlink()
        except OSError:
            pass  # a file another process still holds open is not worth failing over


# --------------------------------------------------------------------------
# Projects
# --------------------------------------------------------------------------

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def _to_ascii(text: str) -> str:
    """Romanises `text` as best the environment allows.

    Topics are routinely Hinglish and often arrive in Devanagari. Stripping
    non-ASCII outright turns "टीपू सुल्तान के रॉकेट" into an empty string and
    the project ends up named `untitled`, which defeats the point of readable
    directory names for the language this is mostly used in. anyascii (ISC,
    pure Python, no dependencies of its own) transliterates it to
    "tipu sultan ke roket" instead. It is listed in requirements.txt, but the
    fallback keeps this module importable without it.
    """
    try:
        from anyascii import anyascii
    except ImportError:
        return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return anyascii(text)


def slugify(text: str, max_length: int = 48) -> str:
    """A filesystem-safe, readable fragment of a topic."""
    slug = _SLUG_STRIP.sub("-", _to_ascii(text).lower()).strip("-")
    if len(slug) > max_length:
        # Cut at a word boundary so the name stays readable.
        slug = slug[:max_length].rsplit("-", 1)[0]
    return slug or "untitled"


def project_name(run_id: str, topic: str = "", created: date | None = None) -> str:
    """``2026-08-22_tipu-sultan-rockets_3ce37bad``

    Date first so a plain directory listing is chronological, topic second so
    you can find a project by reading or grepping, short id last so two runs on
    the same topic never collide.
    """
    day = (created or date.today()).isoformat()
    return f"{day}_{slugify(topic or 'untitled')}_{run_id[:8]}"


def project_dir(run_id: str, topic: str = "", create: bool = True) -> Path:
    """The directory for a run, looked up by id and created if missing.

    The stored name embeds the topic, but the id is the only stable key - a
    topic can be edited at a review gate after the directory already exists.
    So an existing directory is always preferred over a freshly derived name.
    """
    existing = find_project(run_id)
    if existing is not None:
        return existing
    path = projects_dir() / project_name(run_id, topic)
    if create:
        for leaf in ("voice", "output"):
            (path / leaf).mkdir(parents=True, exist_ok=True)
    return path


def find_project(run_id: str) -> Path | None:
    """Locates an existing project directory by run id, or None."""
    if not run_id:
        return None
    suffix = f"_{run_id[:8]}"
    for child in projects_dir().iterdir():
        if child.is_dir() and child.name.endswith(suffix):
            return child
    return None


def list_projects() -> list[Path]:
    """Project directories, newest first by name (names start with the date)."""
    return sorted(
        (p for p in projects_dir().iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )


def state_file(run_id: str, topic: str = "") -> Path:
    return project_dir(run_id, topic) / "project.json"


def timeline_file(run_id: str, topic: str = "") -> Path:
    return project_dir(run_id, topic) / "timeline.json"


def output_dir(run_id: str, topic: str = "") -> Path:
    path = project_dir(run_id, topic) / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_dir(run_id: str, topic: str = "") -> Path:
    path = project_dir(run_id, topic) / "voice"
    path.mkdir(parents=True, exist_ok=True)
    return path


# --------------------------------------------------------------------------
# Content-addressed cache
# --------------------------------------------------------------------------

def cached_asset(digest: str, extension: str, kind: str = "assets") -> Path:
    """Path for a cached download, addressed by content hash.

    Sharded two levels deep (``ab/cd/<digest>.mp4``) because a flat directory
    of tens of thousands of files is slow to list on most filesystems. Naming
    by digest means the same stock clip pulled for three different projects is
    stored once, and re-downloading it is a no-op.
    """
    if len(digest) < 4:
        raise ValueError(f"Digest {digest!r} is too short to shard")
    ext = extension if extension.startswith(".") else f".{extension}"
    path = cache_dir(kind) / digest[:2] / digest[2:4]
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{digest}{ext}"


def cache_index() -> Path:
    """SQLite index mapping digest -> source url, size, last_used. Lets
    `clean --orphans` and LRU eviction work without re-hashing the world."""
    return cache_dir() / "index.db"


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def _dir_size(path: Path) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass  # vanished mid-walk; not worth failing a size report over
    return total


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def usage() -> dict:
    """Per-directory sizes, for `santa-studio where` and the doctor check."""
    root = ensure_tree()
    report = {"home": str(root), "total": 0, "directories": {}}
    for name in ("projects", "library", "cache", "config", "tmp"):
        size = _dir_size(root / name)
        lifecycle = (
            "disposable" if name in DISPOSABLE
            else "secret" if name in SECRET
            else "precious"
        )
        report["directories"][name] = {
            "path": str(root / name),
            "bytes": size,
            "human": human_size(size),
            "lifecycle": lifecycle,
        }
        report["total"] += size
    report["total_human"] = human_size(report["total"])
    return report
