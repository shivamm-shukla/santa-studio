/* Films the demo film's title cards.

   Each is captured at exactly the length it is used at, so its own in/hold/out
   already fits its slot and the editor never retimes type. The lengths come
   from src/titles/cards.js, which is also what reel/demo_edit.py reads. */

import fs from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const FPS = 30;
const W = 1080;
const H = 1920;
const OUT = path.resolve("../build/demo/titles");
const BASE = "http://127.0.0.1:8000/room/titles.html?set=demo";

const cards = JSON.parse(process.env.CARDS_JSON);

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: "new",
  args: ["--no-sandbox",
    // A profile of its own, so a recorder that gets killed cannot leave a
    // lock behind that stops the next one launching at all.
    `--user-data-dir=/tmp/santa-chrome-${process.pid}`, "--hide-scrollbars", `--window-size=${W},${H}`],
});
const page = await browser.newPage();
await page.setViewport({ width: W, height: H, deviceScaleFactor: 1 });

for (const [index, card] of cards.entries()) {
  const dir = path.join(OUT, card.id);
  fs.rmSync(dir, { recursive: true, force: true });
  fs.mkdirSync(dir, { recursive: true });

  await page.goto(`${BASE}&i=${index}`, { waitUntil: "networkidle2", timeout: 60000 });
  // The webfont has to have arrived, or the first cards are set in the
  // fallback and the film changes typeface halfway through.
  await page.evaluate(() => document.fonts.ready);
  await new Promise((r) => setTimeout(r, 350));

  const frames = Math.round(card.seconds * FPS);
  for (let i = 0; i < frames; i += 1) {
    await page.evaluate((k) => window.__titleSeek(k), i / (frames - 1));
    await new Promise((r) => setTimeout(r, 14));
    await page.screenshot({
      path: path.join(dir, `f${String(i).padStart(5, "0")}.png`),
      omitBackground: true,
    });
  }
  console.log(`${card.id}: ${frames}`);
}

await browser.close();
