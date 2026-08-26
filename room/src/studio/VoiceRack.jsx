import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import useScreenRect from "./useScreenRect.js";
import { ACCENT } from "../theme.js";

/* The rack of voices, on the wall of the recording room.

   One slot per profile, and the slot you have chosen is the one that is lit -
   so which voice is selected is a fact about the room rather than a highlight
   in a list. A rack with nothing in it says so on its own face, because an
   empty shelf and a broken shelf look identical otherwise. */

const W = 768;
const H = 1152;

function paint(ctx, names, selected) {
  ctx.clearRect(0, 0, W, H);

  ctx.fillStyle = "#14141d";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, W - 3, H - 3);

  ctx.fillStyle = ACCENT;
  ctx.font = "700 30px Inter, system-ui, sans-serif";
  ctx.letterSpacing = "7px";
  ctx.fillText("VOICES", 50, 84);
  ctx.letterSpacing = "0px";

  if (!names.length) {
    ctx.fillStyle = "rgba(245,243,239,0.34)";
    ctx.font = "600 40px Inter, system-ui, sans-serif";
    ctx.fillText("Nothing on the rack.", 50, 200);
    ctx.font = "400 31px Inter, system-ui, sans-serif";
    ctx.fillText("Record one at the", 50, 254);
    ctx.fillText("microphone.", 50, 296);
    return;
  }

  names.slice(0, 8).forEach((entry, i) => {
    const y = 160 + i * 116;
    const on = entry.id === selected;

    ctx.fillStyle = on ? "rgba(255,107,53,0.16)" : "rgba(255,255,255,0.04)";
    ctx.fillRect(42, y - 52, W - 84, 92);
    if (on) {
      ctx.fillStyle = ACCENT;
      ctx.fillRect(42, y - 52, 7, 92);
    }

    ctx.fillStyle = on ? "#ffffff" : "rgba(245,243,239,0.88)";
    ctx.font = "700 38px Inter, system-ui, sans-serif";
    const name = entry.name.length > 20 ? `${entry.name.slice(0, 19)}…` : entry.name;
    ctx.fillText(name, 70, y - 6);

    ctx.fillStyle = on ? "rgba(255,255,255,0.82)" : "rgba(245,243,239,0.55)";
    ctx.font = "500 27px Inter, system-ui, sans-serif";
    ctx.fillText(entry.mood ? entry.mood : "no mood", 70, y + 30);
  });
}

export default function VoiceRack({ position, rotation, voices, order, selected, focused, onSelect }) {
  /* The panel is a real screen, so the software that belongs on it is laid
     into its picture rather than floating in front of it. */
  const screen = useScreenRect("rack", 1.42, 2.08, focused);
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
        <boxGeometry args={[1.5, 2.16, 0.08]} />
        <meshStandardMaterial color="#0e0e14" roughness={0.55} metalness={0.35} />
      </mesh>
      <mesh ref={screen} position={[0, 0, 0.042]}>
        <planeGeometry args={[1.42, 2.08]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>
      <pointLight ref={light} color={ACCENT} distance={3.6} intensity={1.4} position={[0, 0, 0.5]} />
    </group>
  );
}
