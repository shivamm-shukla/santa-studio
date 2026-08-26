"""Lays the finished film out as frames the laptop screen can play.

Act seven of the demo shows the video the pipeline actually made, on the same
machine the film opened on. The laptop's screen is driven by an image sequence
rather than a video - see room/src/laptop/Macbook.jsx for why - so the master
has to be exploded into numbered JPEGs under room/public/reel/film/, at the
shape of that screen.

It also pulls the audio out, because the mix plays the film's own sound under
act seven and ffmpeg should not be asked to demux the master twice.

    python -m reel.film_frames                 # finds the newest finished run
    python -m reel.film_frames <path-to-mp4>
"""

import os
import subprocess
import sys

FF = "venv/lib/python3.12/site-packages/imageio_ffmpeg/binaries/ffmpeg-linux-x86_64-v7.0.2"

# The laptop screen is 16:10 and the master is 16:9, so the picture is fitted
# inside with the screen's own black either side rather than cropped - a demo
# that crops the thing being demoed is arguing against itself.
SCREEN_W, SCREEN_H = 1680, 1050
FPS = 30
SECONDS = 30.0                      # more than act seven needs; the rest is spare

OUT_FRAMES = "room/public/reel/film"
OUT_AUDIO = "build/demo/film.mp4"


def newest_master():
    """The most recently finished run's video."""
    import paths

    projects = paths.projects_dir()
    best = None
    for name in os.listdir(projects):
        for candidate in ("output/final.mp4", "output/master.mp4", "output/video.mp4"):
            path = os.path.join(projects, name, candidate)
            if os.path.exists(path):
                when = os.path.getmtime(path)
                if best is None or when > best[0]:
                    best = (when, path)
    if best is None:
        # Fall back to anything mp4 under any output directory.
        for root, _, files in os.walk(projects):
            for f in files:
                if f.endswith(".mp4"):
                    path = os.path.join(root, f)
                    when = os.path.getmtime(path)
                    if best is None or when > best[0]:
                        best = (when, path)
    return best[1] if best else None


def main():
    master = sys.argv[1] if len(sys.argv) > 1 else newest_master()
    if not master or not os.path.exists(master):
        sys.exit("no finished film found - run the pipeline first")
    print("film:", master)

    os.makedirs(OUT_FRAMES, exist_ok=True)
    for stale in os.listdir(OUT_FRAMES):
        os.remove(os.path.join(OUT_FRAMES, stale))
    os.makedirs(os.path.dirname(OUT_AUDIO), exist_ok=True)

    subprocess.run(
        [
            FF, "-y", "-hide_banner", "-loglevel", "error",
            "-t", str(SECONDS), "-i", master,
            "-vf", (
                f"fps={FPS},scale={SCREEN_W}:{SCREEN_H}:force_original_aspect_ratio=decrease,"
                f"pad={SCREEN_W}:{SCREEN_H}:(ow-iw)/2:(oh-ih)/2:color=black"
            ),
            "-q:v", "4",
            # From zero, because the page asks for f00000 first and ffmpeg's
            # image muxer starts at one unless told otherwise - which renders
            # as a black screen and looks like a much deeper problem.
            "-start_number", "0",
            os.path.join(OUT_FRAMES, "f%05d.jpg"),
        ],
        check=True,
    )

    subprocess.run(
        [
            FF, "-y", "-hide_banner", "-loglevel", "error",
            "-t", str(SECONDS), "-i", master,
            "-vn", "-c:a", "aac", "-b:a", "192k", OUT_AUDIO,
        ],
        check=True,
    )

    count = len(os.listdir(OUT_FRAMES))
    print(f"{count} frames -> {OUT_FRAMES}")
    print(f"audio -> {OUT_AUDIO}")
    print(f"set SOURCES.film.frames to {count} in room/src/laptop/Macbook.jsx")
    print("then rebuild: vite copies room/public into room/dist, and the "
          "server only ever serves dist")


if __name__ == "__main__":
    main()
