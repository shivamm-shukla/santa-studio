import os

import requests

from providers.base import VisualProvider
from providers.visual import matching
from providers.visual._download import download_asset

API_BASE = "https://api.pexels.com"

# Enough candidates to have something to choose between. Pexels reports eight
# thousand results for any query at all, so the first one is not evidence of
# anything and asking for one was the whole problem.
CANDIDATES = 8

TARGET_WIDTH = 1280
TARGET_FPS = 24


def _rendition_cost(video_file: dict) -> tuple:
    """Sort key: smallest rendition that still covers the output size.

    Anything narrower than the target gets upscaled and looks soft, so
    those sort last; among the rest, closest to the target width wins, then
    the lowest frame rate.
    """
    try:
        width = int(video_file.get("width") or 0)
    except (ValueError, TypeError):
        width = 0
    try:
        fps = float(video_file.get("fps") or TARGET_FPS)
    except (ValueError, TypeError):
        fps = float(TARGET_FPS)
    too_small = width < TARGET_WIDTH
    return (too_small, abs(width - TARGET_WIDTH), abs(fps - TARGET_FPS))


def _description(result: dict) -> str:
    """Everything Pexels says this result is of.

    `alt` comes back null on video results, so the page URL does the work: its
    slug is a human-written description with the asset id on the end.
    """
    return " ".join(
        part for part in (
            matching.slug_words(result.get("url") or ""),
            str(result.get("alt") or ""),
            " ".join(str(tag) for tag in (result.get("tags") or []) if tag),
        ) if part
    )


def _most_relevant(query: str, results: list) -> dict | None:
    """The best result that is actually of the subject, or None if none is."""
    scored = [
        (matching.overlap(query, _description(result)), index, result)
        for index, result in enumerate(results)
        if isinstance(result, dict)
    ]
    if not scored:
        return None

    # Ties break towards the library's own ranking, which is what the index is
    # doing in the sort key.
    best_score, _, best = min(scored, key=lambda item: (-item[0], item[1]))
    return best if best_score >= matching.MIN_MATCHES else None


class PexelsProvider(VisualProvider):
    """Pexels API - free, commercially usable stock video/photo search.

    Returns an empty asset_path on any failure (missing key, no results,
    network error) rather than raising - agents/visual_agent.py treats an
    empty asset_path as a signal to fall back to Pixabay.

    "No results" now includes results that are not of what was asked for. The
    library answers everything: a request for a 1919 gold production chart came
    back as a cryptocurrency trading desk, and a request for a mine closure
    notice as signs on a wire fence, both of which were cut into the video. An
    empty path here sends the shot down the chain to generation, which is
    exactly the case generation exists for - a specific place in a specific
    decade that no stock library carries.
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
                params={"query": query, "per_page": CANDIDATES, "orientation": "landscape"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("videos" if asset_type == "video" else "photos", [])
            chosen = _most_relevant(query, results)
            if chosen is None:
                return {"asset_type": asset_type, "asset_path": ""}

            if asset_type == "video":
                files = [f for f in chosen.get("video_files", []) if f.get("width")]
                if not files:
                    return {"asset_type": asset_type, "asset_path": ""}
                url = min(files, key=_rendition_cost).get("link")
            else:
                url = (chosen.get("src") or {}).get("large")

            if not url:
                return {"asset_type": asset_type, "asset_path": ""}

            return {"asset_type": asset_type, "asset_path": download_asset(url, asset_type, query)}
        except Exception:
            return {"asset_type": asset_type, "asset_path": ""}
