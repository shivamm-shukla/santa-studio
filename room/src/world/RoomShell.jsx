import { useMemo } from "react";
import {
  BOOTH_ROOM,
  BOOTH_ROOM_POS,
  CORRIDOR,
  DOOR_ANGLE,
  DOOR_ARC,
  DOOR_H,
  DOOR_WIDTH,
  ROOM_R,
  WALL_H,
  deskAngle,
  doorDir,
} from "./layout.js";
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

      {/* wall, with a doorway taken out of it.

          Cut as an arc the cylinder simply does not cover, rather than as a
          hole punched in a solid one: a wall you can walk through has to have
          a gap in the geometry, or the camera passes through something that
          is still drawn. The lintel closes the top so it reads as a doorway
          and not as a missing panel. */}
      <mesh
        position={[0, WALL_H / 2, 0]}
        rotation={[0, DOOR_ANGLE + DOOR_ARC / 2, 0]}
        receiveShadow
      >
        <cylinderGeometry
          args={[ROOM_R, ROOM_R, WALL_H, 72, 1, true, 0, Math.PI * 2 - DOOR_ARC]}
        />
        <meshStandardMaterial color="#3d3d49" roughness={0.94} side={1} />
      </mesh>
      <mesh position={[0, 0.07, 0]} rotation={[0, DOOR_ANGLE + DOOR_ARC / 2, 0]}>
        <cylinderGeometry
          args={[ROOM_R - 0.01, ROOM_R - 0.01, 0.14, 72, 1, true, 0, Math.PI * 2 - DOOR_ARC]}
        />
        <meshStandardMaterial color="#22222b" roughness={0.6} side={1} />
      </mesh>

      {/* the lintel over the door */}
      <mesh
        position={[
          doorDir[0] * ROOM_R,
          DOOR_H + (WALL_H - DOOR_H) / 2,
          doorDir[1] * ROOM_R,
        ]}
        rotation={[0, DOOR_ANGLE, 0]}
      >
        <boxGeometry args={[DOOR_WIDTH + 0.5, WALL_H - DOOR_H, 0.3]} />
        <meshStandardMaterial color="#3d3d49" roughness={0.94} />
      </mesh>

      {/* The corridor between the two rooms, so the door leads somewhere
          rather than opening onto the outside of a box. */}
      <group
        position={[
          doorDir[0] * (ROOM_R + CORRIDOR / 2),
          0,
          doorDir[1] * (ROOM_R + CORRIDOR / 2),
        ]}
        rotation={[0, DOOR_ANGLE, 0]}
      >
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[DOOR_WIDTH, CORRIDOR + 0.2]} />
          <meshStandardMaterial color="#2f2f3a" roughness={0.9} />
        </mesh>
        <mesh position={[0, DOOR_H, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <planeGeometry args={[DOOR_WIDTH, CORRIDOR + 0.2]} />
          <meshStandardMaterial color="#33333f" roughness={0.98} />
        </mesh>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[(side * DOOR_WIDTH) / 2, DOOR_H / 2, 0]} rotation={[0, Math.PI / 2, 0]}>
            <planeGeometry args={[CORRIDOR + 0.2, DOOR_H]} />
            <meshStandardMaterial color="#353542" roughness={0.95} side={2} />
          </mesh>
        ))}
      </group>

      {/* The recording room itself: four walls, a low ceiling and a door back.
          A vocal booth wants to be small and dead, which is why it is not the
          same shape as the studio. */}
      <group position={BOOTH_ROOM_POS} rotation={[0, DOOR_ANGLE, 0]}>
        <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[BOOTH_ROOM.width, BOOTH_ROOM.depth]} />
          <meshStandardMaterial color="#2b2b34" roughness={0.95} />
        </mesh>
        <mesh position={[0, BOOTH_ROOM.height, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <planeGeometry args={[BOOTH_ROOM.width, BOOTH_ROOM.depth]} />
          <meshStandardMaterial color="#26262f" roughness={0.99} />
        </mesh>
        {/* far wall */}
        <mesh position={[0, BOOTH_ROOM.height / 2, -BOOTH_ROOM.depth / 2]}>
          <planeGeometry args={[BOOTH_ROOM.width, BOOTH_ROOM.height]} />
          <meshStandardMaterial color="#2d2d37" roughness={0.97} side={2} />
        </mesh>
        {/* sides */}
        {[-1, 1].map((side) => (
          <mesh
            key={side}
            position={[(side * BOOTH_ROOM.width) / 2, BOOTH_ROOM.height / 2, 0]}
            rotation={[0, -side * (Math.PI / 2), 0]}
          >
            <planeGeometry args={[BOOTH_ROOM.depth, BOOTH_ROOM.height]} />
            <meshStandardMaterial color="#2d2d37" roughness={0.97} side={2} />
          </mesh>
        ))}
        {/* the wall you came through, either side of the doorway */}
        {[-1, 1].map((side) => {
          const panel = (BOOTH_ROOM.width - DOOR_WIDTH) / 2;
          return (
            <mesh
              key={`back${side}`}
              position={[side * (DOOR_WIDTH / 2 + panel / 2), BOOTH_ROOM.height / 2, BOOTH_ROOM.depth / 2]}
            >
              <planeGeometry args={[panel, BOOTH_ROOM.height]} />
              <meshStandardMaterial color="#2d2d37" roughness={0.97} side={2} />
            </mesh>
          );
        })}
        <mesh position={[0, DOOR_H + (BOOTH_ROOM.height - DOOR_H) / 2, BOOTH_ROOM.depth / 2]}>
          <planeGeometry args={[DOOR_WIDTH, BOOTH_ROOM.height - DOOR_H]} />
          <meshStandardMaterial color="#2d2d37" roughness={0.97} side={2} />
        </mesh>
      </group>

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
