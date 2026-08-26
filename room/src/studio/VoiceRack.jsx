import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { ACCENT } from "../theme.js";

/* The rack of voices, on the wall of the recording room.

   One slot per profile, and the slot you have chosen is the one that is lit -
   so which voice is selected is a fact about the room rather than a highlight
   in a list. A rack with nothing in it says so on its own face, because an
   empty shelf and a broken shelf look identical otherwise. */

const W = 512;
const H = 768;

function paint(ctx, names, selected) {
  ctx.clearRect(0, 0, W, H);

  ctx.fillStyle = "#101017";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, W - 3, H - 3);

  ctx.fillStyle = ACCENT;
  ctx.font = "700 20px Inter, system-ui, sans-serif";
  ctx.letterSpacing = "5px";
  ctx.fillText("VOICES", 34, 56);
  ctx.letterSpacing = "0px";

  if (!names.length) {
    ctx.fillStyle = "rgba(245,243,239,0.34)";
    ctx.font = "500 24px Inter, system-ui, sans-serif";
    ctx.fillText("Nothing on the rack yet.", 34, 132);
    ctx.font = "400 20px Inter, system-ui, sans-serif";
    ctx.fillText("Record one at the microphone.", 34, 168);
    return;
  }

  names.slice(0, 8).forEach((entry, i) => {
    const y = 104 + i * 76;
    const on = entry.id === selected;

    ctx.fillStyle = on ? "rgba(255,107,53,0.16)" : "rgba(255,255,255,0.04)";
    ctx.fillRect(28, y - 34, W - 56, 60);
    if (on) {
      ctx.fillStyle = ACCENT;
      ctx.fillRect(28, y - 34, 4, 60);
    }

    ctx.fillStyle = on ? "#ffffff" : "rgba(245,243,239,0.78)";
    ctx.font = "600 25px Inter, system-ui, sans-serif";
    const name = entry.name.length > 20 ? `${entry.name.slice(0, 19)}…` : entry.name;
    ctx.fillText(name, 48, y - 4);

    ctx.fillStyle = on ? "rgba(255,255,255,0.7)" : "rgba(245,243,239,0.40)";
    ctx.font = "500 18px Inter, system-ui, sans-serif";
    ctx.fillText(entry.mood ? entry.mood : "no mood", 48, y + 20);
  });
}

export default function VoiceRack({ position, rotation, voices, order, selected, focused, onSelect }) {
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

  const entries = order.map((id) => ({
    id,
    name: voices[id]?.name ?? "Untitled",
    mood: voices[id]?.filter_preset,
  }));

  // Repaint when what is written changes, not every frame.
  const signature = entries.map((e) => `${e.id}:${e.name}:${e.mood ?? ""}`).join("|") + `#${selected}`;
  useMemo(() => {
    paint(ctx, entries, selected);
    texture.needsUpdate = true;
  }, [signature, ctx, texture, entries, selected]);

  useFrame((_, dt) => {
    if (!light.current) return;
    const target = focused ? 4.5 : 1.4;
    light.current.intensity += (target - light.current.intensity) * Math.min(1, dt * 6);
  });

  return (
    <group position={position} rotation={[0, rotation, 0]} onClick={onSelect}>
      <mesh castShadow>
        <boxGeometry args={[1.15, 1.72, 0.08]} />
        <meshStandardMaterial color="#0e0e14" roughness={0.55} metalness={0.35} />
      </mesh>
      <mesh position={[0, 0, 0.042]}>
        <planeGeometry args={[1.08, 1.64]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
      <pointLight ref={light} color={ACCENT} distance={3.6} intensity={1.4} position={[0, 0, 0.5]} />
    </group>
  );
}
