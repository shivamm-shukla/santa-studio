import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { ACCENT } from "../theme.js";
import { BOOTH_ROOM, BOOTH_LOCAL } from "../world/layout.js";

/* The microphone and the treatment around it, inside the recording room.

   Every position here is derived from the room's own dimensions rather than
   written by eye. The first version was not: the foam sat 1.05m off the back
   wall and 2.10m off the sides, which does not read as acoustic treatment -
   it reads as a cloud of pyramids hanging in a room. Nothing in here carries
   a hand-picked coordinate any more, so the furniture and the walls cannot
   drift apart again.

   What moves is driven by what the microphone is hearing, handed down as a
   ref and read per frame. A mic that sits still while you talk into it would
   be worse than a form. */

const WEDGE = 0.32;   // real acoustic foam is 30cm square

/** Foam tiled across a wall of `width` x `height`, starting at its corner. */
function Foam({ width, height, up = 2.6 }) {
  const tiles = useMemo(() => {
    const cols = Math.floor(width / WEDGE);
    const rows = Math.floor(up / WEDGE);
    const out = [];
    for (let x = 0; x < cols; x++) {
      for (let y = 0; y < rows; y++) {
        out.push({
          key: `${x}-${y}`,
          position: [
            (x - (cols - 1) / 2) * WEDGE,
            0.14 + y * WEDGE,
            0,
          ],
          depth: 0.07 + ((x * 5 + y * 3) % 3) * 0.015,
          turn: ((x + y) % 2) * (Math.PI / 4),
        });
      }
    }
    return out;
  }, [width, up]);

  return (
    <>
      {/* the backing board the foam is glued to */}
      <mesh position={[0, 0.14 + up / 2 - WEDGE / 2, -0.03]} receiveShadow>
        <planeGeometry args={[width, up]} />
        <meshStandardMaterial color="#2a2a33" roughness={0.98} />
      </mesh>
      {tiles.map((tile) => (
        <mesh
          key={tile.key}
          position={tile.position}
          rotation={[Math.PI / 2, tile.turn, 0]}
          castShadow
        >
          {/* A four-sided cone is a foam wedge; the faceting is what catches
              the light and makes a wall read as treatment, not as wallpaper. */}
          <coneGeometry args={[WEDGE * 0.7, tile.depth, 4]} />
          <meshStandardMaterial color="#40404c" roughness={0.99} />
        </mesh>
      ))}
    </>
  );
}

export default function VocalBooth({ position, rotation, level, live, focused, lightMode, onSelect }) {
  const capsule = useRef();
  const glow = useRef();
  const rings = useRef([]);
  const lamp = useRef();
  const key = useRef();
  const fill = useRef();

  useFrame(({ clock }, dt) => {
    const loud = live && level ? Math.min(1, level.current * 5.5) : 0;
    const k = Math.min(1, dt * 3.2);
    const on = lightMode ? 1 : 0;

    if (key.current) key.current.intensity += ((on ? 22 : 3.5) - key.current.intensity) * k;
    if (fill.current) fill.current.intensity += ((on ? 7 : 1.8) - fill.current.intensity) * k;

    if (capsule.current) {
      capsule.current.position.y = 1.34 + Math.sin(clock.elapsedTime * 0.7) * 0.005;
    }
    if (glow.current) {
      const target = live ? 1.2 + loud * 7 : focused ? 0.6 : 0.2;
      glow.current.intensity += (target - glow.current.intensity) * Math.min(1, dt * 9);
    }
    if (lamp.current) {
      lamp.current.material.color.set(live ? "#ff3b20" : focused ? ACCENT : "#33333d");
    }

    rings.current.forEach((ring, i) => {
      if (!ring) return;
      const phase = (clock.elapsedTime * 0.55 + i / rings.current.length) % 1;
      ring.scale.setScalar(0.35 + phase * (0.9 + loud * 2.2));
      ring.material.opacity = live ? (1 - phase) * (0.12 + loud * 0.5) : 0;
    });
  });

  const { farZ, sideX } = BOOTH_LOCAL;

  return (
    <group position={position} rotation={[0, rotation, 0]} onClick={onSelect}>
      {/* Its own rig - through a wall from the studio's - on the same switch. */}
      <pointLight ref={key} position={[0.8, 2.5, 1.3]} intensity={3.5} distance={11} color="#ffe3cc" castShadow />
      <pointLight ref={fill} position={[-1.9, 1.7, -0.8]} intensity={1.8} distance={9} color="#4a6ba8" />
      <mesh position={[0.8, BOOTH_ROOM.height - 0.06, 1.3]}>
        <cylinderGeometry args={[0.24, 0.32, 0.09, 20]} />
        <meshStandardMaterial
          color="#1a1a22"
          emissive="#ffe3cc"
          emissiveIntensity={lightMode ? 1.6 : 0.2}
          roughness={0.6}
        />
      </mesh>

      {/* Foam, on the walls it belongs to. */}
      <group position={[0, 0, farZ + 0.04]}>
        <Foam width={BOOTH_ROOM.width - 0.2} />
      </group>
      <group position={[-sideX + 0.04, 0, 1.2]} rotation={[0, Math.PI / 2, 0]}>
        <Foam width={4.4} />
      </group>
      <group position={[sideX - 0.04, 0, 1.2]} rotation={[0, -Math.PI / 2, 0]}>
        <Foam width={4.4} />
      </group>

      {/* stand */}
      <mesh position={[0, 0.02, 0]} castShadow>
        <cylinderGeometry args={[0.22, 0.26, 0.04, 24]} />
        <meshStandardMaterial color="#101016" roughness={0.6} metalness={0.35} />
      </mesh>
      <mesh position={[0, 0.65, 0]} castShadow>
        <cylinderGeometry args={[0.022, 0.026, 1.26, 14]} />
        <meshStandardMaterial color="#15151c" roughness={0.45} metalness={0.6} />
      </mesh>

      {/* shock mount and mic */}
      <mesh position={[0, 1.34, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.14, 0.008, 10, 32]} />
        <meshStandardMaterial color="#1d1d26" roughness={0.5} metalness={0.5} />
      </mesh>
      <mesh ref={capsule} position={[0, 1.34, 0]} castShadow>
        <capsuleGeometry args={[0.055, 0.16, 8, 20]} />
        <meshStandardMaterial color="#24242e" roughness={0.32} metalness={0.75} />
      </mesh>
      <mesh ref={lamp} position={[0, 1.22, 0.05]}>
        <sphereGeometry args={[0.012, 10, 8]} />
        <meshBasicMaterial color="#33333d" />
      </mesh>

      {/* the pop filter, clear of the capsule rather than through it */}
      <group position={[0, 1.34, 0.2]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.1, 0.006, 8, 26]} />
          <meshStandardMaterial color="#1a1a22" roughness={0.5} metalness={0.4} />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.098, 26]} />
          <meshStandardMaterial color="#0e0e14" roughness={0.9} transparent opacity={0.34} side={2} />
        </mesh>
      </group>

      <pointLight ref={glow} color={ACCENT} distance={4} intensity={0.2} position={[0, 1.34, 0.35]} />

      {[0, 1, 2, 3].map((i) => (
        <mesh
          key={i}
          ref={(el) => (rings.current[i] = el)}
          position={[0, 1.34, 0]}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <torusGeometry args={[0.18, 0.004, 8, 40]} />
          <meshBasicMaterial color={ACCENT} transparent opacity={0} depthWrite={false} />
        </mesh>
      ))}

      {/* a stool, in the same grey as everything else that is furniture */}
      <group position={[0, 0, 1.05]}>
        <mesh position={[0, 0.63, 0]} castShadow>
          <cylinderGeometry args={[0.18, 0.18, 0.05, 20]} />
          <meshStandardMaterial color="#26262f" roughness={0.85} />
        </mesh>
        <mesh position={[0, 0.32, 0]}>
          <cylinderGeometry args={[0.028, 0.032, 0.62, 12]} />
          <meshStandardMaterial color="#1b1b23" roughness={0.5} metalness={0.6} />
        </mesh>
        <mesh position={[0, 0.02, 0]}>
          <cylinderGeometry args={[0.19, 0.21, 0.03, 20]} />
          <meshStandardMaterial color="#1b1b23" roughness={0.5} metalness={0.6} />
        </mesh>
      </group>
    </group>
  );
}
