/* Films the reel's title cards.

   Each one is captured with a transparent background, at exactly the length it
   is used at in the edit - so its own in/hold/out animation already fits its
   slot and the editor never has to retime type. The lengths here are the same
   numbers as TITLES in reel/edit.py; if one moves, both move.

     node titles.mjs */

import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const FPS = 30;
const W = 1080;
const H = 1920;
const OUT = path.resolve("../build/reel");
const BASE = "http://127.0.0.1:8000/room/titles.html";

// index -> seconds on screen
const LENGTHS = [3.30, 1.60, 1.60, 1.60, 1.65, 1.65, 1.65, 1.65, 1.80];

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: "new",
  args: ["--no-sandbox", "--hide-scrollbars", `--window-size=${W},${H}`],
});

const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });

for (const [index, seconds] of LENGTHS.entries()) {
  const dir = path.join(OUT, `title${index}`);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });

  await page.goto(`${BASE}?i=${index}`, { waitUntil: "networkidle2", timeout: 60000 });
  // The webfont has to have arrived, or the first cards are set in the
  // fallback and the reel changes typeface halfway through.
  await page.evaluate(() => document.fonts.ready);
  await new Promise((r) => setTimeout(r, 400));

  const frames = Math.round(seconds * FPS);
  for (let i = 0; i < frames; i += 1) {
    await page.evaluate((k) => window.__titleSeek(k), i / (frames - 1));
    await new Promise((r) => setTimeout(r, 16));
    await page.screenshot({
      path: path.join(dir, `f${String(i).padStart(5, "0")}.png`),
      omitBackground: true,
    });
  }
  console.log(`title ${index}: ${frames} frames`);
}

await browser.close();
