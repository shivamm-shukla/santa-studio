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

export function drawApproval(ctx, { request, stage, pulse, hovered }) {
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

  // The headline is the part that has to survive being read from the table.
  ctx.font = "700 84px Inter, system-ui, sans-serif";
  ctx.fillStyle = "#FBFAF7";
  const title = wrap(ctx, request.title, AW - 128).slice(0, 2);
  title.forEach((l, i) => ctx.fillText(l, 64, 268 + i * 92));

  ctx.font = "400 30px Inter, system-ui, sans-serif";
  ctx.fillStyle = "rgba(245,243,239,0.62)";
  wrap(ctx, request.body, AW - 128)
    .slice(0, 3)
    .forEach((l, i) => ctx.fillText(l, 64, 268 + title.length * 92 + 24 + i * 44));

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
