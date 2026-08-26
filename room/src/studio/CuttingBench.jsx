import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { ACCENT, DATA } from "../theme.js";

/* The set on the far wall.

   It is a television, not a poster: a bezel, a screen inset behind it, a
   standby light underneath. What is on it is the Clips app - a standby card
   when nothing has been cut, and otherwise the source as a line with every
   kept moment standing on it, the taller the better it scored. Which parts of
   a half-hour video are worth keeping is then something you read off the wall
   from across the room, before you ever walk up to it. */

const W = 1280;
const H = 720;

function rounded(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function chrome(ctx) {
  ctx.fillStyle = "#0a0a0f";
  ctx.fillRect(0, 0, W, H);

  // The app's own top bar, so the wall and the panel you open are one screen.
  ctx.fillStyle = "rgba(255,255,255,0.03)";
  ctx.fillRect(0, 0, W, 78);
  ctx.strokeStyle = "rgba(255,255,255,0.09)";
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(0, 78);
  ctx.lineTo(W, 78);
  ctx.stroke();

  ctx.fillStyle = DATA;
  ctx.beginPath();
  ctx.arc(52, 39, 6, 0, Math.PI * 2);
  ctx.fill();

  ctx.font = "500 20px Inter, system-ui, sans-serif";
  ctx.letterSpacing = "3px";
  ctx.fillStyle = "rgba(245,243,239,0.55)";
  ctx.fillText("SANTA STUDIO", 74, 46);
  ctx.fillStyle = DATA;
  ctx.font = "700 20px Inter, system-ui, sans-serif";
  ctx.fillText("CLIPS", 262, 46);
  ctx.letterSpacing = "0px";
}

function paint(ctx, project, selected) {
  ctx.clearRect(0, 0, W, H);
  chrome(ctx);

  const candidates = project?.candidates ?? [];

  if (!candidates.length) {
    // Standby. It says what the set is for, because a blank screen on a wall
    // teaches nobody that this is where shorts are made.
    ctx.fillStyle = "rgba(245,243,239,0.88)";
    ctx.font = "600 46px Inter, system-ui, sans-serif";
    ctx.fillText("Cut shorts from any video.", 64, 232);

    ctx.fillStyle = "rgba(245,243,239,0.42)";
    ctx.font = "400 25px Inter, system-ui, sans-serif";
    ctx.fillText("A finished run, a file, or a YouTube link.", 64, 280);

    const steps = [
      ["1", "Bring a video in", "run · upload · link"],
      ["2", "Keep the best moments", "ranked, with reasons"],
      ["3", "Publish or schedule", "straight to YouTube"],
    ];
    steps.forEach(([n, title, sub], i) => {
      const x = 64 + i * 390;
      const y = 372;
      ctx.strokeStyle = "rgba(255,255,255,0.10)";
      ctx.lineWidth = 2;
      rounded(ctx, x, y, 350, 150, 16);
      ctx.stroke();

      ctx.fillStyle = DATA;
      ctx.font = "700 17px 'JetBrains Mono', monospace";
      ctx.fillText(n, x + 26, y + 44);

      ctx.fillStyle = "rgba(245,243,239,0.86)";
      ctx.font = "600 25px Inter, system-ui, sans-serif";
      ctx.fillText(title, x + 26, y + 88);

      ctx.fillStyle = "rgba(245,243,239,0.38)";
      ctx.font = "400 19px Inter, system-ui, sans-serif";
      ctx.fillText(sub, x + 26, y + 122);
    });

    ctx.fillStyle = "rgba(245,243,239,0.34)";
    ctx.font = "500 21px Inter, system-ui, sans-serif";
    ctx.fillText("Walk up to the screen to start.", 64, 626);
    return;
  }

  ctx.fillStyle = "rgba(245,243,239,0.72)";
  ctx.font = "500 28px Inter, system-ui, sans-serif";
  const title = project.source?.title ?? "";
  ctx.fillText(title.length > 56 ? `${title.slice(0, 55)}…` : title, 64, 142);

  // The source, as a line, with each kept moment standing on it.
  const total = Math.max(project.source?.duration || 1, 1);
  const left = 64;
  const width = W - 128;
  const base = H - 116;

  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.fillRect(left, base, width, 4);

  candidates.forEach((clip) => {
    const x = left + (clip.start_time / total) * width;
    const w = Math.max(8, ((clip.end_time - clip.start_time) / total) * width);
    const h = 50 + (clip.score || 0) * 250;
    const on = clip.clip_id === selected;

    ctx.fillStyle = on ? ACCENT : "rgba(0,229,255,0.40)";
    rounded(ctx, x, base - h, w, h, Math.min(5, w / 2));
    ctx.fill();

    if (on) {
      ctx.fillStyle = "#f5f3ef";
      ctx.font = "600 28px Inter, system-ui, sans-serif";
      const hook = clip.hook_text || clip.suggested_title || "";
      ctx.fillText(hook.length > 46 ? `${hook.slice(0, 45)}…` : hook, left, base - h - 26);
    }
  });

  ctx.fillStyle = "rgba(245,243,239,0.40)";
  ctx.font = "500 21px Inter, system-ui, sans-serif";
  ctx.fillText(`${candidates.length} moments worth keeping`, left, H - 48);
}

export default function CuttingBench({ position, rotation, project, selected, focused, onSelect }) {
  const light = useRef();
  const standby = useRef();

  const { texture, ctx } = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = W;
    canvas.height = H;
    const context = canvas.getContext("2d");
    const map = new THREE.CanvasTexture(canvas);
    map.colorSpace = THREE.SRGBColorSpace;
    map.anisotropy = 8;
    return { texture: map, ctx: context };
  }, []);

  const signature = `${project?.project_id ?? ""}|${project?.candidates?.length ?? 0}|${selected}`;
  useMemo(() => {
    paint(ctx, project, selected);
    texture.needsUpdate = true;
  }, [signature, ctx, texture, project, selected]);

  useFrame((state, dt) => {
    if (light.current) {
      // A screen this size lights the wall it is on. Brighter when you are
      // standing at it, because that is when it is actually showing you
      // something rather than sitting there.
      const target = focused ? 6 : project?.candidates?.length ? 2.6 : 1.4;
      light.current.intensity += (target - light.current.intensity) * Math.min(1, dt * 6);
    }
    if (standby.current) {
      const t = state.clock.elapsedTime;
      standby.current.opacity = 0.45 + Math.sin(t * 2) * 0.25;
    }
  });

  const screenW = 3.2;
  const screenH = (screenW * H) / W;

  return (
    <group
      position={position}
      rotation={[0, rotation, 0]}
      onClick={onSelect}
      onPointerOver={() => (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "")}
    >
      {/* Bezel. Thin, like a set made this decade. */}
      <mesh castShadow>
        <boxGeometry args={[screenW + 0.09, screenH + 0.09, 0.06]} />
        <meshStandardMaterial color="#08080c" roughness={0.42} metalness={0.55} />
      </mesh>
      {/* The panel itself, sunk a little behind the bezel. */}
      <mesh position={[0, 0, 0.031]}>
        <planeGeometry args={[screenW, screenH]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
      {/* Standby light under the bottom edge. */}
      <mesh position={[0, -(screenH / 2) - 0.032, 0.032]}>
        <circleGeometry args={[0.012, 12]} />
        <meshBasicMaterial ref={standby} color={DATA} transparent opacity={0.5} toneMapped={false} />
      </mesh>

      <pointLight ref={light} color={DATA} distance={6.5} decay={1.6} intensity={1.4} position={[0, 0, 0.8]} />
    </group>
  );
}
