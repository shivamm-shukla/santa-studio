/* Canvas painters for everything in the landing scene that has words or a
   symbol on it.

   The same technique the room's screens use: paint into a 2D canvas, hand it
   to three as a texture. It is here for the same reasons - no font loader, no
   SDF text pipeline, no drei - and one more that matters on a landing page:
   an object with real text on its surface reads as a thing in the space,
   where HTML floated on top reads as a page with a picture behind it. */

import * as THREE from "three";

export const ACCENT = "#ff6b35";
export const DATA = "#00e5ff";

export function texture(width, height, paint) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  paint(canvas.getContext("2d"), width, height);
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace;
  map.anisotropy = 8;
  return map;
}

function rounded(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

/* ---- Station panels -------------------------------------------------- */

/** One stage of the pipeline, as a lit slab you pass on the way through. */
export function stationTexture({ index, title, body, note }) {
  return texture(1024, 640, (ctx, w, h) => {
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "rgba(16,16,24,0.96)");
    g.addColorStop(1, "rgba(10,10,16,0.96)");
    ctx.fillStyle = g;
    rounded(ctx, 0, 0, w, h, 34);
    ctx.fill();

    ctx.strokeStyle = "rgba(255,255,255,0.10)";
    ctx.lineWidth = 2;
    rounded(ctx, 1, 1, w - 2, h - 2, 34);
    ctx.stroke();

    // The step number, oversized and low-contrast, the way a title card in a
    // documentary carries its chapter.
    ctx.fillStyle = "rgba(255,107,53,0.14)";
    ctx.font = "800 300px Inter, system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(String(index).padStart(2, "0"), w - 48, h - 40);

    ctx.textAlign = "left";
    ctx.fillStyle = ACCENT;
    ctx.font = "700 24px Inter, system-ui, sans-serif";
    ctx.letterSpacing = "6px";
    ctx.fillText(note.toUpperCase(), 64, 96);
    ctx.letterSpacing = "0px";

    ctx.fillStyle = "#f5f3ef";
    ctx.font = "800 76px Inter, system-ui, sans-serif";
    ctx.fillText(title, 64, 210);

    ctx.fillStyle = "rgba(245,243,239,0.62)";
    ctx.font = "400 31px Inter, system-ui, sans-serif";
    wrap(ctx, body, 64, 286, w - 200, 46);
  });
}

function wrap(ctx, text, x, y, maxWidth, lineHeight) {
  let line = "";
  let cursor = y;
  for (const word of text.split(" ")) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > maxWidth && line) {
      ctx.fillText(line, x, cursor);
      line = word;
      cursor += lineHeight;
    } else {
      line = next;
    }
  }
  if (line) ctx.fillText(line, x, cursor);
}

/* ---- Platform badges -------------------------------------------------- */

/* Drawn rather than imported. These are the marks people recognise at a
   glance, and the point of them here is "this is where it goes" - so they are
   simplified to the shape the eye actually reads, not reproduced. */

const PLATFORMS = {
  youtube: (ctx, s) => {
    ctx.fillStyle = "#FF0033";
    rounded(ctx, s * 0.1, s * 0.24, s * 0.8, s * 0.52, s * 0.14);
    ctx.fill();
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.moveTo(s * 0.42, s * 0.36);
    ctx.lineTo(s * 0.66, s * 0.5);
    ctx.lineTo(s * 0.42, s * 0.64);
    ctx.closePath();
    ctx.fill();
  },
  instagram: (ctx, s) => {
    const g = ctx.createLinearGradient(s * 0.15, s * 0.85, s * 0.85, s * 0.15);
    g.addColorStop(0, "#F9CE34");
    g.addColorStop(0.5, "#EE2A7B");
    g.addColorStop(1, "#6228D7");
    ctx.fillStyle = g;
    rounded(ctx, s * 0.14, s * 0.14, s * 0.72, s * 0.72, s * 0.22);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = s * 0.055;
    ctx.beginPath();
    ctx.arc(s * 0.5, s * 0.5, s * 0.17, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "#fff";
    ctx.beginPath();
    ctx.arc(s * 0.68, s * 0.32, s * 0.038, 0, Math.PI * 2);
    ctx.fill();
  },
  x: (ctx, s) => {
    ctx.fillStyle = "#0b0b0f";
    rounded(ctx, s * 0.14, s * 0.14, s * 0.72, s * 0.72, s * 0.2);
    ctx.fill();
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = s * 0.09;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(s * 0.33, s * 0.33);
    ctx.lineTo(s * 0.67, s * 0.67);
    ctx.moveTo(s * 0.67, s * 0.33);
    ctx.lineTo(s * 0.33, s * 0.67);
    ctx.stroke();
  },
};

export function platformTexture(name) {
  return texture(256, 256, (ctx, s) => {
    ctx.clearRect(0, 0, s, s);
    (PLATFORMS[name] ?? PLATFORMS.youtube)(ctx, s);
  });
}

export const PLATFORM_NAMES = Object.keys(PLATFORMS);

/* ---- The mark at the entrance ----------------------------------------- */

export function titleTexture(line, sub) {
  return texture(2048, 1024, (ctx, w, h) => {
    ctx.clearRect(0, 0, w, h);
    ctx.textAlign = "center";

    ctx.fillStyle = ACCENT;
    ctx.font = "700 34px Inter, system-ui, sans-serif";
    ctx.letterSpacing = "18px";
    ctx.fillText("SANTA STUDIO", w / 2, 250);
    ctx.letterSpacing = "0px";

    ctx.fillStyle = "#f7f5f1";
    ctx.font = "800 176px Inter, system-ui, sans-serif";
    line.split("\n").forEach((text, i) => {
      ctx.fillText(text, w / 2, 460 + i * 186);
    });

    ctx.fillStyle = "rgba(245,243,239,0.55)";
    ctx.font = "400 44px Inter, system-ui, sans-serif";
    ctx.fillText(sub, w / 2, 460 + line.split("\n").length * 186 + 70);
  });
}
