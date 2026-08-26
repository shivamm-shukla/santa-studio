/* Screenshots of the actual studio, for the landing page.

   Taken from the built room over the real server rather than mocked up, so
   what the front door shows is what you get when you walk in. Re-run it after
   the room changes: `node shoot.mjs` with the app on :8000. */

import puppeteer from "puppeteer-core";

const OUT = new URL("./public/shots/", import.meta.url).pathname;
const BASE = "http://127.0.0.1:8000/room/";

/* shot=1 puts the room in photography mode: chrome out of the way, and the
   camera standing back on a three-quarter view rather than square-on and
   close the way it does when you are working at a thing. */
const SHOTS = [
  ["floor", "", 6000],
  ["board", "?at=board&shot=1", 5000],
  ["booth", "?at=booth&shot=1", 5000],
  ["rack", "?at=rack&shot=1", 5000],
];

/* Both states of the light switch. The landing shows whichever one the reader
   is already in, so the pictures of the studio are never lit the opposite way
   to the page they are sitting on. */
const THEMES = ["dark", "light"];

const browser = await puppeteer.launch({
  executablePath: "/usr/bin/google-chrome",
  headless: "new",
  args: [
    "--no-sandbox",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--window-size=1600,1000",
  ],
});

const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 1000 });

for (const theme of THEMES) {
  for (const [name, query, settle] of SHOTS) {
    await page.goto(BASE + query, { waitUntil: "networkidle2" });
    await page.evaluate((t) => localStorage.setItem("santa-studio-theme", t), theme);
    await page.reload({ waitUntil: "networkidle2" });
    // Let the camera finish travelling and the lights finish coming up.
    await new Promise((r) => setTimeout(r, settle));
    await page.screenshot({ path: `${OUT}${name}-${theme}.png` });
    console.log("shot", name, theme);
  }
}

await browser.close();
