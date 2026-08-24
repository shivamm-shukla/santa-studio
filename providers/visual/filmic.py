"""The pass that puts a generated still on the same footing as filmed footage.

A generated frame arriving in the cut next to a Pexels clip is obvious for
reasons that have nothing to do with what is in it. It is 1024 pixels wide
where everything around it is 1920. It is clean in a way no lens is: no grain,
no falloff in the corners, no colour fringing at the edges, highlights that
stop dead instead of bleeding. And it carries EXIF naming the model that made
it - a tag that would ship inside the published file.

So every frame that survives the quality gate is finished here. None of this
is decoration; each step replaces something a real camera does and a generator
does not:

* **Resolution.** Scaled to the timeline's 1920x1080 with Lanczos and a light
  unsharp, so the renderer is not scaling it a second time with whatever
  filter it happens to use.
* **Halation.** Real highlights bleed into their surroundings, warm, through
  the film base. Generated ones have hard edges.
* **Grade.** A film toe - blacks lifted off zero, a gentle S through the
  midtones. Digital black at zero is the look of a render.
* **Grain.** Weighted towards the shadows and midtones, where film actually
  puts it, and kept off the highlights.
* **Fringing and falloff.** A pixel of lateral chromatic aberration and a
  little corner darkening. Both are lens defects, and their absence is what
  makes a frame feel drawn.
* **EXIF.** Stripped on save.

Everything is seeded off the cache key, so regenerating a run produces the
same file rather than a differently-grained one, and every step is deliberately
under the threshold where it reads as an effect. The aim is a frame nobody
notices, not a frame that looks filtered.
"""

from __future__ import annotations

import hashlib

import numpy as np
from PIL import Image, ImageFilter

from providers.visual import quality

TARGET_WIDTH, TARGET_HEIGHT = 1920, 1080

# Each of these was raised until it read as an effect and then backed off.
GRAIN_SIGMA = 2.4          # 0-255 scale, before the shadow weighting
HALATION_RADIUS = 14
HALATION_STRENGTH = 0.10
HALATION_TINT = (1.0, 0.62, 0.45)   # warm, the way film base scatters
BLACK_LIFT = 5.0 / 255.0
S_CURVE = 0.18            # how much of the smoothstep is mixed in
SATURATION = 0.94         # pulled back, not pushed
FRINGE_PIXELS = 1.2        # lateral chromatic aberration at the corners
VIGNETTE_STRENGTH = 0.12


def _seed(key: str) -> np.random.Generator:
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


def _fit(image: Image.Image) -> Image.Image:
    """Scaled and centre-cropped to the timeline's frame.

    Cropped rather than padded: a pad would put back the bars the quality pass
    just took off.
    """
    target_ratio = TARGET_WIDTH / TARGET_HEIGHT
    ratio = image.width / max(1, image.height)

    if abs(ratio - target_ratio) > 0.01:
        if ratio > target_ratio:
            width = round(image.height * target_ratio)
            left = (image.width - width) // 2
            image = image.crop((left, 0, left + width, image.height))
        else:
            height = round(image.width / target_ratio)
            top = (image.height - height) // 2
            image = image.crop((0, top, image.width, top + height))

    if image.size != (TARGET_WIDTH, TARGET_HEIGHT):
        image = image.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
        # Upscaling softens; a light unsharp puts back the edge the Lanczos
        # kernel spread, without the halo a heavier one would leave.
        image = image.filter(ImageFilter.UnsharpMask(radius=1.6, percent=55, threshold=3))
    return image


def _halation(pixels: np.ndarray, source: Image.Image) -> np.ndarray:
    """Warm bleed out of the highlights, the way light scatters in film base."""
    luma = np.asarray(source.convert("L"), dtype=np.float32) / 255.0
    mask = np.clip((luma - 0.78) / 0.22, 0.0, 1.0)
    blurred = np.asarray(
        Image.fromarray((mask * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(HALATION_RADIUS)
        ),
        dtype=np.float32,
    ) / 255.0

    tint = np.array(HALATION_TINT, dtype=np.float32)
    return pixels + blurred[:, :, None] * tint * HALATION_STRENGTH


def _grade(pixels: np.ndarray) -> np.ndarray:
    """A film toe and a gentle S, so nothing sits at pure black.

    The S is applied at a fifth strength and the colour pulled slightly back,
    both after looking at the result: run at full strength on all three
    channels it deepened contrast *and* pushed saturation, and a punchy blue
    sky over saturated rust is a graded look, not a photographed one. What
    this is for is the lifted black, not the contrast.
    """
    pixels = BLACK_LIFT + pixels * (1.0 - BLACK_LIFT)
    curved = pixels * pixels * (3.0 - 2.0 * pixels) * S_CURVE + pixels * (1.0 - S_CURVE)
    luma = curved.mean(axis=2, keepdims=True)
    return luma + (curved - luma) * SATURATION


def _grain(pixels: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Luma noise, heaviest in the shadows and midtones as on real stock."""
    luma = pixels.mean(axis=2, keepdims=True)
    weight = 1.0 - np.clip((luma - 0.35) / 0.65, 0.0, 1.0) * 0.75
    noise = rng.normal(0.0, GRAIN_SIGMA / 255.0, size=pixels.shape[:2] + (1,))
    return pixels + noise * weight


def _fringe(pixels: np.ndarray) -> np.ndarray:
    """A pixel of lateral chromatic aberration, zero at centre, most at the edge.

    Every channel is magnified rather than one up and one down, which is the
    same differential and stays inside the frame. Scaling a channel *below* one
    leaves it smaller than the crop, and the missing border comes back as
    zeroes - a strip down the edge of the picture with no blue in it.
    """
    height, width = pixels.shape[:2]
    scale = FRINGE_PIXELS / max(width, height)

    def magnified(channel: np.ndarray, factor: float) -> np.ndarray:
        source = Image.fromarray((np.clip(channel, 0, 1) * 255).astype(np.uint8))
        resized = source.resize(
            (max(width, round(width * factor)), max(height, round(height * factor))),
            Image.BILINEAR,
        )
        left = (resized.width - width) // 2
        top = (resized.height - height) // 2
        cropped = resized.crop((left, top, left + width, top + height))
        return np.asarray(cropped, dtype=np.float32) / 255.0

    out = pixels.copy()
    out[:, :, 0] = magnified(pixels[:, :, 0], 1.0 + scale * 4)
    out[:, :, 1] = magnified(pixels[:, :, 1], 1.0 + scale * 2)
    return out


def _vignette(pixels: np.ndarray) -> np.ndarray:
    """Corner falloff, which every lens has and no generator adds."""
    height, width = pixels.shape[:2]
    y = np.linspace(-1.0, 1.0, height, dtype=np.float32)[:, None]
    x = np.linspace(-1.0, 1.0, width, dtype=np.float32)[None, :]
    radius = np.sqrt(x * x + y * y) / np.sqrt(2.0)
    return pixels * (1.0 - VIGNETTE_STRENGTH * radius[:, :, None] ** 2.2)


def finish(image: Image.Image, key: str = "") -> Image.Image:
    """One generated frame, made to sit beside filmed footage without standing out."""
    image = quality.trim(image).convert("RGB")
    image = _fit(image)

    pixels = np.asarray(image, dtype=np.float32) / 255.0
    pixels = _halation(pixels, image)
    pixels = _grade(pixels)
    pixels = _fringe(pixels)
    pixels = _vignette(pixels)
    pixels = _grain(pixels, _seed(key or "unseeded"))

    return Image.fromarray((np.clip(pixels, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8))


def save(image: Image.Image, path: str) -> None:
    """Written without EXIF.

    What comes back carries the prompt and the model's name in a UserComment
    tag. That is a label saying how the picture was made, travelling inside a
    file that ships in a published video.
    """
    # Rebuilt from raw bytes rather than copied, because a copy carries the
    # info dict the EXIF travels in.
    clean = Image.frombytes(image.mode, image.size, image.tobytes())
    # Saved without `optimize`: its second pass writes through a fixed buffer
    # that a grainy full-frame still overruns, and the encoder fails with a
    # broken data stream rather than a smaller file.
    clean.save(path, quality=94, subsampling=0)
