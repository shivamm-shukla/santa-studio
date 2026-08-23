/* Everything an agent's laptop shows is drawn here onto a 2D canvas that gets
   used as the screen mesh's texture. Nothing an agent is doing is ever
   allowed to surface as a floating toast or side panel: if the user is
   supposed to see it, it is on the screen they'd be looking at over that
   agent's shoulder.

   Type is deliberately oversized for the canvas. A 13-inch laptop lid is a
   small object in a room, so anything set at a realistic UI scale is
   unreadable by the time it reaches the viewer — these screens are drawn the
   way a film prop is, legible first and accurate second. */

export const SCREEN_W = 1024;
export const SCREEN_H = 640;

const mono = (px) => `500 ${px}px 'JetBrains Mono', ui-monospace, Menlo, monospace`;
const ui = (px, w = 600) => `${w} ${px}px Inter, system-ui, sans-serif`;

const PAD = 40;
const BAR = 76;

function rr(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function clip(ctx, text, maxW) {
  if (ctx.measureText(text).width <= maxW) return text;
  let s = text;
  while (s.length > 1 && ctx.measureText(s + "…").width > maxW) s = s.slice(0, -1);
  return s + "…";
}

function wrap(ctx, text, maxW) {
  const out = [];
  let line = "";
  for (const word of text.split(" ")) {
    const next = line ? line + " " + word : word;
    if (ctx.measureText(next).width > maxW && line) {
      out.push(line);
      line = word;
    } else line = next;
  }
  if (line) out.push(line);
  return out;
}

function chrome(ctx, title, color) {
  ctx.fillStyle = "#12121a";
  ctx.fillRect(0, 0, SCREEN_W, BAR);
  ["#ff5f57", "#febc2e", "#28c840"].forEach((c, i) => {
    ctx.fillStyle = c;
    ctx.beginPath();
    ctx.arc(38 + i * 34, BAR / 2, 11, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.font = ui(28);
  ctx.fillStyle = "rgba(245,243,239,0.6)";
  ctx.textAlign = "center";
  ctx.fillText(title, SCREEN_W / 2, BAR / 2 + 10);
  ctx.textAlign = "left";
  ctx.fillStyle = color;
  ctx.fillRect(0, BAR - 3, SCREEN_W, 3);
}

function base(ctx, bg = "#0d0d13") {
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, SCREEN_W, SCREEN_H);
}

/* ---- states ------------------------------------------------------------ */

export function drawSleeping(ctx) {
  // Lid open, machine asleep: near-black with the faintest reflection so the
  // panel still reads as glass rather than a hole in the desk.
  base(ctx, "#08080c");
  const g = ctx.createLinearGradient(0, 0, SCREEN_W, SCREEN_H);
  g.addColorStop(0, "rgba(255,255,255,0.05)");
  g.addColorStop(0.5, "rgba(255,255,255,0.012)");
  g.addColorStop(1, "rgba(255,255,255,0.03)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, SCREEN_W, SCREEN_H);
}

export function drawEmail(ctx, { from, subject, preview, color }) {
  base(ctx, "#101018");
  chrome(ctx, "Inbox", color);

  ctx.fillStyle = "rgba(255,255,255,0.07)";
  rr(ctx, PAD - 12, BAR + 24, SCREEN_W - 2 * PAD + 24, 300, 20);
  ctx.fill();
  ctx.fillStyle = color;
  rr(ctx, PAD - 12, BAR + 24, 9, 300, 4);
  ctx.fill();

  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(PAD + 44, BAR + 76, 22, 0, Math.PI * 2);
  ctx.fill();

  ctx.font = ui(38, 700);
  ctx.fillStyle = "#F5F3EF";
  ctx.fillText(from, PAD + 84, BAR + 88);
  ctx.font = ui(26, 500);
  ctx.fillStyle = color;
  ctx.textAlign = "right";
  ctx.fillText("now", SCREEN_W - PAD, BAR + 88);
  ctx.textAlign = "left";

  ctx.font = ui(40, 700);
  ctx.fillStyle = "#F5F3EF";
  wrap(ctx, subject, SCREEN_W - 2 * PAD - 40)
    .slice(0, 1)
    .forEach((l) => ctx.fillText(l, PAD + 16, BAR + 156));

  ctx.font = ui(30, 400);
  ctx.fillStyle = "rgba(245,243,239,0.66)";
  wrap(ctx, preview, SCREEN_W - 2 * PAD - 40)
    .slice(0, 3)
    .forEach((l, i) => ctx.fillText(l, PAD + 16, BAR + 210 + i * 42));

  ctx.font = ui(28, 500);
  ["Manager — Standup notes", "Manager — Style profile updated"].forEach((t, i) => {
    ctx.fillStyle = "rgba(245,243,239,0.2)";
    ctx.fillText(t, PAD + 16, BAR + 400 + i * 66);
    ctx.fillStyle = "rgba(255,255,255,0.06)";
    ctx.fillRect(PAD - 12, BAR + 424 + i * 66, SCREEN_W - 2 * PAD + 24, 2);
  });
}

/* ---- per-role working screens ------------------------------------------ */

function logLines(ctx, lines, color, y0, max = 8, lh = 46) {
  ctx.font = mono(27);
  const shown = lines.slice(-max);
  shown.forEach((line, i) => {
    const last = i === shown.length - 1;
    ctx.fillStyle = last ? color : "rgba(245,243,239,0.4)";
    ctx.fillText(clip(ctx, line, SCREEN_W - 2 * PAD), PAD, y0 + i * lh);
  });
}

function drawBrowser(ctx, { lines, color, t }) {
  base(ctx);
  chrome(ctx, "Sources", color);
  const url = lines.length ? lines[lines.length - 1] : "about:blank";
  ctx.fillStyle = "rgba(255,255,255,0.08)";
  rr(ctx, PAD - 12, BAR + 20, SCREEN_W - 2 * PAD + 24, 58, 29);
  ctx.fill();
  ctx.font = ui(28, 500);
  ctx.fillStyle = "rgba(245,243,239,0.8)";
  ctx.fillText(clip(ctx, url, SCREEN_W - 2 * PAD - 60), PAD + 24, BAR + 58);
  ctx.fillStyle = color;
  ctx.fillRect(PAD - 12, BAR + 82, ((Math.sin(t * 1.4) + 1) / 2) * (SCREEN_W - 2 * PAD + 24), 4);
  logLines(ctx, lines.slice(0, -1), color, BAR + 148, 8);
}

function drawDoc(ctx, { lines, color, t }) {
  base(ctx, "#14141c");
  chrome(ctx, "script.md", color);
  ctx.fillStyle = "#f7f5f0";
  rr(ctx, 86, BAR + 16, SCREEN_W - 172, SCREEN_H - BAR - 40, 8);
  ctx.fill();
  ctx.font = "400 30px Georgia, serif";
  const body = lines.slice(-8);
  body.forEach((line, i) => {
    ctx.fillStyle = i === body.length - 1 ? "#15151c" : "rgba(21,21,28,0.55)";
    ctx.fillText(clip(ctx, line, SCREEN_W - 240), 122, BAR + 76 + i * 54);
  });
  if (body.length && Math.floor(t * 2) % 2 === 0) {
    const w = ctx.measureText(clip(ctx, body[body.length - 1], SCREEN_W - 240)).width;
    ctx.fillStyle = "#15151c";
    ctx.fillRect(126 + w, BAR + 50 + (body.length - 1) * 54, 3, 34);
  }
}

function drawWaveform(ctx, { lines, color, t, progress }) {
  base(ctx);
  chrome(ctx, "Voice — render", color);
  const midY = 250;
  ctx.strokeStyle = color;
  ctx.lineWidth = 4;
  ctx.beginPath();
  for (let x = 0; x < SCREEN_W - 2 * PAD; x += 6) {
    const seed = Math.sin(x * 0.11) * Math.sin(x * 0.037 + 1.3) * Math.sin(x * 0.007);
    const live = x / (SCREEN_W - 2 * PAD) < progress ? 1 : 0.12;
    const amp = seed * 120 * live * (0.85 + 0.15 * Math.sin(t * 3 + x * 0.02));
    ctx.moveTo(PAD + x, midY - amp);
    ctx.lineTo(PAD + x, midY + amp);
  }
  ctx.stroke();
  ctx.fillStyle = "rgba(255,255,255,0.9)";
  ctx.fillRect(PAD + progress * (SCREEN_W - 2 * PAD), 110, 3, 280);
  logLines(ctx, lines, color, 452, 4);
}

function drawGallery(ctx, { lines, color, progress }) {
  base(ctx);
  chrome(ctx, "Media bin", color);
  const cols = 4;
  const cw = (SCREEN_W - 2 * PAD - 3 * 20) / cols;
  const ch = 130;
  for (let i = 0; i < 8; i++) {
    const x = PAD + (i % cols) * (cw + 20);
    const y = BAR + 24 + Math.floor(i / cols) * (ch + 20);
    const filled = i / 8 < progress;
    ctx.fillStyle = filled ? `hsl(${(i * 47 + 190) % 360} 42% 34%)` : "rgba(255,255,255,0.05)";
    rr(ctx, x, y, cw, ch, 10);
    ctx.fill();
    if (filled && i === Math.floor(progress * 8) - 1) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 4;
      rr(ctx, x, y, cw, ch, 10);
      ctx.stroke();
    }
  }
  logLines(ctx, lines, color, 456, 4);
}

function drawTimeline(ctx, { lines, color, progress }) {
  base(ctx);
  chrome(ctx, "Assembly — timeline", color);
  const tracks = [
    { label: "V1", c: "#4DD0E1" },
    { label: "A1", c: "#9D6BFF" },
    { label: "A2", c: "#FFD23F" },
    { label: "TX", c: "#7CE38B" },
  ];
  tracks.forEach((tr, i) => {
    const y = BAR + 22 + i * 76;
    ctx.font = ui(26, 600);
    ctx.fillStyle = "rgba(245,243,239,0.5)";
    ctx.fillText(tr.label, PAD, y + 40);
    ctx.fillStyle = "rgba(255,255,255,0.05)";
    rr(ctx, PAD + 70, y, SCREEN_W - PAD - 110, 56, 8);
    ctx.fill();
    let x = PAD + 70;
    let k = 0;
    while (x < SCREEN_W - PAD - 40) {
      const w = 50 + ((i * 37 + k * 53) % 120);
      if ((x - PAD - 70) / (SCREEN_W - PAD - 110) < progress) {
        ctx.fillStyle = tr.c;
        ctx.globalAlpha = 0.78;
        rr(ctx, x + 4, y + 5, Math.min(w, SCREEN_W - PAD - 44 - x), 46, 6);
        ctx.fill();
        ctx.globalAlpha = 1;
      }
      x += w + 8;
      k++;
    }
  });
  ctx.fillStyle = "#fff";
  ctx.fillRect(PAD + 70 + progress * (SCREEN_W - PAD - 110), BAR + 12, 3, 320);
  logLines(ctx, lines, color, 470, 3);
}

function drawShorts(ctx, { lines, color, progress }) {
  base(ctx);
  chrome(ctx, "Shorts — candidates", color);
  for (let i = 0; i < 4; i++) {
    const x = 64 + i * 232;
    const on = i / 4 < progress;
    ctx.fillStyle = on ? "rgba(255,255,255,0.09)" : "rgba(255,255,255,0.04)";
    rr(ctx, x, BAR + 20, 180, 300, 14);
    ctx.fill();
    if (on) {
      ctx.strokeStyle = color;
      ctx.lineWidth = 3;
      rr(ctx, x, BAR + 20, 180, 300, 14);
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.font = ui(46, 700);
      ctx.textAlign = "center";
      ctx.fillText((0.94 - i * 0.11).toFixed(2), x + 90, BAR + 180);
      ctx.font = ui(22, 500);
      ctx.fillStyle = "rgba(245,243,239,0.5)";
      ctx.fillText("hook score", x + 90, BAR + 214);
      ctx.textAlign = "left";
    }
  }
  logLines(ctx, lines, color, 470, 3);
}

function drawNotes(ctx, { lines, color }) {
  base(ctx, "#121218");
  chrome(ctx, "Notes", color);
  const shown = lines.slice(-7);
  ctx.font = ui(30, 500);
  shown.forEach((line, i) => {
    const last = i === shown.length - 1;
    ctx.fillStyle = last ? color : "rgba(245,243,239,0.3)";
    ctx.beginPath();
    ctx.arc(PAD + 14, BAR + 42 + i * 66, 7, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = last ? "#F5F3EF" : "rgba(245,243,239,0.45)";
    ctx.fillText(clip(ctx, line, SCREEN_W - PAD - 80), PAD + 42, BAR + 52 + i * 66);
  });
}

function drawTerminal(ctx, { lines, color }) {
  base(ctx, "#08080c");
  chrome(ctx, "publish — bash", color);
  logLines(ctx, lines, color, BAR + 60, 9, 52);
}

/* The Manager's own screen: the pipeline, as the state machine sees it. */
function drawBoard(ctx, { color, roster, stage }) {
  base(ctx, "#0d0d13");
  chrome(ctx, "Run board", color);
  ctx.font = ui(26, 600);
  roster.forEach((a, i) => {
    const col = i % 2;
    const row = Math.floor(i / 2);
    const x = PAD - 8 + col * 480;
    const y = BAR + 16 + row * 80;
    const done = a.status === "done";
    const active = a.status === "working" || a.status === "incoming";
    ctx.fillStyle = active ? "rgba(255,107,53,0.16)" : "rgba(255,255,255,0.04)";
    rr(ctx, x, y, 456, 64, 10);
    ctx.fill();
    ctx.fillStyle = done ? "#7CE38B" : active ? color : "rgba(245,243,239,0.22)";
    ctx.beginPath();
    ctx.arc(x + 32, y + 32, 11, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = active ? "#F5F3EF" : "rgba(245,243,239,0.45)";
    ctx.fillText(a.name, x + 58, y + 42);
  });
  ctx.font = mono(26);
  ctx.fillStyle = color;
  ctx.fillText(stage, PAD, SCREEN_H - 26);
}

const RENDERERS = {
  browser: drawBrowser,
  doc: drawDoc,
  waveform: drawWaveform,
  gallery: drawGallery,
  timeline: drawTimeline,
  shorts: drawShorts,
  notes: drawNotes,
  terminal: drawTerminal,
  board: drawBoard,
};

/** Single entry point used by LaptopScreen. */
export function paintScreen(ctx, kind, props) {
  (RENDERERS[kind] || drawTerminal)(ctx, props);
}
