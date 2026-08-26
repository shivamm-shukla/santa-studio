import * as THREE from "three";
import { ACCENT } from "../theme.js";

/* What the screen on the booth wall says, painted into a canvas.

   The prompt, the clock and the level used to live in a panel floating over
   the middle of the room, which covered the thing you had walked in to look
   at. A booth has a screen on the wall for exactly this, so it says it there
   and the view stays clear. Typing a name still needs a keyboard, so that one
   step is still flat - everything before it is in the room. */

export const W = 900;
export const H = 520;

export function makeScreen() {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 8;
  return { ctx, texture };
}

function timecode(seconds) {
  const whole = Math.floor(seconds || 0);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

export function paintScreen(ctx, { status, seconds, enough, level, minSeconds, error }) {
  ctx.clearRect(0, 0, W, H);
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, "#0d0d15");
  g.addColorStop(1, "#07070c");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  const live = status === "recording";

  ctx.fillStyle = live ? "#ff3b20" : ACCENT;
  ctx.font = "700 22px Inter, system-ui, sans-serif";
  ctx.letterSpacing = "7px";
  ctx.fillText(
    { idle: "THE BOOTH", ready: "READY", recording: "RECORDING", recorded: "LISTEN BACK", denied: "NO MICROPHONE" }[status] ??
      "THE BOOTH",
    54,
    74
  );
  ctx.letterSpacing = "0px";

  if (live) {
    // A blinking dot, the way every recorder anyone has used says it is on.
    const on = Math.floor(Date.now() / 550) % 2 === 0;
    if (on) {
      ctx.beginPath();
      ctx.arc(W - 74, 66, 12, 0, Math.PI * 2);
      ctx.fillStyle = "#ff3b20";
      ctx.fill();
    }
  }

  ctx.fillStyle = "#f5f3ef";

  if (status === "idle" || status === "denied") {
    ctx.font = "800 46px Inter, system-ui, sans-serif";
    ctx.fillText(status === "denied" ? "It could not listen." : "Say something", 54, 176);
    if (status !== "denied") ctx.fillText("in your own voice.", 54, 230);

    ctx.fillStyle = "rgba(245,243,239,0.62)";
    ctx.font = "400 26px Inter, system-ui, sans-serif";
    if (status === "denied") {
      ctx.fillText(error || "No microphone was available.", 54, 232);
      ctx.fillText("Press the button on the stand to try again.", 54, 272);
    } else {
      ctx.fillText(`${minSeconds} seconds is the floor.`, 54, 292);
      ctx.fillText("Press the orange button on the stand.", 54, 332);
    }
    return;
  }

  // Clock, big, because it is the thing you are watching while you talk.
  ctx.font = "800 122px 'JetBrains Mono', monospace";
  ctx.fillText(timecode(seconds), 54, 226);

  // How far past the floor. Fills to it, then stays full - there is no
  // ceiling to run out of.
  const barX = 54;
  const barW = W - 108;
  ctx.fillStyle = "rgba(255,255,255,0.09)";
  ctx.fillRect(barX, 268, barW, 10);
  ctx.fillStyle = enough ? "#37a85b" : ACCENT;
  ctx.fillRect(barX, 268, barW * Math.min(1, seconds / minSeconds), 10);

  // The live level, as a row of bars: the picture of a voice everyone knows.
  if (live) {
    const loud = Math.min(1, (level ?? 0) * 5.5);
    const bars = 34;
    for (let i = 0; i < bars; i++) {
      const t = i / (bars - 1);
      // A bell, so the middle of the row is tallest - it reads as a voice
      // rather than as a progress bar.
      const shape = Math.sin(t * Math.PI);
      const h = 6 + loud * shape * 92 * (0.55 + Math.random() * 0.45);
      ctx.fillStyle = `rgba(255,107,53,${0.25 + loud * 0.6})`;
      ctx.fillRect(barX + t * (barW - 12), 420 - h, 7, h);
    }
  }

  ctx.fillStyle = "rgba(245,243,239,0.62)";
  ctx.font = "400 25px Inter, system-ui, sans-serif";
  if (status === "recording") {
    ctx.fillText(
      enough ? "Enough to work with. Keep going for a closer match." : "Keep talking.",
      barX,
      474
    );
  } else if (status === "recorded") {
    ctx.fillText("Name it on the panel, or press the button to go again.", barX, 474);
  } else {
    ctx.fillText("Press the orange button on the stand.", barX, 474);
  }
}
