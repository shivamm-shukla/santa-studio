import { useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";

import {
  ACCENT,
  DATA,
  PLATFORM_NAMES,
  platformTexture,
  stationTexture,
  titleTexture,
} from "./draw.js";

/* The landing is a place rather than a page: you start inside it, and
   scrolling moves you *through* it rather than moving text past you. Every
   station is a real object at a real depth, so it arrives, passes, and is
   behind you - which is the whole difference between reading about a pipeline
   and walking down one.

   Nothing here is decoration for its own sake. The stations are the pipeline's
   actual stages, in order; the badges at the end are the places a finished
   video goes; the dust is there because a space with nothing in it gives the
   eye no sense of movement, and without that the camera does not feel like it
   is travelling. */

export const STATIONS = [
  {
    note: "it finds out",
    title: "Research",
    body: "Three indexes, none of which needs a key. The sources in the description are the ones it actually read.",
  },
  {
    note: "it writes",
    title: "Script",
    body: "Structure learned from the channels you point it at. Substance from the research. Never their content.",
  },
  {
    note: "it speaks",
    title: "Your voice",
    body: "Cloned once from a few seconds of you, then every video from here on is read in it.",
  },
  {
    note: "it looks",
    title: "Footage",
    body: "Stock that is actually of the subject, and where none exists, stills made to look photographed.",
  },
  {
    note: "it cuts",
    title: "The edit",
    body: "Shots, moves, charts built from real figures, one grade over all of it. Then captions, then shorts.",
  },
];

const SPACING = 26;          // how far apart the stations sit, in world units
const START_Z = 6;           // where the camera begins, in front of the title
export const TRAVEL = SPACING * (STATIONS.length + 1);

/* ---- Dust ------------------------------------------------------------- */

function Dust({ count = 900 }) {
  const points = useRef();

  const geometry = useMemo(() => {
    const positions = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) {
      // A tube around the path rather than a cube: everything lands where the
      // camera will actually pass it.
      const angle = Math.random() * Math.PI * 2;
      const radius = 4 + Math.random() * 22;
      positions[i * 3] = Math.cos(angle) * radius;
      positions[i * 3 + 1] = Math.sin(angle) * radius * 0.55;
      positions[i * 3 + 2] = START_Z - Math.random() * (TRAVEL + 40);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return g;
  }, [count]);

  useFrame((_, dt) => {
    if (points.current) points.current.rotation.z += dt * 0.012;
  });

  return (
    <points ref={points} geometry={geometry}>
      <pointsMaterial
        size={0.075}
        color="#9fb4c8"
        transparent
        opacity={0.55}
        sizeAttenuation
        depthWrite={false}
      />
    </points>
  );
}

/* ---- The mark you start in front of ----------------------------------- */

function Title() {
  const map = useMemo(
    () => titleTexture("Your channel,\non autopilot.", "A topic in. A finished, sourced video out."),
    []
  );
  const mesh = useRef();

  useFrame(({ clock }) => {
    if (mesh.current) mesh.current.position.y = Math.sin(clock.elapsedTime * 0.4) * 0.12;
  });

  return (
    <mesh ref={mesh} position={[0, 0.4, -4]}>
      <planeGeometry args={[15, 7.5]} />
      <meshBasicMaterial map={map} transparent depthWrite={false} />
    </mesh>
  );
}

/* ---- A station ---------------------------------------------------------- */

function Station({ station, index }) {
  const group = useRef();
  const map = useMemo(
    () => stationTexture({ ...station, index: index + 1 }),
    [station, index]
  );

  // Alternating sides, so travelling through them feels like passing things
  // rather than watching a stack.
  const side = index % 2 === 0 ? -1 : 1;
  const z = -SPACING * (index + 1);

  useFrame(({ camera, clock }) => {
    if (!group.current) return;
    const distance = group.current.position.z - camera.position.z;

    // Turn to face you as you come level with it, and settle back once past.
    const facing = THREE.MathUtils.clamp(1 - Math.abs(distance) / 22, 0, 1);
    group.current.rotation.y = side * (0.42 - facing * 0.34);
    group.current.position.y = 0.2 + Math.sin(clock.elapsedTime * 0.5 + index) * 0.08;
  });

  return (
    <group ref={group} position={[side * 6.4, 0.2, z]}>
      <mesh>
        <planeGeometry args={[9, 5.6]} />
        <meshBasicMaterial map={map} transparent toneMapped={false} />
      </mesh>
      {/* A light of its own, so the dust around it brightens as you arrive. */}
      <pointLight color={ACCENT} distance={16} intensity={9} position={[0, 0, 1.6]} />
    </group>
  );
}

/* ---- Where it ends up --------------------------------------------------- */

function PlatformBadge({ name, angle, radius, z }) {
  const mesh = useRef();
  const map = useMemo(() => platformTexture(name), [name]);

  useFrame(({ clock }) => {
    if (!mesh.current) return;
    const t = clock.elapsedTime * 0.24 + angle;
    mesh.current.position.x = Math.cos(t) * radius;
    mesh.current.position.y = Math.sin(t) * radius * 0.42 + 0.4;
    mesh.current.rotation.z = Math.sin(t) * 0.12;
  });

  return (
    <mesh ref={mesh} position={[0, 0, z]}>
      <planeGeometry args={[2.4, 2.4]} />
      <meshBasicMaterial map={map} transparent depthWrite={false} toneMapped={false} />
    </mesh>
  );
}

function Publish({ z }) {
  const map = useMemo(
    () =>
      stationTexture({
        index: STATIONS.length + 1,
        note: "and it goes out",
        title: "Published",
        body: "Uploaded with the sources as links a viewer can click, and cut for every platform you post to.",
      }),
    []
  );

  return (
    <group position={[0, 0, z]}>
      <mesh position={[0, 0.2, -1.6]}>
        <planeGeometry args={[9.6, 6]} />
        <meshBasicMaterial map={map} transparent toneMapped={false} />
      </mesh>
      {PLATFORM_NAMES.map((name, i) => (
        <PlatformBadge
          key={name}
          name={name}
          angle={(i / PLATFORM_NAMES.length) * Math.PI * 2}
          radius={5.4}
          z={2}
        />
      ))}
      <pointLight color={DATA} distance={22} intensity={12} position={[0, 0, 2]} />
    </group>
  );
}

/* ---- The scene ---------------------------------------------------------- */

export default function Scene({ progress }) {
  const { camera } = useThree();
  const travelled = useRef(0);

  useFrame((_, dt) => {
    // Eased towards the scroll position rather than pinned to it: a camera
    // that lands exactly where the wheel says feels like a scrollbar, and one
    // that catches up feels like a body moving.
    const target = progress.current * TRAVEL;
    travelled.current += (target - travelled.current) * Math.min(1, dt * 3.2);

    camera.position.z = START_Z - travelled.current;
    // A little drift, so it never reads as being on rails.
    camera.position.x = Math.sin(travelled.current * 0.03) * 0.9;
    camera.position.y = 0.6 + Math.cos(travelled.current * 0.025) * 0.35;
    camera.lookAt(camera.position.x * 0.4, 0.2, camera.position.z - 12);
  });

  return (
    <>
      <ambientLight intensity={0.35} />
      <Dust />
      <Title />
      {STATIONS.map((station, i) => (
        <Station key={station.title} station={station} index={i} />
      ))}
      <Publish z={-SPACING * (STATIONS.length + 1)} />
    </>
  );
}
