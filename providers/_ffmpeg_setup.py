"""Ensures `ffmpeg` and `ffprobe` are resolvable on PATH before any provider
that shells out to them (Whisper, MoviePy, pydub) runs. No system install
(and therefore no sudo) is required - static-ffmpeg fetches and caches
standalone binaries via pip, which this module exposes as `ffmpeg` and
`ffprobe` on PATH.
"""

import os
import shutil
import tempfile

_SHIM_DIR = os.path.join(tempfile.gettempdir(), "santa-studio-ffmpeg-shim")


def ensure_ffmpeg_on_path() -> None:
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return

    try:
        import static_ffmpeg
    except ImportError:
        return  # let the caller's own error message explain what's missing

    ffmpeg_bin, ffprobe_bin = static_ffmpeg.run.get_or_fetch_platform_executables_else_raise()

    os.makedirs(_SHIM_DIR, exist_ok=True)
    for name, real_path in (("ffmpeg", ffmpeg_bin), ("ffprobe", ffprobe_bin)):
        shim_path = os.path.join(_SHIM_DIR, name)
        if os.path.lexists(shim_path):
            try:
                if os.path.realpath(shim_path) == os.path.realpath(real_path):
                    continue
                os.remove(shim_path)
            except OSError:
                pass
        try:
            os.symlink(real_path, shim_path)
        except FileExistsError:
            pass

    if _SHIM_DIR not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = _SHIM_DIR + os.pathsep + os.environ.get("PATH", "")

    # If pydub was already imported, ensure it points directly to the ffmpeg executable
    try:
        import sys
        if "pydub" in sys.modules:
            import pydub
            pydub.AudioSegment.converter = os.path.join(_SHIM_DIR, "ffmpeg")
    except Exception:
        pass
