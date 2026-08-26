/* Films the whole product, a frame at a time, for a vertical reel.

   Same principle as film.mjs and a superset of it: nothing is screen-recorded,
   because a headless browser renders far slower than real time and a recording
   would stutter wherever the machine did. Instead every scene is a function of
   its frame number - seek, settle, capture - so the result is a clean 30fps
   whatever the render actually cost.

   A scene is a URL plus a `drive(page, k)` where k runs 0 -> 1 across it. That
   covers all of it: the room drives its shot list, the landing page drives its
   own scroll, and the screens inside the studio drive their own tabs.

     node reel.mjs                every scene
     node reel.mjs landing tv     only those

   Frames land in ../build/demo/<scene>/ as JPEGs. They were PNGs until a
   three minute film at 1080x1920 filled the disk and took a pipeline run down
   with it - libsndfile reports a full disk as "System error", which is a fun
   afternoon. At quality 92 the difference is invisible through a grade and
   the footage is a fifth of the size. */

import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const FPS = 30;
const W = 1080;
const H = 1920;
const OUT = path.resolve("../build/demo");
const HOST = "http://127.0.0.1:8000";

/* Milliseconds after a seek before the shutter. Long enough for a canvas
   panel to have repainted and one animation frame to have run. */
const SETTLE = 55;

const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const easeOut = (x) => 1 - Math.pow(1 - x, 3);

/* ---------------------------------------------------------------- scenes -- */

const SCENES = [
  {
    /* The site, running on a laptop on a desk, filmed from six angles - the
       opening of the reel. The picture on the screen is the landing capture
       below, which has to have been shot and encoded first. */
    name: "laptop",
    seconds: 15.0,
    url: `${HOST}/room/laptop.html`,
    warmup: 6000,
    async prepare(page) {
      // The video texture has to have decoded a frame before any of this is
      // worth photographing, or the first shots are of a black rectangle.
      await page.waitForFunction(() => window.__shotReady && window.__shotReady(), { timeout: 30000 });
    },
    async drive(page, k, scene) {
      await page.evaluate((t) => window.__shotSeek(t), k * scene.seconds);
    },
  },
  {
    /* The front door, filmed at the shape of a laptop screen rather than a
       phone's - this footage is not shown flat. It becomes the picture on a
       MacBook standing on a desk, which the camera then moves around. So it
       is captured at 16:10 and at the size that screen is actually rendered.

       Scrolls itself from the hero to the last section, eased at both ends so
       it starts and stops like a hand on a trackpad rather than like a
       script. */
    name: "landing",
    seconds: 11.0,
    width: 1680,
    height: 1050,
    url: `${HOST}/`,
    warmup: 3500,
    async prepare(page) {
      // The reveals fire on intersection; give the top of the page a moment.
      await page.evaluate(() => window.scrollTo(0, 0));
      await new Promise((r) => setTimeout(r, 900));
    },
    async drive(page, k) {
      await page.evaluate((frac) => {
        const max = document.body.scrollHeight - window.innerHeight;
        window.scrollTo(0, max * frac);
      }, easeInOut(k));
    },
  },
  {
    /* The long tour, on the shot list in src/world/demo.js: arrival, the
       lights coming up mid-move, a full turn round the outside, and time at
       each place rather than a touch on the way past. The run id attaches the
       room to a real pipeline run, so the desks are showing work that is
       actually happening rather than a rehearsal. */
    name: "tour",
    seconds: 93.75,
    url: `${HOST}/room/?demo=1&run=${process.env.SANTA_RUN || ""}`,
    warmup: 8000,
    async drive(page, k, scene) {
      await page.evaluate((t) => window.__demoSeek(t), k * scene.seconds);
    },
  },
  {
    /* The studio itself, on the shot list in src/world/film.js - arrival,
       the drone, the lights coming up, the desks, the booth, the crane out. */
    name: "studio",
    seconds: 30.6,
    url: `${HOST}/room/?film=1`,
    warmup: 7000,
    async drive(page, k, scene) {
      await page.evaluate((t) => window.__filmSeek(t), k * scene.seconds);
    },
  },
  {
    /* Act seven: the film the pipeline actually made, playing on the same
       machine the demo opened on. Needs the run to have finished and its
       frames to have been laid out under room/public/reel/film/ - see
       reel/film_frames.sh. */
    name: "film",
    seconds: 22.5,
    url: `${HOST}/room/laptop.html?src=film&shots=film`,
    warmup: 6000,
    async prepare(page) {
      await page.waitForFunction(() => window.__shotReady && window.__shotReady(), { timeout: 30000 });
    },
    async drive(page, k, scene) {
      await page.evaluate((t) => window.__shotSeek(t), k * scene.seconds);
    },
  },
  {
    /* The board, being written on. The brief types itself, because a form
       sitting still says nothing about what it does. */
    name: "board",
    seconds: 5.0,
    url: `${HOST}/room/?at=board`,
    warmup: 6500,
    async drive(page, k) {
      await page.evaluate((frac) => {
        const NICHE = "the history of the shipping container";
        const typed = NICHE.slice(0, Math.round(NICHE.length * Math.min(1, frac * 1.6)));
        const field = document.querySelector(".board-panel input");
        if (!field) return;
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, "value"
        ).set;
        setter.call(field, typed);
        field.dispatchEvent(new Event("input", { bubbles: true }));
      }, frac(k));
    },
  },
  {
    /* The television, with the Clips app on it, walking its own tabs. */
    name: "tv",
    seconds: 6.0,
    url: `${HOST}/room/?at=bench`,
    warmup: 6500,
    async drive(page, k) {
      await page.evaluate((frac) => {
        const tabs = [...document.querySelectorAll(".tv-tab")];
        if (!tabs.length) return;
        const want = Math.min(tabs.length - 1, Math.floor(frac * tabs.length));
        if (!tabs[want].classList.contains("on")) tabs[want].click();
      }, k);
    },
  },
  {
    /* Inside the booth, at the microphone. */
    name: "booth",
    seconds: 4.5,
    url: `${HOST}/room/?at=booth`,
    warmup: 6500,
    async drive() {},
  },
];

const frac = (k) => k;

/* ------------------------------------------------------------------ film -- */

const only = process.argv.slice(2);
const wanted = only.length ? SCENES.filter((s) => only.includes(s.name)) : SCENES;

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: "new",
  args: [
    "--no-sandbox",
    // A profile of its own, so a recorder that gets killed cannot leave a
    // lock behind that stops the next one launching at all.
    `--user-data-dir=/tmp/santa-chrome-${process.pid}`,
    // Native GL against the card. SwiftShader takes seconds a frame here.
    "--use-gl=angle",
    "--use-angle=gl",
    "--enable-gpu-rasterization",
    "--ignore-gpu-blocklist",
    "--hide-scrollbars",
    `--window-size=${W},${H}`,
  ],
});

const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });

for (const scene of wanted) {
  const dir = path.join(OUT, scene.name);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });

  await page.setViewport({
    width: scene.width ?? W,
    height: scene.height ?? H,
    deviceScaleFactor: 1,
  });
  await page.goto(scene.url, { waitUntil: "domcontentloaded", timeout: 90000 });
  // First paint of a WebGL scene includes compiling every shader in it.
  await new Promise((r) => setTimeout(r, scene.warmup));
  if (scene.prepare) await scene.prepare(page);

  const frames = Math.round(scene.seconds * FPS);
  const began = Date.now();
  console.log(`${scene.name}: ${frames} frames (${scene.seconds}s)`);

  for (let i = 0; i < frames; i += 1) {
    await scene.drive(page, i / (frames - 1), scene);
    await new Promise((r) => setTimeout(r, SETTLE));
    await page.screenshot({
      path: path.join(dir, `f${String(i).padStart(5, "0")}.jpg`),
      type: "jpeg",
      quality: 92,
    });
    if (i % 60 === 0 && i) {
      const rate = i / ((Date.now() - began) / 1000);
      console.log(`  ${i}/${frames}  ${rate.toFixed(1)} fps  ~${Math.round((frames - i) / rate)}s left`);
    }
  }
  console.log(`${scene.name}: done in ${Math.round((Date.now() - began) / 1000)}s`);
}

await browser.close();
