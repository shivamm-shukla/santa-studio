"""Generates candidate thumbnails for the assembled video.

Sources a base image through the existing VisualProvider abstraction -
`search(query, asset_type="image")` is already part of that interface, so
no provider needs a new method - then overlays bold, high-contrast title
text with Pillow. Several variants are produced (different text, crop and
layout) so the approval gate is a real choice rather than a yes/no.
"""

import os
import textwrap

from agents._llm_utils import call_llm_json, language_instruction
from providers.registry import get_provider

OUTPUT_DIR = "runs/thumbnails"
WIDTH, HEIGHT = 1280, 720

SYSTEM = (
    "You write YouTube thumbnail text: three to five words, all caps, "
    "built on a curiosity gap. Not a sentence, not the video title - the "
    "few words that make someone stop scrolling."
)

# Ordered by preference; the first one present on the system wins. PIL's
# built-in bitmap font is the last resort and looks it, but it keeps the
# agent working on a box with no fonts installed rather than failing.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]

# (name, crop anchor, layout) - the crop anchor shifts which part of the
# source image survives the 16:9 crop, so variants differ visually even
# when the provider returns the same image for every query.
VARIANTS = [
    ("bottom-bar", 0.5, "bottom"),
    ("left-block", 0.7, "left"),
    ("center-punch", 0.35, "center"),
]


def _load_font(size: int):
    from PIL import ImageFont

    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def _overlay_texts(topic: str, config: dict) -> list[str]:
    """Three short overlay lines from the LLM, or topic-derived fallbacks."""
    prompt = (
        f"Video topic: {topic!r}\n"
        "Write exactly 3 different YouTube thumbnail overlay texts for it. "
        "Each must be 3-5 words and punchy.\n"
        f"{language_instruction(config)}\n"
        'Respond with ONLY a JSON object: {"texts": ["...", "...", "..."]}'
    )
    try:
        parsed = call_llm_json(get_provider("llm", config), prompt, SYSTEM)
        texts = [str(t).upper() for t in parsed.get("texts", []) if str(t).strip()]
        if len(texts) >= len(VARIANTS):
            return texts[: len(VARIANTS)]
    except Exception:
        pass  # thumbnails must not fail just because the LLM did

    # Fallback: first few words of the topic, which is already a title.
    words = topic.upper().split()
    return [
        " ".join(words[:4]) or "WATCH THIS",
        " ".join(words[:6]) or "WATCH THIS",
        " ".join(words[:3]) or "WATCH THIS",
    ][: len(VARIANTS)]


def _base_image(topic: str, scenes: list[dict], config: dict):
    """A 1280x720-ready source image from the visual provider, or a plain
    dark canvas if no provider returned one."""
    from PIL import Image

    primary = get_provider("visual", config)
    pixabay_cfg = dict(
        config, ACTIVE_PROVIDERS={**config["ACTIVE_PROVIDERS"], "visual": "pixabay"}
    )
    pixabay_fallback = get_provider("visual", pixabay_cfg)
    wikimedia_cfg = dict(
        config, ACTIVE_PROVIDERS={**config["ACTIVE_PROVIDERS"], "visual": "wikimedia"}
    )
    wikimedia_fallback = get_provider("visual", wikimedia_cfg)

    queries = [topic] + [s.get("visual_hint", "") for s in scenes[:2] if s.get("visual_hint")]
    for query in queries:
        for provider in (primary, pixabay_fallback, wikimedia_fallback):
            try:
                result = provider.search(query, asset_type="image")
            except Exception:
                continue
            path = (result or {}).get("asset_path")
            if path and os.path.exists(path):
                try:
                    return Image.open(path).convert("RGB")
                except Exception:
                    continue
    return Image.new("RGB", (WIDTH, HEIGHT), (18, 18, 24))


def _crop_to_frame(image, anchor: float):
    """Center-crops to 16:9 around `anchor` (0=left/top, 1=right/bottom),
    then scales to the thumbnail size."""
    from PIL import Image

    target_ratio = WIDTH / HEIGHT
    w, h = image.size
    if w / h > target_ratio:
        new_w = int(h * target_ratio)
        left = int((w - new_w) * anchor)
        box = (left, 0, left + new_w, h)
    else:
        new_h = int(w / target_ratio)
        top = int((h - new_h) * anchor)
        box = (0, top, w, top + new_h)
    return image.crop(box).resize((WIDTH, HEIGHT), Image.LANCZOS)


def _wrap(text: str, font, draw, max_width: int) -> list[str]:
    for width in range(14, 4, -1):
        lines = textwrap.wrap(text, width=width) or [text]
        if all(draw.textlength(line, font=font) <= max_width for line in lines):
            return lines
    return textwrap.wrap(text, width=8) or [text]


def _draw_variant(image, text: str, layout: str):
    from PIL import Image, ImageDraw

    canvas = image.copy()
    shade = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)

    if layout == "left":
        shade_draw.rectangle([0, 0, int(WIDTH * 0.58), HEIGHT], fill=(0, 0, 0, 190))
        box_width, anchor_x, anchor_y = int(WIDTH * 0.50), int(WIDTH * 0.05), HEIGHT // 2
        font_size, align = 86, "left"
    elif layout == "bottom":
        shade_draw.rectangle([0, int(HEIGHT * 0.60), WIDTH, HEIGHT], fill=(0, 0, 0, 190))
        box_width, anchor_x, anchor_y = int(WIDTH * 0.90), WIDTH // 2, int(HEIGHT * 0.80)
        font_size, align = 92, "center"
    else:  # center
        shade_draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(0, 0, 0, 110))
        box_width, anchor_x, anchor_y = int(WIDTH * 0.86), WIDTH // 2, HEIGHT // 2
        font_size, align = 110, "center"

    canvas = Image.alpha_composite(canvas.convert("RGBA"), shade)
    draw = ImageDraw.Draw(canvas)

    font = _load_font(font_size)
    lines = _wrap(text, font, draw, box_width)
    # Shrink until the wrapped block actually fits the frame vertically.
    while font_size > 34 and len(lines) * font_size * 1.12 > HEIGHT * 0.8:
        font_size -= 8
        font = _load_font(font_size)
        lines = _wrap(text, font, draw, box_width)

    line_height = int(font_size * 1.12)
    y = anchor_y - (len(lines) * line_height) // 2
    for line in lines:
        draw.text(
            (anchor_x, y),
            line,
            font=font,
            fill=(255, 255, 255),
            stroke_width=max(4, font_size // 18),
            stroke_fill=(0, 0, 0),
            anchor="la" if align == "left" else "ma",
        )
        y += line_height

    return canvas.convert("RGB")


def run(input_data: dict, config: dict) -> dict:
    """Input: {topic: str, scenes: list[dict], run_id: str}
    Output: {thumbnails: list[dict]}
    Each: {variant: str, path: str, text: str}
    """
    topic = input_data.get("topic") or "Untitled"
    scenes = input_data.get("scenes") or []
    run_id = input_data.get("run_id", "unknown")

    try:
        source = _base_image(topic, scenes, config)
        texts = _overlay_texts(topic, config)
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        thumbnails = []
        for (name, anchor, layout), text in zip(VARIANTS, texts):
            frame = _crop_to_frame(source, anchor)
            image = _draw_variant(frame, text, layout)
            path = os.path.join(OUTPUT_DIR, f"{run_id}_{name}.jpg")
            image.save(path, "JPEG", quality=88)
            thumbnails.append({"variant": name, "path": path, "text": text})

        return {"success": True, "output": {"thumbnails": thumbnails}, "error": None}
    except Exception as e:
        return {"success": False, "output": None, "error": str(e)}
