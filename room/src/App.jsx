import { useEffect, useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import { useStudio } from "./store.js";
import { FILM_SECONDS, filmPose, SHOT_FOCUS } from "./world/film.js";
import { demoAt, TOTAL as DEMO_SECONDS } from "./world/demo.js";
import { connectRun, startRun } from "./net/liveSource.js";
import useCommission from "./studio/useCommission.js";
import useVoices from "./studio/useVoices.js";
import useBench from "./studio/useBench.js";
import useProjects from "./studio/useProjects.js";
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
  const bench = useBench();
  // Everything the studio has made. The Manager's board shows it, because
  // knowing what is in the building is the Manager's job.
  const projects = useProjects();

  // Where the room gets its events.
  //   ?run=<id>      watch a real run that is already going
  //   ?start=<niche> begin one and watch it
  //   neither        attach to whatever is really running, or sit idle
  //
  // There used to be a rehearsal here, and it was what you got by default: a
  // scripted walk through the state machine with placeholder content, built
  // to have something to film before the backend existed. Opening the room
  // therefore showed desks working, sources scrolling and a fact-check
  // running on Mysorean rockets - a topic nobody had asked for. A chip in the
  // corner said "nothing running" and stood no chance against a whole room
  // performing a run. The backend is here now, so the room shows it or shows
  // an idle studio, and there is no third thing it can be doing.
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const existing = params.get("run");
    const niche = params.get("start");

    let disconnect = null;
    let cancelled = false;
    const store = useStudio.getState();
    store.setConnection("connecting");

    (async () => {
      try {
        // Nothing named: ask what is actually going on rather than assuming.
        if (!existing && !niche) {
          const live = await fetch("/api/runs/live")
            .then((r) => (r.ok ? r.json() : null))
            .catch(() => null);
          if (cancelled) return;
          if (!live?.run_id) {
            store.setConnection("idle");
            return;
          }
          store.setRun(live.run_id);
          disconnect = connectRun(useStudio, live.run_id, {
            onStatus: (status) => useStudio.getState().setConnection(status),
          });
          return;
        }

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

  // ?at=<place> walks you somewhere on arrival, so a link from the landing
  // page or from anywhere else lands you at the thing it was about rather
  // than at the door.
  // ?shot=1 is photography mode: the flat UI is out of the way and the camera
  // stands back rather than up close, because a working pose fills the frame
  // with one panel and shows none of the room.
  const shooting = useMemo(
    () => new URLSearchParams(location.search).get("shot") === "1",
    []
  );

  /* ?film=1 hands the camera to the shot list in world/film.js and takes the
     flat UI away. The recorder drives it a frame at a time through
     window.__filmSeek(t), which also walks the room to whatever that shot is
     about, so the screens the camera is pointed at are the ones that are
     awake. See film.mjs. */
  const filming = useMemo(
    () => new URLSearchParams(location.search).get("film") === "1",
    []
  );

  /* ?demo=1 is the long shot list in world/demo.js - the one with the full
     turn round the room and time at each place. Same contract as film mode:
     the recorder seeks, the room renders exactly that frame. */
  const demoing = useMemo(
    () => new URLSearchParams(location.search).get("demo") === "1",
    []
  );

  useEffect(() => {
    if (!demoing) return undefined;
    const store = useStudio.getState();
    store.setFilming(true);
    store.setDemoing(true);
    window.__demoT = 0;
    window.__demoSeconds = DEMO_SECONDS;
    window.__demoSeek = (t) => {
      window.__demoT = t;
      const shot = demoAt(t);
      const now = useStudio.getState();
      now.setLightLevel(shot.lights);
      // Only on a change: setting focus every frame restarts every panel
      // animation thirty times a second.
      if (shot.focus && (now.focus.kind !== shot.focus.kind || now.focus.id !== shot.focus.id)) {
        useStudio.setState({ focus: { ...shot.focus, photo: null }, interacted: true });
      }
    };
    window.__demoSeek(0);
    return () => {
      const now = useStudio.getState();
      now.setFilming(false);
      now.setDemoing(false);
      now.setLightLevel(null);
      delete window.__demoT;
      delete window.__demoSeconds;
      delete window.__demoSeek;
    };
  }, [demoing]);

  useEffect(() => {
    if (!filming) return undefined;
    useStudio.getState().setFilming(true);
    window.__filmT = 0;
    window.__filmSeconds = FILM_SECONDS;
    window.__filmSeek = (t) => {
      window.__filmT = t;
      const { shot } = filmPose(t);
      const want = SHOT_FOCUS[shot];
      const store = useStudio.getState();
      // Only when it changes: setting focus every frame would restart the
      // panel animations thirty times a second.
      if (want && store.focus.kind !== want.kind) {
        useStudio.setState({ focus: { ...want, photo: null }, interacted: true });
      }
    };
    window.__filmSeek(0);
    return () => {
      useStudio.getState().setFilming(false);
      delete window.__filmT;
      delete window.__filmSeconds;
      delete window.__filmSeek;
    };
  }, [filming]);

  useEffect(() => {
    const store = useStudio.getState();
    const where = new URLSearchParams(location.search).get("at");
    if (shooting && where) {
      store.focusPhoto(where);
      return;
    }
    const go = {
      booth: store.focusBooth,
      board: store.focusBoard,
      rack: store.focusRack,
      bench: store.focusBench,
      table: store.focusTable,
    }[where];
    if (go) go();
  }, [shooting]);

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
        <Scene ludo={ludo} mic={mic} commission={commission} voices={voices} bench={bench} />
      </Canvas>
      {!shooting && !filming && (
        <Hud
          ludo={ludo}
          mic={mic}
          commission={commission}
          voices={voices}
          bench={bench}
          projects={projects}
          bare={demoing}
        />
      )}
    </>
  );
}
