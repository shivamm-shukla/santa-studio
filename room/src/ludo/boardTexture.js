import * as THREE from "three";
import { RING, SEATS, SAFE } from "./engine.js";

/* Paints the standard board: four yards, the 52-cell ring, four home lanes
   and the centre triangle. Drawn once and reused as the table-top texture. */

const S = 1024;
const CELL = S / 15;
const px = (n) => n * CELL;

function star(ctx, cx, cy, r) {
  ctx.beginPath();
  for (let i = 0; i < 10; i++) {
    const a = (Math.PI / 5) * i - Math.PI / 2;
    const rad = i % 2 ? r * 0.44 : r;
    ctx[i ? "lineTo" : "moveTo"](cx + Math.cos(a) * rad, cy + Math.sin(a) * rad);
  }
  ctx.closePath();
  ctx.fill();
}

function arrow(ctx, cx, cy, r, dir) {
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(dir);
  ctx.beginPath();
  ctx.moveTo(0, -r);
  ctx.lineTo(r * 0.62, r * 0.45);
  ctx.lineTo(0, r * 0.12);
  ctx.lineTo(-r * 0.62, r * 0.45);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

export function drawBoard(ctx) {
  ctx.fillStyle = "#F4EEDD";
  ctx.fillRect(0, 0, S, S);

  // yards
  for (const seat of Object.values(SEATS)) {
    const top = seat.corner.startsWith("top") ? 0 : 9;
    const left = seat.corner.endsWith("left") ? 0 : 9;
    ctx.fillStyle = seat.color;
    ctx.fillRect(px(left), px(top), px(6), px(6));
    ctx.fillStyle = "#FBF7EC";
    ctx.fillRect(px(left + 1), px(top + 1), px(4), px(4));
    ctx.strokeStyle = "rgba(0,0,0,0.18)";
    ctx.lineWidth = 3;
    ctx.strokeRect(px(left + 1), px(top + 1), px(4), px(4));
    // the four parking circles
    for (const [r, c] of seat.yard) {
      ctx.fillStyle = seat.color;
      ctx.beginPath();
      ctx.arc(px(c + 0.5), px(r + 0.5), CELL * 0.42, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "rgba(255,255,255,0.35)";
      ctx.beginPath();
      ctx.arc(px(c + 0.5), px(r + 0.5), CELL * 0.3, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  // ring cells
  RING.forEach(([row, col], i) => {
    const seat = Object.values(SEATS).find((s) => s.start === i);
    ctx.fillStyle = seat ? seat.color : "#FBF7EC";
    ctx.fillRect(px(col), px(row), CELL, CELL);
    if (SAFE.has(i) && !seat) {
      ctx.fillStyle = "rgba(0,0,0,0.16)";
      star(ctx, px(col + 0.5), px(row + 0.5), CELL * 0.34);
    }
    if (seat) {
      // an arrow on each start square, pointing the way that player travels
      const [nr, nc] = RING[(i + 1) % RING.length];
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      arrow(ctx, px(col + 0.5), px(row + 0.5), CELL * 0.3, Math.atan2(nc - col, -(nr - row)));
    }
  });

  // home lanes
  for (const seat of Object.values(SEATS)) {
    ctx.fillStyle = seat.color;
    for (const [row, col] of seat.lane) ctx.fillRect(px(col), px(row), CELL, CELL);
  }

  // grid, over the whole cross only
  ctx.strokeStyle = "rgba(0,0,0,0.28)";
  ctx.lineWidth = 2;
  for (let i = 0; i <= 15; i++) {
    ctx.beginPath();
    ctx.moveTo(px(6), px(i));
    ctx.lineTo(px(9), px(i));
    ctx.moveTo(px(i), px(6));
    ctx.lineTo(px(i), px(9));
    ctx.stroke();
  }
  // centre triangle, one wedge per seat, each facing its own lane
  const c = px(7.5);
  const wedges = [
    { seat: SEATS.red, a: [px(6), px(6)], b: [px(6), px(9)] },      // opens west, toward row-7 lane
    { seat: SEATS.green, a: [px(6), px(6)], b: [px(9), px(6)] },    // opens north
    { seat: SEATS.yellow, a: [px(9), px(6)], b: [px(9), px(9)] },   // opens east
    { seat: SEATS.blue, a: [px(6), px(9)], b: [px(9), px(9)] },     // opens south
  ];
  for (const w of wedges) {
    ctx.fillStyle = w.seat.color;
    ctx.beginPath();
    ctx.moveTo(...w.a);
    ctx.lineTo(...w.b);
    ctx.lineTo(c, c);
    ctx.closePath();
    ctx.fill();
  }
  ctx.strokeStyle = "rgba(0,0,0,0.3)";
  ctx.lineWidth = 3;
  ctx.strokeRect(px(6), px(6), px(3), px(3));

  // outer frame
  ctx.strokeStyle = "rgba(0,0,0,0.35)";
  ctx.lineWidth = 8;
  ctx.strokeRect(4, 4, S - 8, S - 8);
}

export function makeBoardTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = S;
  canvas.height = S;
  drawBoard(canvas.getContext("2d"));
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

/* Grid coordinates -> table-top coordinates. The board plane is laid flat with
   its texture's top row at -Z, so rows map straight onto Z. */
export const BOARD_SIZE = 2.6;
const UNIT = BOARD_SIZE / 15;
export const gridToLocal = (row, col) => [
  (col + 0.5 - 7.5) * UNIT,
  (row + 0.5 - 7.5) * UNIT,
];
export const TOKEN_R = UNIT * 0.34;
