import os

import requests

from providers.base import VisualProvider
from providers.visual import matching
from providers.visual._download import download_asset

VIDEO_ENDPOINT = "https://pixabay.com/api/videos/"
IMAGE_ENDPOINT = "https://pixabay.com/api/"


def _description(hit: dict) -> str:
    """What Pixabay says this hit is of: its tags, and its page slug."""
    return " ".join(part for part in (
        str(hit.get("tags") or ""),
        matching.slug_words(hit.get("pageURL") or ""),
    ) if part)


def _most_relevant(query: str, hits: list) -> dict | None:
    scored = [
        (matching.overlap(query, _description(hit)), index, hit)
        for index, hit in enumerate(hits or [])
        if isinstance(hit, dict)
    ]
    if not scored:
        return None
    best_score, _, best = min(scored, key=lambda item: (-item[0], item[1]))
    return best if best_score >= matching.MIN_MATCHES else None


class PixabayProvider(VisualProvider):
    """Pixabay API - free fallback when Pexels has no result for a query.

    Returns an empty asset_path on any failure (missing key, no results,
    network error) rather than raising - and "no results" includes results
    that are not of what was asked for. See providers/visual/matching.py: the
    stock libraries answer every query, so a hit is not on its own evidence
    that anything relevant was found. Pixabay does at least return real tags
    to check against rather than only a page slug.
    """

    def search(self, query: str, asset_type: str = "video") -> dict:
        api_key = os.getenv("PIXABAY_API_KEY", "")
        if not api_key:
            return {"asset_type": asset_type, "asset_path": ""}

        endpoint = VIDEO_ENDPOINT if asset_type == "video" else IMAGE_ENDPOINT
        try:
            response = requests.get(
                endpoint,
                params={"key": api_key, "q": query, "per_page": 10, "safesearch": "true"},
                timeout=15,
            )
            response.raise_for_status()
            hits = response.json().get("hits", [])
            hit = _most_relevant(query, hits)
            if hit is None:
                return {"asset_type": asset_type, "asset_path": ""}

            if asset_type == "video":
                variants = hit.get("videos", {})
                url = (
                    variants.get("medium", {}).get("url")
                    or variants.get("small", {}).get("url")
                    or variants.get("large", {}).get("url")
                )
            else:
                url = hit.get("largeImageURL")

            if not url:
                return {"asset_type": asset_type, "asset_path": ""}

            return {"asset_type": asset_type, "asset_path": download_asset(url, asset_type, query)}
        except requests.RequestException:
            return {"asset_type": asset_type, "asset_path": ""}
