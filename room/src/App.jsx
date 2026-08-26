import { useEffect, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import { useStudio } from "./store.js";
import { startSimulation } from "./sim/pipelineSim.js";
import { connectRun, startRun } from "./net/liveSource.js";
import useCommission from "./studio/useCommission.js";
import useVoices from "./studio/useVoices.js";
import useLudoGame from "./ludo/useLudoGame.js";
import { useRecorder } from "./studio/useRecorder.js";
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
  // The microphone belongs to the app rather than to a panel, because two
  // things need it: the booth's controls, and the booth itself, which reacts
  // to the level while you talk.
  const mic = useRecorder();
  // Commissioning a run happens at the board in the room, and the room then
  // attaches to what it started - so briefing and watching are one thing.
  const commission = useCommission();
  // The rack and the board both need the list of voices, and the rack changes
  // it - so it is owned here rather than fetched twice.
  const voices = useVoices();

  // Where the room gets its events.
  //   ?run=<id>      watch a real run that is already going
  //   ?start=<niche> begin one and watch it
  //   neither        the demo simulation, at ?speed=8 to see it all quickly
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const existing = params.get("run");
    const niche = params.get("start");

    if (!existing && !niche) {
      useStudio.getState().setConnection("sim");
      const speed = Number(params.get("speed")) || 1;
      return startSimulation(useStudio, { speed });
    }

    let disconnect = null;
    let cancelled = false;
    const store = useStudio.getState();
    store.setConnection("connecting");

    (async () => {
      try {
        const runId = existing || (await startRun({ niche, topic: params.get("topic") }));
        if (cancelled) return;
        store.setRun(runId);
        // Keep the id in the URL so a reload rejoins the same run rather
        // than starting a second one.
        if (!existing) {
          const url = new URL(location.href);
          url.searchParams.delete("start");
          url.searchParams.set("run", runId);
          history.replaceState({}, "", url);
        }
        disconnect = connectRun(useStudio, runId, {
          onStatus: (status) => useStudio.getState().setConnection(status),
        });
      } catch (err) {
        if (!cancelled) useStudio.getState().setConnection("offline");
        console.error("Could not attach to a run:", err);
      }
    })();

    return () => {
      cancelled = true;
      disconnect?.();
    };
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  // ?at=booth walks you to the microphone on arrival, so a link from the rest
  // of the studio lands somewhere rather than at the door.
  useEffect(() => {
    const where = new URLSearchParams(location.search).get("at");
    if (where === "booth") useStudio.getState().focusBooth();
  }, []);

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
        <Scene ludo={ludo} mic={mic} commission={commission} voices={voices} />
      </Canvas>
      <Hud ludo={ludo} mic={mic} commission={commission} voices={voices} />
    </>
  );
}
