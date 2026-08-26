/* Films the studio, a frame at a time.

   Not a screen recording. The camera follows the shot list in
   src/world/film.js, which is a pure function of time, so every frame is asked
   for by number: seek to t, let the scene settle, capture. A headless browser
   under software GL renders far slower than real time - that would ruin a
   recording and does nothing at all here, because no frame depends on how long
   the last one took. The result is a clean 30fps whatever the machine does.

   Vertical, because it is going out as a reel.

     node film.mjs               the whole film
     node film.mjs 12 18         only the seconds between 12 and 18

   Frames land in ../build/film/ as PNGs for ffmpeg to assemble. */

import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const FPS = 30;
const WIDTH = 1080;
const HEIGHT = 1920;
const OUT = path.resolve("../build/film");
const BASE = "http://127.0.0.1:8000/room/?film=1";

// Every scene has a little motion of its own - a blinking record light, a
// ticking clock. This many milliseconds after a seek is enough for the panels
// to have repainted and for one animation frame to have run.
const SETTLE = 45;

const [fromArg, toArg] = process.argv.slice(2);

fs.mkdirSync(OUT, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: "new",
  args: [
    "--no-sandbox",
    // A profile of its own, so a recorder that gets killed cannot leave a
    // lock behind that stops the next one launching at all.
    `--user-data-dir=/tmp/santa-chrome-${process.pid}`,
    /* Real GL against the card at /dev/dri, not SwiftShader. Software
       rendering a vertical 1080 frame of this scene takes seconds; the GPU
       takes a fraction of one, and there is a GPU right there. */
    /* Native GL through ANGLE, against the card at /dev/dri. SwiftShader
       renders a vertical 1080 frame of this scene in seconds; this does it in
       a fraction of one. --use-gl=egl looks like the same thing and is not -
       it produced no WebGL context at all, which is what a reel of forty-five
       identical black frames turned out to be. */
    "--use-gl=angle",
    "--use-angle=gl",
    "--enable-gpu-rasterization",
    "--ignore-gpu-blocklist",
    "--hide-scrollbars",
    `--window-size=${WIDTH},${HEIGHT}`,
  ],
});

const page = await browser.newPage();
await page.setViewport({ width: WIDTH, height: HEIGHT, deviceScaleFactor: 1 });
await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });

// The first paint of a WebGL scene includes compiling every shader in it.
await new Promise((r) => setTimeout(r, 6000));

/* The app publishes its own length on window when film mode starts, because
   the bundle is content-hashed and cannot be imported here by name. Getting
   this wrong is expensive: the first run filmed fourteen seconds past the end
   of the shot list, which is four hundred identical frames of the last one. */
const total = await page.evaluate(() => window.__filmSeconds ?? null) ?? 30.6;
const start = fromArg ? Number(fromArg) : 0;
const end = toArg ? Number(toArg) : total;

const first = Math.round(start * FPS);
const last = Math.round(end * FPS);
console.log(`filming ${start}s -> ${end}s  (${last - first} frames at ${FPS}fps, ${WIDTH}x${HEIGHT})`);

const began = Date.now();
for (let frame = first; frame < last; frame += 1) {
  const t = frame / FPS;
  await page.evaluate((time) => window.__filmSeek(time), t);
  await new Promise((r) => setTimeout(r, SETTLE));
  await page.screenshot({ path: path.join(OUT, `f${String(frame).padStart(5, "0")}.png`) });

  if ((frame - first) % 30 === 0) {
    const done = frame - first + 1;
    const rate = done / ((Date.now() - began) / 1000);
    const left = Math.round((last - frame) / rate);
    console.log(`  ${t.toFixed(1)}s  ${done}/${last - first}  ${rate.toFixed(1)} fps  ~${left}s left`);
  }
}

await browser.close();
console.log(`done in ${Math.round((Date.now() - began) / 1000)}s -> ${OUT}`);
