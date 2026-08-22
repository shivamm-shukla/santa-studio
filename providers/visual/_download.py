"""Shared asset-download helper for the visual providers.

Downloads land in the content-addressed cache rather than in a directory beside
the projects. Two things follow from that: the same clip fetched twice - by a
rerun, a regenerate, or two different URLs pointing at identical bytes - is
stored once, and everything here is disposable, because the index knows where
each file came from and it can be fetched again.
"""

import os

import requests

import asset_cache

# Some hosts reject the default urllib agent outright, so identify properly.
USER_AGENT = "SantaStudio/1.0 (+https://github.com/shivamm-shukla/santa-studio)"
TIMEOUT_SECONDS = 30
CHUNK = 65536


def download_asset(url: str, asset_type: str, query: str) -> str:
    """Fetches `url` into the cache and returns the local path."""
    extension = ".mp4" if asset_type == "video" else ".jpg"

    # The URL index answers before any network call, so a rerun on the same
    # topic costs nothing.
    existing = asset_cache.by_url(url)
    if existing:
        return existing

    # A unique scratch name per download: concurrent scene fetches used to
    # collide on a shared temporary path and corrupt each other's files.
    partial = asset_cache.temp_path(extension)
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            stream=True,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        with open(partial, "wb") as handle:
            for chunk in response.iter_content(chunk_size=CHUNK):
                handle.write(chunk)

        if os.path.getsize(partial) == 0:
            raise RuntimeError(f"{url} returned an empty file")

        # adopt() hashes the bytes, so a file already cached under a different
        # URL is recognised here and the download is discarded.
        return asset_cache.adopt(
            partial, extension, kind="assets", source_url=url, query=query
        )
    finally:
        if os.path.exists(partial):
            try:
                os.remove(partial)
            except OSError:
                pass
