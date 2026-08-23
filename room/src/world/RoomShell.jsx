import { useMemo } from "react";
import { ROOM_R, WALL_H, deskAngle } from "./layout.js";
import { AGENTS } from "../sim/agents.js";

/* The building. Deliberately plain surfaces — the room is meant to read as a
   real space that lights change, not as a set that glows on its own. */

function Plant({ position }) {
  const leaves = useMemo(
    () => Array.from({ length: 7 }, (_, i) => ({
      a: (i / 7) * Math.PI * 2 + Math.random(),
      tilt: 0.5 + Math.random() * 0.4,
      h: 0.5 + Math.random() * 0.35,
    })),
    []
  );
  return (
    <group position={position}>
      <mesh position={[0, 0.18, 0]} castShadow>
        <cylinderGeometry args={[0.22, 0.17, 0.36, 16]} />
        <meshStandardMaterial color="#8a6a4f" roughness={0.85} />
      </mesh>
      <mesh position={[0, 0.37, 0]}>
        <cylinderGeometry args={[0.2, 0.2, 0.03, 16]} />
        <meshStandardMaterial color="#2b2118" roughness={1} />
      </mesh>
      {leaves.map((l, i) => (
        <mesh
          key={i}
          position={[Math.sin(l.a) * 0.1, 0.4 + l.h / 2, Math.cos(l.a) * 0.1]}
          rotation={[l.tilt * Math.cos(l.a), -l.a, l.tilt * Math.sin(l.a)]}
          castShadow
        >
          <capsuleGeometry args={[0.05, l.h, 4, 8]} />
          <meshStandardMaterial color="#2f6b3a" roughness={0.75} />
        </mesh>
      ))}
    </group>
  );
}

export default function RoomShell() {
  return (
    <group>
      {/* floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[ROOM_R, 72]} />
        <meshStandardMaterial color="#3a3a46" roughness={0.7} metalness={0.12} />
      </mesh>
      {/* rug under the table, to make the centre feel like somewhere you sit */}
      <mesh position={[0, 0.008, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[3.6, 64]} />
        <meshStandardMaterial color="#4a3a44" roughness={0.95} />
      </mesh>
      <mesh position={[0, 0.012, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[3.34, 3.42, 64]} />
        <meshStandardMaterial color="#63505d" roughness={0.9} />
      </mesh>

      {/* wall */}
      <mesh position={[0, WALL_H / 2, 0]} receiveShadow>
        <cylinderGeometry args={[ROOM_R, ROOM_R, WALL_H, 72, 1, true]} />
        <meshStandardMaterial color="#3d3d49" roughness={0.94} side={1} />
      </mesh>
      <mesh position={[0, 0.07, 0]}>
        <cylinderGeometry args={[ROOM_R - 0.01, ROOM_R - 0.01, 0.14, 72, 1, true]} />
        <meshStandardMaterial color="#22222b" roughness={0.6} side={1} />
      </mesh>

      {/* ceiling */}
      <mesh position={[0, WALL_H, 0]} rotation={[Math.PI / 2, 0, 0]}>
        <circleGeometry args={[ROOM_R, 72]} />
        <meshStandardMaterial color="#4a4a57" roughness={0.98} />
      </mesh>

      {/* a plant in every third gap between desks */}
      {AGENTS.map((_, i) => {
        if (i % 3) return null;
        const a = deskAngle(i) + Math.PI / AGENTS.length;
        return <Plant key={i} position={[Math.sin(a) * 10.6, 0, Math.cos(a) * 10.6]} />;
      })}
    </group>
  );
}
