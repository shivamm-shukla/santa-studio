"""Generated stills, for the shots stock does not have.

Last link in the visual chain, and deliberately so: a real photograph of the
thing beats a picture of something like it every time. This exists because
research videos keep needing shots no stock library will ever carry - a
specific mine in a specific decade, a street that no longer looks like that.

Two backends, tried in order, because what is free changed under us:

* **Pollinations** - no key, no account, no quota to manage. What runs today.
* **Gemini** - better images, but image generation is *not* on the Gemini free
  tier: a key without billing enabled is refused with `limit: 0`, not with a
  spent allowance. Used only when GEMINI_IMAGE_ENABLED says billing is on.

Generated *video* is not here and is not planned. There is no free tier for it
at any useful quality, and the motion these stills need comes from the
renderer, which is what the reference channels are doing anyway.

Never raises. An empty asset_path means "nothing found", which is what
agents/visual_agent.py already expects from every provider before it.
"""

import hashlib
import os
import urllib.parse

import requests

from providers.base import VisualProvider

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
GEMINI_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")

WIDTH, HEIGHT = 1280, 720
TIMEOUT_SECONDS = 90

# What separates a usable documentary still from an obviously generated one.
# Written as camera direction rather than as the word "realistic", because
# asking for realism by name reliably produces the opposite.
PROMPT = (
    "A photorealistic documentary photograph: {query}. "
    "Natural available light, real depth of field, authentic materials and "
    "wear, colour and grain consistent with a full-frame camera. "
    "No text, no captions, no watermarks, no logos, no borders, no collage, "
    "no illustration or 3D-render look."
)

_MAGIC = (b"\x89PNG", b"\xff\xd8\xff")


def _looks_like_an_image(data: bytes) -> bool:
    """Cheap guard against a JSON error page arriving with a 200."""
    return bool(data) and data.startswith(_MAGIC)


def _cache_key(backend: str, query: str) -> str:
    """A stable pseudo-URL, so the same prompt is generated once and reused.

    Quota and latency are the scarce resources, not disk, and a regenerate on
    the same topic should not spend either twice.
    """
    digest = hashlib.sha256(f"{backend}:{query}".encode("utf-8")).hexdigest()[:32]
    return f"generated-image://{backend}/{digest}"


def _from_pollinations(prompt: str) -> bytes:
    url = POLLINATIONS_BASE + urllib.parse.quote(prompt, safe="")
    response = requests.get(
        url,
        params={"width": WIDTH, "height": HEIGHT, "nologo": "true"},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content if _looks_like_an_image(response.content) else b""


def _from_gemini(prompt: str) -> bytes:
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
    response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)

    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            data = getattr(getattr(part, "inline_data", None), "data", None)
            if data:
                return data
    return b""


def _backends() -> list[tuple[str, object]]:
    """The generators available right now, best last-resort first.

    Gemini is opt-in because its image models are not on the free tier: a key
    without billing is refused outright, and burning a retry on a request that
    cannot succeed is worse than not making it.
    """
    available: list[tuple[str, object]] = [("pollinations", _from_pollinations)]
    billing_on = os.getenv("GEMINI_IMAGE_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    if billing_on and os.getenv("GEMINI_API_KEY", ""):
        available.insert(0, ("gemini", _from_gemini))
    return available


class GeneratedImageProvider(VisualProvider):
    """Generates a still when the stock libraries came back empty."""

    def search(self, query: str, asset_type: str = "image") -> dict:
        import asset_cache

        empty = {"asset_type": "image", "asset_path": ""}
        query = (query or "").strip()
        if not query:
            return empty

        prompt = PROMPT.format(query=query)

        for name, generate in _backends():
            source_url = _cache_key(name, query)
            cached = asset_cache.by_url(source_url)
            if cached:
                return {"asset_type": "image", "asset_path": cached}

            try:
                data = generate(prompt)
            except Exception:
                continue
            if not _looks_like_an_image(data):
                continue

            extension = ".png" if data.startswith(b"\x89PNG") else ".jpg"
            partial = asset_cache.temp_path(extension)
            try:
                with open(partial, "wb") as handle:
                    handle.write(data)
                path = asset_cache.adopt(
                    partial, extension, kind="assets", source_url=source_url, query=query
                )
            except Exception:
                continue
            finally:
                if os.path.exists(partial):
                    try:
                        os.remove(partial)
                    except OSError:
                        pass

            return {"asset_type": "image", "asset_path": path}

        return empty
