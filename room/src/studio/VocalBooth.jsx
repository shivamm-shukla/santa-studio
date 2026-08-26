import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { ACCENT } from "../theme.js";

/* The vocal booth, standing on the studio floor rather than on a page of its
   own. Walking to it is a camera move like any other, which is the point: a
   separate page for recording made the studio a set of places you leave to do
   things, and this is meant to be one place you do them in.

   Everything that moves here is driven by what the microphone is actually
   hearing, handed down as a ref and read per frame. A mic that sits still
   while you talk into it would be worse than a form, not better. */

function Panels({ count = 4, rows = 4, size = 0.46 }) {
  const tiles = [];
  for (let x = 0; x < count; x++) {
    for (let y = 0; y < rows; y++) {
      tiles.push({
        key: `${x}-${y}`,
        position: [(x - (count - 1) / 2) * size, y * size + 0.24, 0],
        depth: 0.03 + ((x * 7 + y * 5) % 4) * 0.012,
      });
    }
  }
  return (
    <>
      {tiles.map((tile) => (
        <mesh key={tile.key} position={tile.position} castShadow receiveShadow>
          <boxGeometry args={[size * 0.92, size * 0.92, tile.depth]} />
          <meshStandardMaterial color="#191920" roughness={0.97} />
        </mesh>
      ))}
    </>
  );
}

export default function VocalBooth({ position, rotation, level, live, focused, onSelect }) {
  const capsule = useRef();
  const glow = useRef();
  const rings = useRef([]);
  const lamp = useRef();

  useFrame(({ clock }, dt) => {
    const loud = live && level ? Math.min(1, level.current * 5.5) : 0;

    if (capsule.current) {
      capsule.current.position.y = 1.28 + Math.sin(clock.elapsedTime * 0.7) * 0.006;
    }
    if (glow.current) {
      const target = live ? 1.2 + loud * 7 : focused ? 0.5 : 0.16;
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

  return (
    <group position={position} rotation={[0, rotation, 0]} onClick={onSelect}>
      {/* three walls, so it is a booth and not a backdrop */}
      <group position={[0, 0, -0.95]}>
        <Panels count={5} />
      </group>
      <group position={[-1.12, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <Panels count={4} />
      </group>
      <group position={[1.12, 0, 0]} rotation={[0, -Math.PI / 2, 0]}>
        <Panels count={4} />
      </group>

      {/* stand */}
      <mesh position={[0, 0.02, 0]} castShadow>
        <cylinderGeometry args={[0.22, 0.26, 0.04, 24]} />
        <meshStandardMaterial color="#101016" roughness={0.6} metalness={0.35} />
      </mesh>
      <mesh position={[0, 0.62, 0]} castShadow>
        <cylinderGeometry args={[0.022, 0.026, 1.2, 14]} />
        <meshStandardMaterial color="#15151c" roughness={0.45} metalness={0.6} />
      </mesh>

      {/* shock mount and mic */}
      <mesh position={[0, 1.28, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.15, 0.009, 10, 32]} />
        <meshStandardMaterial color="#1d1d26" roughness={0.5} metalness={0.5} />
      </mesh>
      <mesh ref={capsule} position={[0, 1.28, 0]} castShadow>
        <capsuleGeometry args={[0.085, 0.2, 8, 20]} />
        <meshStandardMaterial color="#24242e" roughness={0.32} metalness={0.75} />
      </mesh>
      {/* the live lamp, which is how you know from across the room */}
      <mesh ref={lamp} position={[0, 1.13, 0.075]}>
        <sphereGeometry args={[0.016, 10, 8]} />
        <meshBasicMaterial color="#33333d" />
      </mesh>

      <pointLight ref={glow} color={ACCENT} distance={4.5} intensity={0.16} position={[0, 1.3, 0.3]} />

      {[0, 1, 2, 3].map((i) => (
        <mesh
          key={i}
          ref={(el) => (rings.current[i] = el)}
          position={[0, 1.28, 0]}
          rotation={[Math.PI / 2, 0, 0]}
        >
          <torusGeometry args={[0.22, 0.005, 8, 40]} />
          <meshBasicMaterial color={ACCENT} transparent opacity={0} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}
