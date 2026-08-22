"""Shared asset-download helper for the visual providers."""

import hashlib
import os
import re

import requests

ASSET_DIR = "runs/assets"


def download_asset(url: str, asset_type: str, query: str) -> str:
    os.makedirs(ASSET_DIR, exist_ok=True)
    ext = "mp4" if asset_type == "video" else "jpg"
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower())[:40].strip("-") or "asset"
    # md5, not hash(): Python randomises string hashing per process, so
    # hash() gave the same URL a different filename on every run and the
    # cache below could never hit.
    digest = hashlib.md5(url.encode()).hexdigest()[:10]
    filename = f"{slug}-{digest}.{ext}"
    path = os.path.join(ASSET_DIR, filename)

    # The filename is derived from the URL, so the same clip requested
    # again - a regenerate, a rerun on the same topic - is already here.
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    # Write to a temp name first: a download interrupted halfway would
    # otherwise leave a truncated file that the cache check above then
    # treats as complete forever.
    partial = path + ".part"
    with open(partial, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            f.write(chunk)
    os.replace(partial, path)
    return path
