"""What a renderer has to be able to do, and how one is chosen.

The interface is deliberately tiny: hand it a Timeline, get back a path to a
file. Everything a renderer needs is already in the Timeline, which is what
makes swapping one for another a configuration change rather than a rewrite -
the same reason agents talk to providers through an interface instead of
importing them.

MoviePy is the implementation that exists today. An FFmpeg filtergraph renderer
is the planned second one, for when render time on long videos starts to hurt.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class Renderer(ABC):
    """Turns a Timeline into a video file."""

    name = "base"

    @abstractmethod
    def render(
        self,
        timeline,
        output_path: str,
        progress: Callable[[str, float], None] | None = None,
    ) -> str:
        """Writes `timeline` to `output_path` and returns the path.

        `progress` is called with a stage name and a 0..1 fraction. Rendering a
        twenty minute video takes long enough that a caller with a UI needs
        something to show, and long enough that a caller without one needs to
        know it has not hung.
        """
        ...


_RENDERERS: dict[str, type[Renderer]] = {}


def register(name: str, renderer: type[Renderer]) -> None:
    _RENDERERS[name] = renderer


def get_renderer(name: str = "moviepy") -> Renderer:
    if name not in _RENDERERS:
        # Imported here rather than at module scope so that importing the
        # interface does not drag MoviePy (and its FFmpeg probing) into a
        # process that only wants to read a Timeline.
        if name == "moviepy":
            from render.moviepy_renderer import MoviePyRenderer  # noqa: F401
    try:
        return _RENDERERS[name]()
    except KeyError:
        raise ValueError(
            f"No renderer named {name!r}. Available: {', '.join(sorted(_RENDERERS)) or 'none'}"
        )
