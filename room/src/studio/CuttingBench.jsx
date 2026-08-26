import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { ACCENT, DATA } from "../theme.js";

/* The cutting bench. A wall panel showing the moments found in the last video
   it was given - each one a strip along a timeline, the taller the better it
   scored, so which parts of a half-hour video are worth keeping is something
   you read off the wall at a glance. */

const W = 1024;
const H = 512;

function paint(ctx, project, selected) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#0f0f16";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, W - 3, H - 3);

  ctx.fillStyle = DATA;
  ctx.font = "700 22px Inter, system-ui, sans-serif";
  ctx.letterSpacing = "6px";
  ctx.fillText("CUTTING BENCH", 46, 66);
  ctx.letterSpacing = "0px";

  const candidates = project?.candidates ?? [];
  if (!candidates.length) {
    ctx.fillStyle = "rgba(245,243,239,0.34)";
    ctx.font = "500 28px Inter, system-ui, sans-serif";
    ctx.fillText("Nothing on the bench.", 46, 150);
    ctx.font = "400 22px Inter, system-ui, sans-serif";
    ctx.fillText("Finish a run, then cut it up here.", 46, 190);
    return;
  }

  ctx.fillStyle = "rgba(245,243,239,0.62)";
  ctx.font = "500 24px Inter, system-ui, sans-serif";
  const title = project.source?.title ?? "";
  ctx.fillText(title.length > 52 ? `${title.slice(0, 51)}…` : title, 46, 106);

  // The source, as a line, with each kept moment standing on it.
  const total = Math.max(project.source?.duration || 1, 1);
  const left = 46;
  const width = W - 92;
  const base = H - 78;

  ctx.fillStyle = "rgba(255,255,255,0.08)";
  ctx.fillRect(left, base, width, 4);

  candidates.forEach((clip) => {
    const x = left + (clip.start_time / total) * width;
    const w = Math.max(6, ((clip.end_time - clip.start_time) / total) * width);
    const h = 40 + (clip.score || 0) * 190;
    const on = clip.clip_id === selected;

    ctx.fillStyle = on ? ACCENT : "rgba(0,229,255,0.42)";
    ctx.fillRect(x, base - h, w, h);

    if (on) {
      ctx.fillStyle = "#f5f3ef";
      ctx.font = "600 25px Inter, system-ui, sans-serif";
      const hook = clip.hook_text || clip.suggested_title || "";
      ctx.fillText(hook.length > 44 ? `${hook.slice(0, 43)}…` : hook, left, base - h - 22);
    }
  });

  ctx.fillStyle = "rgba(245,243,239,0.38)";
  ctx.font = "500 19px Inter, system-ui, sans-serif";
  ctx.fillText(`${candidates.length} moments worth keeping`, left, H - 34);
}

export default function CuttingBench({ position, rotation, project, selected, focused, onSelect }) {
  const light = useRef();

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

  useFrame((_, dt) => {
    if (!light.current) return;
    const target = focused ? 4.5 : project?.candidates?.length ? 1.8 : 0.7;
    light.current.intensity += (target - light.current.intensity) * Math.min(1, dt * 6);
  });

  return (
    <group position={position} rotation={[0, rotation, 0]} onClick={onSelect}>
      <mesh castShadow>
        <boxGeometry args={[2.6, 1.35, 0.07]} />
        <meshStandardMaterial color="#0d0d13" roughness={0.55} metalness={0.35} />
      </mesh>
      <mesh position={[0, 0, 0.037]}>
        <planeGeometry args={[2.52, 1.28]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
      <pointLight ref={light} color={DATA} distance={4.5} intensity={0.7} position={[0, 0, 0.6]} />
    </group>
  );
}
