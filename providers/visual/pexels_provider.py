import os

import requests

from providers.base import VisualProvider
from providers.visual._download import download_asset

API_BASE = "https://api.pexels.com"

TARGET_WIDTH = 1280
TARGET_FPS = 24


def _rendition_cost(video_file: dict) -> tuple:
    """Sort key: smallest rendition that still covers the output size.

    Anything narrower than the target gets upscaled and looks soft, so
    those sort last; among the rest, closest to the target width wins, then
    the lowest frame rate.
    """
    width = video_file.get("width") or 0
    fps = video_file.get("fps") or TARGET_FPS
    too_small = width < TARGET_WIDTH
    return (too_small, abs(width - TARGET_WIDTH), abs(fps - TARGET_FPS))


class PexelsProvider(VisualProvider):
    """Pexels API - free, commercially usable stock video/photo search.

    Returns an empty asset_path on any failure (missing key, no results,
    network error) rather than raising - agents/visual_agent.py treats an
    empty asset_path as a signal to fall back to Pixabay.
    """

    def search(self, query: str, asset_type: str = "video") -> dict:
        api_key = os.getenv("PEXELS_API_KEY", "")
        if not api_key:
            return {"asset_type": asset_type, "asset_path": ""}

        endpoint = f"{API_BASE}/videos/search" if asset_type == "video" else f"{API_BASE}/v1/search"
        try:
            response = requests.get(
                endpoint,
                headers={"Authorization": api_key},
                params={"query": query, "per_page": 1, "orientation": "landscape"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            if asset_type == "video":
                videos = data.get("videos", [])
                if not videos:
                    return {"asset_type": asset_type, "asset_path": ""}
                files = [f for f in videos[0].get("video_files", []) if f.get("width")]
                if not files:
                    return {"asset_type": asset_type, "asset_path": ""}
                # The render is 1280x720 at 24fps, so anything wider or
                # smoother is bytes we download and then throw away - which
                # on a slow connection is the slowest stage of the whole
                # pipeline. Prefer the smallest rendition that still covers
                # 720p, and the lowest frame rate among equals.
                best = min(files, key=_rendition_cost)
                url = best.get("link")
            else:
                photos = data.get("photos", [])
                if not photos:
                    return {"asset_type": asset_type, "asset_path": ""}
                url = photos[0].get("src", {}).get("large")

            if not url:
                return {"asset_type": asset_type, "asset_path": ""}

            return {"asset_type": asset_type, "asset_path": download_asset(url, asset_type, query)}
        except requests.RequestException:
            return {"asset_type": asset_type, "asset_path": ""}
