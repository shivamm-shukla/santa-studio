import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

/* A small floating label so you can tell who's who from across the room.
   It carries a name and a status colour and nothing else — the actual work,
   and any message an agent receives, only ever appears on their own screen. */

const world = new THREE.Vector3();

export default function NamePlate({ label, color, status, ...props }) {
  const sprite = useRef();
  const { texture, dotMat } = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0, 0, 512, 128);
    ctx.fillStyle = "rgba(8,8,12,0.72)";
    ctx.beginPath();
    ctx.roundRect(56, 28, 400, 72, 36);
    ctx.fill();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.stroke();
    ctx.font = "700 40px Inter, system-ui, sans-serif";
    ctx.fillStyle = "#F5F3EF";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(label, 256, 66);
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    return { texture: tex, dotMat: new THREE.Color(color) };
  }, [label, color]);

  useFrame(({ clock, camera }) => {
    const s = sprite.current;
    if (!s) return;
    // An unopened message makes the plate breathe; nothing else moves it.
    const pulse = status === "incoming" ? 1 + Math.sin(clock.elapsedTime * 5) * 0.09 : 1;
    // Scale with distance so a label is the same size on screen wherever it
    // is — a name tag shouldn't turn into a billboard when you walk past it.
    s.getWorldPosition(world);
    const d = THREE.MathUtils.clamp(camera.position.distanceTo(world) / 9, 0.45, 1.5);
    s.scale.set(1.5 * pulse * d, 0.375 * pulse * d, 1);
    // Close up, the label is in the way of the thing it labels.
    const near = camera.position.distanceTo(world);
    const fade = THREE.MathUtils.smoothstep(near, 2.0, 3.4);
    s.material.opacity = fade * (status === "idle" ? 0.5 : 1);
    s.visible = fade > 0.02;
  });

  return (
    <sprite ref={sprite} {...props}>
      <spriteMaterial map={texture} transparent depthWrite={false} color={dotMat.clone().lerp(new THREE.Color("#ffffff"), 0.75)} />
    </sprite>
  );
}
