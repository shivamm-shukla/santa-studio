"""Whether a generated frame is a photograph of the right thing.

`quality` can tell a photograph from a soft smear, and that is all it can tell.
It scored a lit tunnel and a colonial bungalow as strong frames when the brief
asked for a mine headframe, because by every measure it takes - texture,
exposure, tonal range - they are strong frames. Subject drift is the largest
remaining hole in generated visuals and nothing in the pipeline could see it.

A vision model can. Image *understanding* is on the Gemini free tier even
though image *generation* is not, which is the one useful asymmetry in that
account: the key already on this machine cannot make a picture and can read
one.

Two things this deliberately does not do:

* **It does not veto.** Asked whether a frame "shows an abandoned gold mine
  headframe", the model says no to every frame the free generator produces -
  correctly, since none of them has a winding wheel on it. A gate that strict
  rejects everything and leaves the scene blank, which is worse than an
  approximate picture. So it scores, the score ranks candidates, and only a
  frame of a plainly different subject is refused.
* **It does not block.** No key, a quota, a bad reply - all return None, and
  the caller ranks on picture quality alone, exactly as before this existed.
"""

from __future__ import annotations

import io
import json
import os
import re

from PIL import Image

# Vision, not generation: this one is free, and it is a different model from
# the image generator in providers/visual/generated_provider.py.
VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-3.1-flash-lite")

# Below this the frame is of something else. Deliberately low - see the note
# above about what a strict gate costs.
REJECT_BELOW = 0.2

# The model does not need the finished frame to say what is in it, and a
# smaller one is a smaller share of a free quota.
ASK_WIDTH = 768

PROMPT = (
    'A documentary needs a photograph of: "{subject}".\n'
    "How well does this image serve that? Reply only with JSON: "
    '{{"score": 0-10, "is": "<what it shows, six words>"}}\n'
    "10 = exactly that. 6 = the right kind of thing, close enough to cut. "
    "3 = a related subject but the wrong thing. 0 = unrelated."
)


def available() -> bool:
    """Whether there is any point calling this."""
    if os.getenv("VISUAL_RELEVANCE_CHECK", "").strip().lower() in {"0", "false", "no"}:
        return False
    return bool(os.getenv("GEMINI_API_KEY", ""))


def _parse(text: str) -> float | None:
    """The score out of the reply, however it was wrapped.

    Models fence JSON in markdown about half the time and there is no setting
    that reliably stops it, so the fence is stripped rather than argued with.
    """
    stripped = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        score = float(json.loads(stripped).get("score"))
    except Exception:
        return None
    return max(0.0, min(1.0, score / 10.0))


def _jpeg(image: Image.Image) -> bytes:
    """The frame as JPEG bytes, small, whatever the backend handed back.

    Re-encoded rather than passed through, so the declared mime type is always
    the truth - a backend that answers in PNG would otherwise be sent as JPEG.
    """
    if image.width > ASK_WIDTH:
        height = max(1, round(image.height * ASK_WIDTH / image.width))
        image = image.resize((ASK_WIDTH, height), Image.BILINEAR)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=82)
    return buffer.getvalue()


def score(image: Image.Image, subject: str) -> float | None:
    """How well this frame serves `subject`, 0 to 1, or None if unanswerable."""
    if not available() or image is None or not (subject or "").strip():
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
        response = client.models.generate_content(
            model=VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=_jpeg(image), mime_type="image/jpeg"),
                PROMPT.format(subject=subject.strip()),
            ],
        )
        return _parse(getattr(response, "text", "") or "")
    except Exception:
        return None
