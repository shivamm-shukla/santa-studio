import os

import requests

from providers.base import VisualProvider
from providers.visual._download import download_asset

VIDEO_ENDPOINT = "https://pixabay.com/api/videos/"
IMAGE_ENDPOINT = "https://pixabay.com/api/"


class PixabayProvider(VisualProvider):
    """Pixabay API - free fallback when Pexels has no result for a query.

    Returns an empty asset_path on any failure (missing key, no results,
    network error) rather than raising.
    """

    def search(self, query: str, asset_type: str = "video") -> dict:
        api_key = os.getenv("PIXABAY_API_KEY", "")
        if not api_key:
            return {"asset_type": asset_type, "asset_path": ""}

        endpoint = VIDEO_ENDPOINT if asset_type == "video" else IMAGE_ENDPOINT
        try:
            response = requests.get(
                endpoint,
                params={"key": api_key, "q": query, "per_page": 3, "safesearch": "true"},
                timeout=15,
            )
            response.raise_for_status()
            hits = response.json().get("hits", [])
            if not hits:
                return {"asset_type": asset_type, "asset_path": ""}

            if asset_type == "video":
                variants = hits[0].get("videos", {})
                url = (
                    variants.get("medium", {}).get("url")
                    or variants.get("small", {}).get("url")
                    or variants.get("large", {}).get("url")
                )
            else:
                url = hits[0].get("largeImageURL")

            if not url:
                return {"asset_type": asset_type, "asset_path": ""}

            return {"asset_type": asset_type, "asset_path": download_asset(url, asset_type, query)}
        except requests.RequestException:
            return {"asset_type": asset_type, "asset_path": ""}
