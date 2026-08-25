"""How far away each pixel is, so a still can be moved like a scene.

A push-in on a flat photograph moves every pixel at the same rate, which is
exactly what a photograph of a photograph looks like. Real depth means the
foreground crosses the frame faster than the background - and to do that you
have to know which is which.

Depth Anything V2 Small answers that: about a hundred megabytes of weights,
and 1.4 seconds on this machine's CPU for a 1920x1080 still, measured. That is
cheap enough to run per shot and far too slow to run per frame, so the map is
computed once and cached beside the picture it belongs to.

Returns None rather than raising, on every path. A still with no depth map is
rendered with the flat Ken Burns move it would have had anyway, which is the
behaviour this is an improvement on rather than a replacement for.
"""

from __future__ import annotations

import hashlib
import os

import numpy as np
from PIL import Image

MODEL = os.getenv("DEPTH_MODEL", "depth-anything/Depth-Anything-V2-Small-hf")

# The map is only used to separate planes, so it does not need the picture's
# resolution - and estimating at this width keeps the model's own cost down.
WORK_WIDTH = 768

_model = None
_processor = None


def _load():
    """The model, loaded once per process, or None if it cannot be had.

    Off by default in the sense that nothing here installs anything: if the
    weights are not present and cannot be fetched, every caller falls back to
    a flat move.
    """
    global _model, _processor
    if _model is not None:
        return _processor, _model
    try:
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        _processor = AutoImageProcessor.from_pretrained(MODEL)
        _model = AutoModelForDepthEstimation.from_pretrained(MODEL)
        _model.eval()
        torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
    except Exception:
        _processor, _model = None, None
    return _processor, _model


def _cache_path(image_path: str) -> str:
    import paths

    digest = hashlib.sha256(image_path.encode("utf-8")).hexdigest()[:32]
    directory = paths.cache_dir("depth")
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, f"{digest}.png")


def estimate(image: Image.Image) -> np.ndarray | None:
    """A 0..1 map the size of `image`, 1 being nearest, or None."""
    processor, model = _load()
    if model is None:
        return None

    try:
        import torch

        working = image.convert("RGB")
        if working.width > WORK_WIDTH:
            height = max(1, round(working.height * WORK_WIDTH / working.width))
            working = working.resize((WORK_WIDTH, height), Image.BILINEAR)

        with torch.no_grad():
            inputs = processor(images=working, return_tensors="pt")
            predicted = model(**inputs).predicted_depth

        depth = torch.nn.functional.interpolate(
            predicted[None], size=(image.height, image.width), mode="bicubic",
            align_corners=False,
        )[0, 0].numpy()
    except Exception:
        return None

    span = float(depth.max() - depth.min())
    if span <= 1e-6:
        return None
    return ((depth - depth.min()) / span).astype(np.float32)


def for_image(path: str) -> np.ndarray | None:
    """The depth map for a still on disk, computed once and kept.

    Cached as a PNG rather than as an array: it is a greyscale image, the
    format is already a dependency, and eight bits is more precision than
    separating three or four planes can use.
    """
    cached = _cache_path(path)
    if os.path.exists(cached):
        try:
            with Image.open(cached) as stored:
                return np.asarray(stored.convert("L"), dtype=np.float32) / 255.0
        except Exception:
            pass

    try:
        with Image.open(path) as image:
            image.load()
            depth = estimate(image)
    except Exception:
        return None

    if depth is None:
        return None

    try:
        Image.fromarray((depth * 255).astype(np.uint8)).save(cached)
    except Exception:
        pass
    return depth
