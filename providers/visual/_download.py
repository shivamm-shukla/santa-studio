"""Shared asset-download helper for the visual providers."""

import os
import re

import requests

ASSET_DIR = "runs/assets"


def download_asset(url: str, asset_type: str, query: str) -> str:
    os.makedirs(ASSET_DIR, exist_ok=True)
    ext = "mp4" if asset_type == "video" else "jpg"
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower())[:40].strip("-") or "asset"
    filename = f"{slug}-{abs(hash(url)) % 100000}.{ext}"
    path = os.path.join(ASSET_DIR, filename)

    response = requests.get(url, stream=True, timeout=30)
    response.raise_for_status()
    with open(path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    return path
