import { ACCENT } from "../theme.js";

/* The one screen in the building that talks to the human. Everything the
   pipeline needs a decision on is drawn here and nowhere else — no modal, no
   toast, no sidebar — so the user can answer without getting up from the
   Ludo table.

   Because it has to be legible from that seat, the layout is deliberately
   two-tier: the headline and the two buttons are sized to be read across the
   room at a glance, and the detail underneath is for when you walk over. */

export const AW = 1200;
export const AH = 760;

function rr(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
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

/* When the decision is about a video, the video is on the screen. Asking "is
   this cut good to go?" over a filename was asking somebody to approve
   something they had not been shown - the file was on disk and the only way
   to watch it was to go and find it in a file manager.

   The pane, the download chip and the buttons are all laid out here and
   hit-tested against the same rectangles, so what you click is what you see. */
export const VIDEO_PANE = { x: (AW - 640) / 2, y: 44, w: 640, h: 360 };
export const DOWNLOAD_CHIP = {
  x: VIDEO_PANE.x + VIDEO_PANE.w - 196,
  y: VIDEO_PANE.y + VIDEO_PANE.h + 14,
  w: 196,
  h: 46,
};
const SCRUB = {
  x: VIDEO_PANE.x,
  y: VIDEO_PANE.y + VIDEO_PANE.h + 26,
  w: VIDEO_PANE.w - 216,
  h: 6,
};


function clock(seconds) {
  if (!Number.isFinite(seconds)) return "0:00";
  const m = Math.floor(seconds / 60);
  return `${m}:${String(Math.floor(seconds % 60)).padStart(2, "0")}`;
}

/** Button hit boxes, shared by the painter and the click handler. */
export function buttonRects(count) {
  const w = count === 2 ? 500 : 350;
  const gap = 36;
  const total = count * w + (count - 1) * gap;
  const x0 = (AW - total) / 2;
  return Array.from({ length: count }, (_, i) => ({
    x: x0 + i * (w + gap),
    y: AH - 186,
    w,
    h: 124,
  }));
}

/* An LCD is never truly black and never perfectly even — a faint backlight
   gradient is most of what separates a screen from a hole cut in the wall. */
function panelGround(ctx, lit) {
  const g = ctx.createLinearGradient(0, 0, 0, AH);
  g.addColorStop(0, lit ? "#16161f" : "#0a0a0e");
  g.addColorStop(0.55, lit ? "#101018" : "#07070a");
  g.addColorStop(1, lit ? "#0c0c13" : "#0a0a0f");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, AW, AH);

  const glow = ctx.createRadialGradient(AW / 2, AH * 0.42, 40, AW / 2, AH * 0.42, AW * 0.75);
  glow.addColorStop(0, lit ? "rgba(255,255,255,0.05)" : "rgba(255,255,255,0.015)");
  glow.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, AW, AH);
}

function drawVideo(ctx, video, { playing, hotVideo, hotDownload }) {
  const { x, y, w, h } = VIDEO_PANE;

  ctx.fillStyle = "#000";
  rr(ctx, x, y, w, h, 12);
  ctx.fill();

  // Letterboxed into the pane, never stretched: this is the cut being judged.
  const ratio = video && video.videoWidth ? video.videoWidth / video.videoHeight : 16 / 9;
  const fitH = Math.min(h, w / ratio);
  const fitW = fitH * ratio;
  if (video && video.readyState >= 2) {
    ctx.save();
    rr(ctx, x, y, w, h, 12);
    ctx.clip();
    ctx.drawImage(video, x + (w - fitW) / 2, y + (h - fitH) / 2, fitW, fitH);
    ctx.restore();
  }

  ctx.strokeStyle = hotVideo ? "rgba(255,255,255,0.35)" : "rgba(255,255,255,0.12)";
  ctx.lineWidth = 2;
  rr(ctx, x, y, w, h, 12);
  ctx.stroke();

  if (!playing) {
    // The play button is the whole pane; this is only the badge that says so.
    const cx = x + w / 2;
    const cy = y + h / 2;
    ctx.fillStyle = "rgba(10,10,14,0.62)";
    ctx.beginPath();
    ctx.arc(cx, cy, 52, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#F5F3EF";
    ctx.beginPath();
    ctx.moveTo(cx - 17, cy - 26);
    ctx.lineTo(cx + 30, cy);
    ctx.lineTo(cx - 17, cy + 26);
    ctx.closePath();
    ctx.fill();
  }

  const played = video && video.duration ? video.currentTime / video.duration : 0;
  ctx.fillStyle = "rgba(255,255,255,0.14)";
  rr(ctx, SCRUB.x, SCRUB.y, SCRUB.w, SCRUB.h, 3);
  ctx.fill();
  ctx.fillStyle = ACCENT;
  rr(ctx, SCRUB.x, SCRUB.y, Math.max(4, SCRUB.w * played), SCRUB.h, 3);
  ctx.fill();

  ctx.font = "500 22px 'JetBrains Mono', ui-monospace, monospace";
  ctx.fillStyle = "rgba(245,243,239,0.5)";
  ctx.fillText(
    `${clock(video?.currentTime ?? 0)} / ${clock(video?.duration ?? 0)}`,
    SCRUB.x,
    SCRUB.y + 34
  );

  ctx.fillStyle = hotDownload ? "rgba(255,255,255,0.16)" : "rgba(255,255,255,0.07)";
  rr(ctx, DOWNLOAD_CHIP.x, DOWNLOAD_CHIP.y, DOWNLOAD_CHIP.w, DOWNLOAD_CHIP.h, 12);
  ctx.fill();
  ctx.strokeStyle = "rgba(255,255,255,0.2)";
  ctx.lineWidth = 2;
  ctx.stroke();
  ctx.font = "600 24px Inter, system-ui, sans-serif";
  ctx.fillStyle = "#F5F3EF";
  ctx.textAlign = "center";
  ctx.fillText(
    "Save to my laptop",
    DOWNLOAD_CHIP.x + DOWNLOAD_CHIP.w / 2,
    DOWNLOAD_CHIP.y + 31
  );
  ctx.textAlign = "left";
}

export function drawApproval(ctx, { request, stage, pulse, hovered, video, playing, hotVideo, hotDownload }) {
  panelGround(ctx, !!request);

  if (!request) {
    // Standby. A screen with nothing to say sits nearly dark, the way a real
    // one does — the room's attention cue is that it lights up, not that it
    // wears a frame.
    ctx.font = "600 30px Inter, system-ui, sans-serif";
    ctx.fillStyle = "rgba(245,243,239,0.22)";
    ctx.fillText("No decisions pending", 64, AH - 96);
    ctx.font = "500 26px 'JetBrains Mono', ui-monospace, monospace";
    ctx.fillStyle = "rgba(245,243,239,0.13)";
    ctx.fillText(stage, 64, AH - 54);
    return;
  }

  const watching = !!video;

  if (watching) {
    drawVideo(ctx, video, { playing, hotVideo, hotDownload });
  } else {
    ctx.font = "700 30px Inter, system-ui, sans-serif";
    ctx.fillStyle = ACCENT;
    ctx.letterSpacing = "5px";
    ctx.fillText("NEEDS YOUR DECISION", 64, 92);
    ctx.letterSpacing = "0px";
    // a thin rule instead of a border: the panel is the light, not the frame
    ctx.fillStyle = `rgba(255,107,53,${0.35 + pulse * 0.45})`;
    ctx.fillRect(64, 112, 372, 3);

    ctx.font = "500 27px Inter, system-ui, sans-serif";
    ctx.fillStyle = "rgba(245,243,239,0.4)";
    ctx.fillText(`${request.from} · ${request.stage}`, 64, 156);
  }

  // The headline is the part that has to survive being read from the table.
  const headY = watching ? 500 : 268;
  ctx.font = `700 ${watching ? 52 : 84}px Inter, system-ui, sans-serif`;
  ctx.fillStyle = "#FBFAF7";
  const title = wrap(ctx, request.title, AW - 128).slice(0, watching ? 1 : 2);
  title.forEach((l, i) => ctx.fillText(l, 64, headY + i * (watching ? 60 : 92)));

  ctx.font = `400 ${watching ? 26 : 30}px Inter, system-ui, sans-serif`;
  ctx.fillStyle = "rgba(245,243,239,0.62)";
  wrap(ctx, request.body, AW - 128)
    .slice(0, watching ? 1 : 3)
    .forEach((l, i) =>
      ctx.fillText(l, 64, headY + title.length * (watching ? 60 : 92) + 24 + i * 44)
    );

  const rects = buttonRects(request.options.length);
  request.options.forEach((opt, i) => {
    const r = rects[i];
    const primary = opt.tone === "primary";
    const hot = hovered === i;
    ctx.fillStyle = primary
      ? hot ? "#ff8355" : ACCENT
      : hot ? "rgba(255,255,255,0.15)" : "rgba(255,255,255,0.06)";
    rr(ctx, r.x, r.y, r.w, r.h, 20);
    ctx.fill();
    if (!primary) {
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.lineWidth = 3;
      ctx.stroke();
    }
    ctx.font = "700 42px Inter, system-ui, sans-serif";
    ctx.fillStyle = primary ? "#140702" : "#F5F3EF";
    ctx.textAlign = "center";
    ctx.fillText(opt.label, r.x + r.w / 2, r.y + r.h / 2 + 15);
    ctx.textAlign = "left";
  });
}
