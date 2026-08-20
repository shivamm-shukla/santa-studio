import os

import requests

from providers.base import VisualProvider
from providers.visual._download import download_asset

API_BASE = "https://api.pexels.com"


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
                # Prefer a file close to 720p width rather than the largest/smallest.
                best = min(files, key=lambda f: abs(f["width"] - 1280))
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
