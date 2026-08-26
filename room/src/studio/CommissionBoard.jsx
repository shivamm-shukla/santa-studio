import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import useScreenRect from "./useScreenRect.js";
import { ACCENT } from "../theme.js";

/* The board a run is commissioned at.

   Everything the studio needs to start is written here, on a wall you walk up
   to, rather than on a form somewhere else. The panel is painted into a canvas
   and used as a texture - the same way every screen in this room works - so
   what it says is part of the object and not HTML floating over it.

   It repaints only when the brief changes, because a texture upload every
   frame for a board that is mostly still is the sort of thing that quietly
   costs a scene its frame rate. */

const W = 1024;
const H = 640;

function paint(ctx, brief, live) {
  ctx.clearRect(0, 0, W, H);

  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, "#16161f");
  g.addColorStop(1, "#0d0d14");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);

  ctx.strokeStyle = "rgba(255,255,255,0.10)";
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, W - 3, H - 3);

  ctx.fillStyle = ACCENT;
  ctx.font = "700 22px Inter, system-ui, sans-serif";
  ctx.letterSpacing = "6px";
  ctx.fillText(live ? "RUNNING" : "THE BRIEF", 54, 74);
  ctx.letterSpacing = "0px";

  ctx.fillStyle = "rgba(255,255,255,0.10)";
  ctx.fillRect(54, 92, W - 108, 2);

  const rows = [
    ["Niche", brief.niche || "—"],
    ["Topic", brief.topic || "whatever people are reading"],
    ["Voice", brief.voiceName || "the default voice"],
    ["Length", `${brief.minutes} minutes`],
    ["Review", brief.reviewMode === "checkpoints" ? "stop at checkpoints" : "run it through"],
    [
      "References",
      brief.referenceUrls.length
        ? `${brief.referenceUrls.length} link${brief.referenceUrls.length > 1 ? "s" : ""}`
        : "none",
    ],
  ];

  rows.forEach(([label, value], i) => {
    const y = 156 + i * 74;
    ctx.fillStyle = "rgba(245,243,239,0.42)";
    ctx.font = "600 21px Inter, system-ui, sans-serif";
    ctx.fillText(label.toUpperCase(), 54, y);

    ctx.fillStyle = "#f5f3ef";
    ctx.font = "600 34px Inter, system-ui, sans-serif";
    const text = String(value);
    ctx.fillText(text.length > 40 ? `${text.slice(0, 39)}…` : text, 300, y + 4);
  });
}

export default function CommissionBoard({ position, rotation, brief, live, focused, onSelect }) {
  /* The panel is a real screen, so the software that belongs on it is laid
     into its picture rather than floating in front of it. */
  const screen = useScreenRect("board", 2.42, 1.5, focused);
  const frame = useRef();

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

  // Repaint on change, not on frame. The key is every value that is drawn.
  const signature = `${brief.niche}|${brief.topic}|${brief.voiceName}|${brief.minutes}|${brief.reviewMode}|${brief.referenceUrls.length}|${live}`;
  useMemo(() => {
    paint(ctx, brief, live);
    texture.needsUpdate = true;
  }, [signature, ctx, texture, brief, live]);

  useFrame((_, dt) => {
    if (!frame.current) return;
    const target = focused ? 1 : live ? 0.55 : 0.22;
    frame.current.intensity += (target * 5 - frame.current.intensity) * Math.min(1, dt * 6);
  });

  return (
    <group position={position} rotation={[0, rotation, 0]} onClick={onSelect}>
      {/* the board */}
      <mesh castShadow>
        <boxGeometry args={[2.5, 1.56, 0.07]} />
        <meshStandardMaterial color="#101017" roughness={0.55} metalness={0.35} />
      </mesh>
      <mesh ref={screen} position={[0, 0, 0.037]}>
        <planeGeometry args={[2.42, 1.5]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>

      {/* it throws a little light onto the wall, which is how you notice it */}
      <pointLight ref={frame} color={ACCENT} distance={4.5} intensity={1} position={[0, 0, 0.6]} />
    </group>
  );
}
