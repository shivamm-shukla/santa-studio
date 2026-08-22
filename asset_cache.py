"""The disposable half of the storage layout: downloads, addressed by content.

Two problems with how assets used to be kept. They were named after the query
that found them plus a hash of the URL, so the same clip reached by two
different URLs was stored twice and nothing could tell that they were the same
file. And nothing ever deleted anything - one directory had grown to 216 MB of
the 310 MB total, with a single 124 MB clip in it, and no way to know which
projects still needed any of it.

Both are fixed by addressing files by the hash of their contents. Identical
bytes land on one path however they were fetched, the index records where each
one came from and when it was last used, and eviction becomes a matter of
deleting the least recently used until the cache is back under its ceiling.

Nothing here is precious. Every file can be fetched again, which is what makes
`clean --cache` safe to suggest and what lets a project record the hash of an
asset rather than a copy of it.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager

import paths

CHUNK = 1 << 16

# Default ceiling before least-recently-used files start being dropped.
DEFAULT_MAX_BYTES = 8 * 1024 * 1024 * 1024  # 8 GB

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    digest      TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    extension   TEXT NOT NULL,
    bytes       INTEGER NOT NULL,
    source_url  TEXT,
    query       TEXT,
    created_at  REAL NOT NULL,
    last_used   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS assets_last_used ON assets(last_used);
CREATE INDEX IF NOT EXISTS assets_source ON assets(source_url);
"""


@contextmanager
def _db():
    connection = sqlite3.connect(paths.cache_index(), timeout=30)
    try:
        connection.executescript(SCHEMA)
        yield connection
        connection.commit()
    finally:
        connection.close()


def hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

def path_for(digest: str, extension: str, kind: str = "assets"):
    return paths.cached_asset(digest, extension, kind)


def by_url(url: str) -> str | None:
    """The cached file previously fetched from `url`, if it is still here.

    Checked before downloading, so a rerun on the same topic costs nothing.
    """
    with _db() as connection:
        row = connection.execute(
            "SELECT digest, extension, kind FROM assets WHERE source_url = ? LIMIT 1", (url,)
        ).fetchone()
    if not row:
        return None

    digest, extension, kind = row
    path = path_for(digest, extension, kind)
    if not path.exists():
        forget(digest)
        return None

    touch(digest)
    return str(path)


def touch(digest: str) -> None:
    """Marks an asset as used now, which is what keeps eviction sensible."""
    with _db() as connection:
        connection.execute("UPDATE assets SET last_used = ? WHERE digest = ?", (time.time(), digest))


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def adopt(temp_path: str, extension: str, kind: str = "assets",
          source_url: str = "", query: str = "") -> str:
    """Moves a freshly downloaded file into the cache and returns its path.

    If the same bytes are already cached the temporary file is discarded and
    the existing path is returned - which is the deduplication, and it happens
    whatever URL the file arrived from.
    """
    digest = hash_file(temp_path)
    destination = path_for(digest, extension, kind)

    if destination.exists() and destination.stat().st_size > 0:
        try:
            os.remove(temp_path)
        except OSError:
            pass
    else:
        os.replace(temp_path, destination)

    size = destination.stat().st_size
    now = time.time()
    with _db() as connection:
        connection.execute(
            """INSERT INTO assets (digest, kind, extension, bytes, source_url, query,
                                   created_at, last_used)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(digest) DO UPDATE SET
                   last_used = excluded.last_used,
                   source_url = COALESCE(NULLIF(assets.source_url, ''), excluded.source_url)""",
            (digest, kind, extension, size, source_url, query, now, now),
        )
    return str(destination)


def temp_path(extension: str) -> str:
    """A scratch path for a download in progress.

    Unique per call: concurrent scene fetches used to collide on a shared
    temporary name and corrupt each other's downloads.
    """
    scratch = paths.tmp_dir()
    return str(scratch / f"download.{uuid.uuid4().hex}{extension}")


def forget(digest: str) -> None:
    with _db() as connection:
        connection.execute("DELETE FROM assets WHERE digest = ?", (digest,))


# --------------------------------------------------------------------------
# Housekeeping
# --------------------------------------------------------------------------

def stats() -> dict:
    with _db() as connection:
        row = connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(bytes), 0) FROM assets"
        ).fetchone()
    count, total = row
    return {"files": count, "bytes": total, "human": paths.human_size(total)}


def evict(max_bytes: int = DEFAULT_MAX_BYTES, protect: set[str] | None = None) -> dict:
    """Drops least-recently-used assets until the cache fits `max_bytes`.

    `protect` is the set of digests projects still reference. Passing it means
    an in-flight run cannot have its own footage deleted out from under it.
    """
    protect = protect or set()
    removed, freed = 0, 0

    with _db() as connection:
        rows = connection.execute(
            "SELECT digest, extension, kind, bytes FROM assets ORDER BY last_used ASC"
        ).fetchall()

    total = sum(row[3] for row in rows)
    for digest, extension, kind, size in rows:
        if total <= max_bytes:
            break
        if digest in protect:
            continue
        try:
            os.remove(path_for(digest, extension, kind))
        except OSError:
            pass
        forget(digest)
        total -= size
        freed += size
        removed += 1

    return {"removed": removed, "freed": freed, "freed_human": paths.human_size(freed)}


def referenced_digests() -> set[str]:
    """Every asset digest any project still points at.

    Read from the projects themselves rather than tracked separately, so a
    project deleted by hand cannot leave a phantom reference keeping files
    alive forever.
    """
    import json

    digests: set[str] = set()
    for project in paths.list_projects():
        for name in ("project.json", "timeline.json"):
            path = project / name
            if not path.exists():
                continue
            try:
                blob = path.read_text()
            except OSError:
                continue
            # Digests appear inside stored paths; find them by shape rather
            # than by walking every schema that might contain one.
            for token in _sha256_tokens(blob):
                digests.add(token)
            try:
                json.loads(blob)
            except json.JSONDecodeError:
                continue
    return digests


def _sha256_tokens(text: str) -> set[str]:
    import re

    return set(re.findall(r"\b[0-9a-f]{64}\b", text))


def orphans() -> list[dict]:
    """Cached files no project references any more."""
    keep = referenced_digests()
    with _db() as connection:
        rows = connection.execute(
            "SELECT digest, extension, kind, bytes, query FROM assets"
        ).fetchall()
    return [
        {"digest": d, "extension": e, "kind": k, "bytes": b, "query": q}
        for d, e, k, b, q in rows
        if d not in keep
    ]


def drop_orphans() -> dict:
    removed, freed = 0, 0
    for entry in orphans():
        try:
            os.remove(path_for(entry["digest"], entry["extension"], entry["kind"]))
        except OSError:
            pass
        forget(entry["digest"])
        removed += 1
        freed += entry["bytes"]
    return {"removed": removed, "freed": freed, "freed_human": paths.human_size(freed)}


def reindex() -> dict:
    """Rebuilds the index from what is actually on disk.

    Needed after a migration, and worth having whenever the index and the
    filesystem disagree - the files are the truth, the index is a convenience.
    """
    seen = 0
    with _db() as connection:
        connection.execute("DELETE FROM assets")
        for kind in ("assets", "music", "models"):
            root = paths.cache_dir(kind)
            for dirpath, _, filenames in os.walk(root):
                for filename in filenames:
                    stem, extension = os.path.splitext(filename)
                    if len(stem) != 64:
                        continue  # not content-addressed; leave it alone
                    full = os.path.join(dirpath, filename)
                    stat = os.stat(full)
                    connection.execute(
                        """INSERT OR REPLACE INTO assets
                           (digest, kind, extension, bytes, source_url, query, created_at, last_used)
                           VALUES (?, ?, ?, ?, '', '', ?, ?)""",
                        (stem, kind, extension, stat.st_size, stat.st_mtime, stat.st_mtime),
                    )
                    seen += 1
    return {"indexed": seen}
