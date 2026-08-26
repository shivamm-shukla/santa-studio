import puppeteer from "puppeteer-core";
const [url, ...times] = process.argv.slice(2);
const b = await puppeteer.launch({ executablePath: "/usr/bin/google-chrome", headless: "new",
  args: ["--no-sandbox",
    // A profile of its own, so a recorder that gets killed cannot leave a
    // lock behind that stops the next one launching at all.
    `--user-data-dir=/tmp/santa-chrome-${process.pid}`,"--use-gl=angle","--use-angle=gl","--ignore-gpu-blocklist","--hide-scrollbars"] });
const p = await b.newPage();
await p.setViewport({ width: 1080, height: 1920 });
await p.goto(url, { waitUntil: "domcontentloaded", timeout: 90000 });
await new Promise(r => setTimeout(r, 8000));
for (const t of times) {
  await p.evaluate((x) => window.__demoSeek(Number(x)), t);
  await new Promise(r => setTimeout(r, 800));
  await p.screenshot({ path: `/tmp/demo-${t}.png` });
}
console.log("peeked", times.join(" "));
await b.close();
