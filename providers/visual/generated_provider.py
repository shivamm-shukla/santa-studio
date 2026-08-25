"""Generated stills, for the shots stock does not have.

Last link in the visual chain, and deliberately so: a real photograph of the
thing beats a picture of something like it every time. This exists because
research videos keep needing shots no stock library will ever carry - a
specific mine in a specific decade, a street that no longer looks like that.

A generated still used to be one request with one prompt, kept whatever came
back. Three things were wrong with that, all measured rather than assumed:

1. **The prompt was a subject, not a photograph.** Handing the model "a mine
   headframe" leaves the camera to it, and it always makes the same choices.
   `art_direction` writes the brief now, and that alone moved edge detail from
   6 to 15 on the same subject.
2. **The service is not consistent.** The same brief on two seeds returns a
   usable photograph and a soft smear. So several are generated and `quality`
   picks, which is the cheapest quality gain available here.
3. **What came back went straight into the cut.** At 1024 wide, clean, with
   the model's name in its EXIF, sat next to 1920-wide filmed footage.
   `filmic` finishes it first.

Backends, tried in order:

* **Cloudflare Workers AI** - FLUX.1-schnell, Apache-2.0, free tier, needs a
  free account. The real quality upgrade, and off until the account exists.
* **Gemini** - better than what is free, but image generation is *not* on the
  Gemini free tier: a key without billing is refused with `limit: 0`, not with
  a spent allowance. Used only when GEMINI_IMAGE_ENABLED says billing is on.
* **Pollinations** - no key, no account, no quota. What actually runs today,
  and the ceiling we are working against: `model` is accepted and ignored
  (every request comes back tagged `sana`, whatever was asked for), and a
  request for 1280x720 returns 1024x576.

Some shots are refused outright rather than generated badly. A brief whose
subject is a notice, a chart or any other document comes back as invented
paperwork with garbled lettering on it - a fabricated official record about a
real company, cut into a documentary that promises checkable sources. See
`art_direction.refuses`.

Generated *video* is not here and is not planned. There is no free tier for it
at any useful quality, and the motion these stills need comes from the
renderer, which is what the reference channels are doing anyway.

Never raises. An empty asset_path means "nothing found", which is what
agents/visual_agent.py already expects from every provider before it.
"""

import base64
import hashlib
import io
import os
import urllib.parse

import requests
from PIL import Image

from providers.base import VisualProvider
from providers.visual import art_direction, filmic, quality, relevance

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
GEMINI_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
CLOUDFLARE_MODEL = os.getenv(
    "CLOUDFLARE_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell"
)
# schnell is a few-step model and caps at 8. Neurons are charged per step and
# the free tier is 10,000 a day, but generation is the last resort for a shot
# no stock library carries, so a run spends this on a handful of frames rather
# than on all of them - which is worth the best the model does.
CLOUDFLARE_STEPS = max(1, min(8, int(os.getenv("CLOUDFLARE_IMAGE_STEPS", "8"))))

# What we ask for. Pollinations caps below this and returns 1024x576; asking
# for the frame size anyway costs nothing and a better backend will honour it.
WIDTH, HEIGHT = 1280, 720
TIMEOUT_SECONDS = 90

# How many seeds to try before keeping the best. Three is where the return
# flattened in testing, and each one is a round trip on a service with no SLA.
CANDIDATES = max(1, int(os.getenv("GENERATED_IMAGE_CANDIDATES", "3")))

# A candidate this good ends the search without spending the remaining round
# trips. Set at the bottom of the range good art-directed returns measure in,
# so a strong first result is taken and a mediocre one is not.
GOOD_ENOUGH = 13.0

# How much of a candidate's standing rests on being a picture of the right
# thing. Kept to a third on purpose: against this generator even the on-subject
# frames score low in absolute terms, and weighting it any harder would mean no
# frame ever cleared GOOD_ENOUGH and every shot always spent every round trip.
# It is here to order candidates and to catch the plainly wrong one, not to
# decide on its own.
RELEVANCE_WEIGHT = 0.3

_MAGIC = (b"\x89PNG", b"\xff\xd8\xff")


def _looks_like_an_image(data: bytes) -> bool:
    """Cheap guard against a JSON error page arriving with a 200."""
    return bool(data) and data.startswith(_MAGIC)


def _cache_key(backend: str, prompt: str, variation: int) -> str:
    """A stable pseudo-URL, so the same shot is generated once and reused.

    Keyed on the brief rather than on the subject, and that is not a detail:
    keyed on the subject, improving the brief changed nothing that had already
    been generated. Every scene came straight back out of the cache as the
    picture the old prompt made, and the fix looked like it had done nothing.

    The variation is in the key too, because it is part of the brief: scene 3
    and scene 9 asking for the same subject are two different photographs of
    it, and collapsing them to one entry would put one frame in the cut twice.
    """
    digest = hashlib.sha256(f"{backend}:{prompt}:{variation}".encode("utf-8")).hexdigest()[:32]
    return f"generated-image://{backend}/{digest}"


def _from_pollinations(prompt: str, seed: int) -> bytes:
    url = POLLINATIONS_BASE + urllib.parse.quote(prompt, safe="")
    response = requests.get(
        url,
        params={"width": WIDTH, "height": HEIGHT, "nologo": "true", "seed": seed},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content if _looks_like_an_image(response.content) else b""


def _from_cloudflare(prompt: str, _seed: int) -> bytes:
    """FLUX.1-schnell on Workers AI.

    Answers with base64 inside JSON rather than with image bytes, which is why
    this does not share a path with the others.

    The seed is taken and dropped. Workers AI validates the request body
    strictly and refuses an unknown property outright - sending `seed` returns
    400, not a request with the seed ignored - and it does not take `width` or
    `height` either. So every call comes back 1024x1024, and the candidates
    differ because the model is sampling freshly each time rather than because
    we asked for a different seed. What that costs is reproducibility: the same
    shot regenerated is a different picture, which the cache covers, since a
    shot is generated once and reused from then on.

    The square is worth being clear about. Cropped to the timeline's 16:9 it
    leaves 1024x576, which is exactly what the keyless service returns - so
    this backend is a gain in what the picture looks like, not in how many
    pixels of it there are.
    """
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    response = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CLOUDFLARE_MODEL}",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt, "steps": CLOUDFLARE_STEPS},
        timeout=TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    encoded = ((response.json() or {}).get("result") or {}).get("image") or ""
    try:
        return base64.b64decode(encoded)
    except Exception:
        return b""


def _from_gemini(prompt: str, seed: int) -> bytes:
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
    """The generators available right now, best first.

    Both of the good ones are opt-in, for the same reason in two forms: a
    request that cannot succeed is worse than a request not made. Gemini's
    image models refuse a free-tier key outright, and Cloudflare needs an
    account id and a token that either exist or do not.
    """
    available: list[tuple[str, object]] = [("pollinations", _from_pollinations)]

    billing_on = os.getenv("GEMINI_IMAGE_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    if billing_on and os.getenv("GEMINI_API_KEY", ""):
        available.insert(0, ("gemini", _from_gemini))

    if os.getenv("CLOUDFLARE_ACCOUNT_ID", "") and os.getenv("CLOUDFLARE_API_TOKEN", ""):
        available.insert(0, ("cloudflare", _from_cloudflare))

    return available


def _seeds(query: str, variation: int) -> list[int]:
    """The seeds to try, derived from the shot so a rerun repeats it."""
    digest = hashlib.sha256(f"{query}:{variation}".encode("utf-8")).digest()
    first = int.from_bytes(digest[:4], "big") % 1_000_000
    return [(first + step * 7919) % 1_000_000 for step in range(CANDIDATES)]


def _best_candidate(generate, prompt: str, query: str, variation: int):
    """The best usable frame across several seeds, or None if none was usable.

    Returns early on a strong result rather than spending every round trip:
    the seeds are only being sampled because the service is inconsistent, and
    once it has been consistent there is nothing left to sample for.
    """
    best, best_score = None, 0.0

    for seed in _seeds(query, variation):
        try:
            data = generate(prompt, seed)
        except Exception as error:
            # A day's free allowance running out is not the same as a broken
            # backend, and it explains a whole run's worth of pictures getting
            # worse. Said once per shot rather than swallowed, so the drop to
            # the weaker generator is visible in the activity log instead of
            # being deduced later from the video.
            if "429" in str(error) or "too many requests" in str(error).lower():
                try:
                    import runlog

                    runlog.report("Image generator is out of quota; falling back")
                except Exception:
                    pass
            continue
        if not _looks_like_an_image(data):
            continue

        try:
            image = quality.trim(Image.open(io.BytesIO(data)))
            image.load()
        except Exception:
            continue

        ok, _reason = quality.usable(image)
        if not ok:
            continue

        # Whether it is a photograph, and then whether it is a photograph of
        # the right thing. The second question is the one quality cannot ask,
        # and it is unanswerable without a key - in which case fit is None and
        # the ranking is exactly what it was.
        candidate_score = quality.score(image)
        try:
            fit = relevance.score(image, query)
        except Exception:
            # It answers None for everything it cannot do, so this is only
            # reached if the module itself breaks - and this is the end of the
            # visual chain, where an exception costs the whole run a scene
            # that could have been filled.
            fit = None
        if fit is not None:
            if fit < relevance.REJECT_BELOW:
                continue
            candidate_score *= (1.0 - RELEVANCE_WEIGHT) + RELEVANCE_WEIGHT * fit

        if candidate_score > best_score:
            best, best_score = image, candidate_score
        if best_score >= GOOD_ENOUGH:
            break

    return best


class GeneratedImageProvider(VisualProvider):
    """Generates a still when the stock libraries came back empty."""

    def search(self, query: str, asset_type: str = "image", variation: int = 0) -> dict:
        import asset_cache

        empty = {"asset_type": "image", "asset_path": ""}
        query = (query or "").strip()
        if not query:
            return empty

        refusal = art_direction.refuses(query)
        if refusal:
            try:
                import runlog

                runlog.report(f"Not generating {query!r}: {refusal}")
            except Exception:
                pass
            return empty

        prompt = art_direction.brief(query, variation)

        for name, generate in _backends():
            source_url = _cache_key(name, prompt, variation)
            cached = asset_cache.by_url(source_url)
            if cached:
                return {"asset_type": "image", "asset_path": cached}

            image = _best_candidate(generate, prompt, query, variation)
            if image is None:
                continue

            partial = asset_cache.temp_path(".jpg")
            try:
                filmic.save(filmic.finish(image, source_url), partial)
                path = asset_cache.adopt(
                    partial, ".jpg", kind="assets", source_url=source_url, query=query
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
