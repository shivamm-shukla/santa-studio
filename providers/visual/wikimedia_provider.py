import os
import requests

from providers.base import VisualProvider
from providers.visual._download import download_asset

WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
USER_AGENT = "SantaStudio/1.0 (contact@santastudio.dev)"


class WikimediaProvider(VisualProvider):
    """Wikimedia Commons API - free, public domain / Creative Commons
    historical photos, paintings, documents, and illustrations.
    Especially powerful for history, science, space, and cultural topics
    where modern stock video platforms lack coverage.
    """

    def search(self, query: str, asset_type: str = "image") -> dict:
        clean_query = query.strip()
        if not clean_query:
            return {"asset_type": asset_type, "asset_path": ""}

        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": f"file:{clean_query}",
            "gsrnamespace": "6",  # 6 = File namespace
            "gsrlimit": 5,
            "prop": "imageinfo",
            "iiprop": "url|thumburl|mime|size",
            "iiurlwidth": 1280,
            "format": "json",
        }
        headers = {"User-Agent": USER_AGENT}

        try:
            response = requests.get(WIKIMEDIA_API, params=params, headers=headers, timeout=12)
            response.raise_for_status()
            data = response.json()

            pages = data.get("query", {}).get("pages", {})
            if not pages:
                # Fallback search without 'file:' prefix
                params["gsrsearch"] = clean_query
                response = requests.get(WIKIMEDIA_API, params=params, headers=headers, timeout=12)
                response.raise_for_status()
                pages = response.json().get("query", {}).get("pages", {})

            for _, page in pages.items():
                imageinfo = page.get("imageinfo", [])
                if not imageinfo:
                    continue
                info = imageinfo[0]
                mime = info.get("mime", "")
                # Prefer images (jpg, png, webp, svg)
                if not mime.startswith("image/"):
                    continue

                url = info.get("thumburl") or info.get("url")
                if url:
                    # Strip extra query params from wikimedia URL if any
                    clean_url = url.split("?")[0]
                    path = download_asset(clean_url, "image", query)
                    if path and os.path.exists(path):
                        return {"asset_type": "image", "asset_path": path}

            return {"asset_type": asset_type, "asset_path": ""}
        except Exception:
            return {"asset_type": asset_type, "asset_path": ""}
