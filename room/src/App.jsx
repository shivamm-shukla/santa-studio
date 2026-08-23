import { useEffect, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import { useStudio } from "./store.js";
import { startSimulation } from "./sim/pipelineSim.js";
import useLudoGame from "./ludo/useLudoGame.js";
import Scene from "./world/Scene.jsx";
import Hud from "./ui/Hud.jsx";

export default function App() {
  const theme = useStudio((s) => s.theme);
  const focus = useStudio((s) => s.focus);
  const backToRoom = useStudio((s) => s.backToRoom);
  const toggleTheme = useStudio((s) => s.toggleTheme);
  // ?ludoStep=260 slows the pieces down (ms per square) if you want to watch
  // a move land square by square.
  const stepMs = useMemo(
    () => Number(new URLSearchParams(location.search).get("ludoStep")) || 190,
    []
  );
  const ludo = useLudoGame({ stepMs });

  // Simulated pipeline. Swapping this for a WebSocket that emits the same
  // events (see net/events.js) is the whole of the backend wiring.
  // ?speed=8 runs a whole simulated run in about a minute.
  useEffect(() => {
    const speed = Number(new URLSearchParams(location.search).get("speed")) || 1;
    return startSimulation(useStudio, { speed });
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // Dev-only handles, so the room can be driven from the console while
  // building it (window.__studio.getState().focusDesk("research"), and
  // window.__ludo.roll() / .pick(0) to play without a mouse).
  if (import.meta.env.DEV) {
    window.__studio = useStudio;
    window.__ludo = ludo;
  }

  useEffect(() => {
    const onKey = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
      if (e.key === "Escape") backToRoom();
      if (e.key === "l" || e.key === "L") toggleTheme();
      if (focus.kind !== "table") return;
      if (e.key === "r" || e.key === "R" || e.code === "Space") {
        e.preventDefault();
        ludo.roll();
      }
      if (["1", "2", "3", "4"].includes(e.key)) ludo.pick(Number(e.key) - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [focus.kind, ludo, backToRoom, toggleTheme]);

  return (
    <>
      <Canvas
        shadows
        dpr={[1, 2]}
        camera={{ fov: 50, near: 0.1, far: 120, position: [0, 6, 14] }}
        gl={{ antialias: true }}
        onCreated={({ scene, gl }) => {
          scene.fog = new THREE.Fog("#07070b", 15, 40);
          gl.toneMapping = THREE.ACESFilmicToneMapping;
          gl.toneMappingExposure = 1.05;
        }}
        onPointerMissed={() => backToRoom()}
      >
        <Scene ludo={ludo} />
      </Canvas>
      <Hud ludo={ludo} />
    </>
  );
}
