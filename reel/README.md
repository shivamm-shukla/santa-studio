# The demo film

`santa_studio_demo.mp4` is built here. Nothing about it is a screen recording:
every frame is asked for by number, so a machine that renders at two frames a
second still produces a clean thirty.

## Why it works this way

A headless browser rendering this scene at 1080×1920 manages one or two frames
a second. Recording the screen at that rate gives you a recording of a
stuttering machine. So each scene is a pure function of time — seek, settle,
capture — and the result is the same on any machine, just faster or slower to
produce.

The same rule covers the camera, the lights, the page scroll and what is on the
laptop's screen. If it moves, it moves as a function of `t`.

## The pieces

| what | where |
|---|---|
| the studio's shot list | `room/src/world/demo.js` |
| the laptop on a desk | `room/src/laptop/` |
| the film's script (all its words) | `room/src/titles/cards.js` |
| the recorders | `room/reel.mjs`, `room/titles_demo.mjs` |
| the score | `reel/score.py` |
| the mix | `reel/mix.py` |
| the cut | `reel/demo_edit.py` |

Footage lands in `build/demo/<scene>/` as numbered JPEGs. It is gitignored and
reproducible; none of it is precious.

## Building it

The app has to be built and served first — the recorders drive the real thing
over `http://127.0.0.1:8000`, not a mock.

```sh
cd room && node node_modules/.bin/vite build && cd ..
# ...and the server running on :8000

python reel/score.py build/demo/score.wav       # 92 bars, nine movements

cd room
node reel.mjs tour laptop                       # the studio, and the machine
CARDS_JSON="$(node -e '…')" node titles_demo.mjs  # every card
cd ..

python -m reel.demo_edit                        # cut, grade, mix, encode
```

For the act that plays the film the pipeline made, a run has to have finished:

```sh
python -m reel.film_frames                      # explode it onto the screen
# then set SOURCES.film.frames in room/src/laptop/Macbook.jsx
cd room && node reel.mjs film && cd ..
```

## Things that cost an afternoon

**A `VideoTexture` at 1080×1920 loses the WebGL context.** Every run, and a
lost context renders a white page. The laptop's screen is an image sequence
instead — which is also more accurate, because a seeked video lands on the
nearest keyframe and an image sequence lands on the frame you asked for.

**Writing every finished frame to disk fills the disk.** Three minutes of PNG
at this size is about ten gigabytes. It filled the disk far enough to take a
running pipeline down with it, and libsndfile reports a full disk as `System
error`, which is not a helpful thing to read at one in the morning. The editor
pipes raw video straight into ffmpeg and never writes a frame.

**The walls are 4.3 metres.** `sin(pol) * dist` has to stay under about 2.4 from
a target at eye height or the camera climbs over the top of the room and half
the frame is the black outside it.

**`az` is the direction from the target to the camera.** Not the way the panel
faces. Every pose is checked against the face it is looking at rather than
written by eye, because writing them by eye put three different cameras behind
the thing they were meant to be filming.

**Only DejaVu is installed.** So the type is set in the browser, in the
product's own faces, and filmed with a transparent background — not drawn by
ffmpeg's `drawtext`.

## The soundtrack

Synthesised, not licensed. Everything else in this project refuses to use
material it has no right to, and a borrowed track is the one thing that could
get the whole film taken down. It also means the drop can be written to land on
the frame the picture wants it on.

The one recording that is not ours is the Hindi voice sample the demo clones
from: *Hindi Dengue Details*, Wikimedia Commons, CC BY-SA 3.0, credited on
screen.
