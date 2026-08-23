import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { SCREEN_W, SCREEN_H, drawSleeping, drawEmail, paintScreen } from "./screenDraw.js";

/* Turns a 2D canvas into the laptop's panel. Repainting is deliberately
   stingy: a sleeping or finished screen is painted once and left alone, and
   only screens that are actually doing something animate — the focused one
   a little faster, since that's the one being read. */

export default function LaptopScreen({ agent, agentState, roster, stage, focused }) {
  const { ctx, texture } = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = SCREEN_W;
    canvas.height = SCREEN_H;
    const c = canvas.getContext("2d");
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 4;
    return { ctx: c, texture: tex };
  }, []);

  const acc = useRef(1e9);
  const lastKey = useRef(null);

  useFrame(({ clock }, dt) => {
    const { status, lines, email, progress } = agentState;
    const key = `${status}|${lines.length}|${email?.subject ?? ""}|${stage}|${roster?.version ?? 0}`;
    const animated = status === "working" || agent.screen === "board";
    const interval = focused ? 1 / 15 : animated ? 1 / 8 : Infinity;

    acc.current += dt;
    if (key === lastKey.current && acc.current < interval) return;
    acc.current = 0;
    lastKey.current = key;

    const t = clock.elapsedTime;
    if (agent.screen === "board") {
      paintScreen(ctx, "board", { color: agent.color, roster: roster.list, stage, t });
    } else if (status === "idle") {
      drawSleeping(ctx);
    } else if (status === "incoming") {
      drawEmail(ctx, { ...email, color: agent.color });
    } else {
      paintScreen(ctx, agent.screen, {
        lines,
        color: agent.color,
        t,
        progress: status === "done" ? 1 : progress,
      });
    }
    texture.needsUpdate = true;
  });

  return (
    /* toneMapped off: a screen emits its own light, it shouldn't dim when the
       room lights go out — that difference is most of what sells the dark mode. */
    <meshBasicMaterial map={texture} toneMapped={false} />
  );
}
