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

function Panels({ count = 4, rows = 4, size = 0.42 }) {
  const tiles = [];
  for (let x = 0; x < count; x++) {
    for (let y = 0; y < rows; y++) {
      tiles.push({
        key: `${x}-${y}`,
        position: [(x - (count - 1) / 2) * size, y * size + 0.24, 0.05],
        depth: 0.09 + ((x * 7 + y * 5) % 4) * 0.02,
        // Alternating quarter turns, the way foam is actually laid up.
        turn: ((x + y) % 2) * (Math.PI / 4),
      });
    }
  }
  return (
    <>
      {tiles.map((tile) => (
        <mesh
          key={tile.key}
          position={tile.position}
          rotation={[Math.PI / 2, tile.turn, 0]}
          castShadow
          receiveShadow
        >
          {/* A four-sided cone is a foam wedge. Flat tiles read as a painted
              grid: it is the faceting that catches the light and makes the
              wall look like acoustic treatment rather than wallpaper. */}
          <coneGeometry args={[size * 0.62, tile.depth, 4]} />
          <meshStandardMaterial color="#3b3b46" roughness={0.99} />
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
  const ceiling = useRef();

  useFrame(({ clock }, dt) => {
    const loud = live && level ? Math.min(1, level.current * 5.5) : 0;
    const k = Math.min(1, dt * 3.2);

    // The switch reaches in here too. It was wired to fixed lights, so this
    // was the one room in the building where turning the lights on did
    // nothing - which is worse than having no switch, because you press it
    // and the place ignores you.
    const on = lightMode ? 1 : 0;
    if (key.current) key.current.intensity += ((on ? 16 : 2.4) - key.current.intensity) * k;
    if (fill.current) fill.current.intensity += ((on ? 5 : 1.6) - fill.current.intensity) * k;
    if (ceiling.current) ceiling.current.intensity += ((on ? 9 : 0.6) - ceiling.current.intensity) * k;

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
      {/* Its own rig, because it is through a wall from the studio's, but on
          the same switch - a booth with lights you cannot turn on is a booth
          with a broken switch. */}
      <pointLight ref={key} position={[0.9, 2.4, 1.1]} intensity={2.4} distance={10} color="#ffd9c2" castShadow />
      <pointLight ref={fill} position={[-1.7, 1.5, -1.2]} intensity={1.6} distance={8} color="#3a5a9a" />
      <pointLight ref={ceiling} position={[0, 3.1, -0.4]} intensity={0.6} distance={9} color="#e8e4dd" />

      {/* the ceiling fitting the key comes out of, so the light has a source */}
      <mesh position={[0.9, 3.2, 1.1]}>
        <cylinderGeometry args={[0.22, 0.3, 0.1, 20]} />
        <meshStandardMaterial
          color="#1a1a22"
          emissive="#ffd9c2"
          emissiveIntensity={lightMode ? 1.4 : 0.15}
          roughness={0.6}
        />
      </mesh>

      {/* foam on the walls behind and beside the microphone */}
      <group position={[0, 0, -1.25]}>
        <Panels count={6} />
      </group>
      <group position={[-1.6, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
        <Panels count={5} />
      </group>
      <group position={[1.6, 0, 0]} rotation={[0, -Math.PI / 2, 0]}>
        <Panels count={5} />
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

      {/* A pop filter, because there is one on every microphone anyone has
          ever recorded a voice into. */}
      <group position={[0, 1.28, 0.24]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.13, 0.008, 8, 28]} />
          <meshStandardMaterial color="#1a1a22" roughness={0.5} metalness={0.4} />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <circleGeometry args={[0.128, 28]} />
          <meshStandardMaterial color="#0e0e14" roughness={0.9} transparent opacity={0.42} side={2} />
        </mesh>
        <mesh position={[0, -0.08, -0.1]} rotation={[0.5, 0, 0]}>
          <cylinderGeometry args={[0.007, 0.007, 0.26, 8]} />
          <meshStandardMaterial color="#15151c" roughness={0.5} metalness={0.5} />
        </mesh>
      </group>

      {/* Headphones over the stand, and the cable down it. */}
      <group position={[0.16, 0.92, 0]} rotation={[0, 0, -0.35]}>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.1, 0.016, 8, 24, Math.PI]} />
          <meshStandardMaterial color="#16161d" roughness={0.6} />
        </mesh>
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * 0.1, -0.02, 0]}>
            <cylinderGeometry args={[0.045, 0.045, 0.035, 16]} />
            <meshStandardMaterial color="#1c1c25" roughness={0.7} />
          </mesh>
        ))}
      </group>

      {/* A stool, because recording standing up for twenty seconds is fine and
          for twenty minutes is not. */}
      <group position={[0, 0, 0.95]}>
        <mesh position={[0, 0.62, 0]} castShadow>
          <cylinderGeometry args={[0.19, 0.19, 0.05, 20]} />
          <meshStandardMaterial color="#4a3a44" roughness={0.85} />
        </mesh>
        <mesh position={[0, 0.31, 0]}>
          <cylinderGeometry args={[0.03, 0.035, 0.6, 12]} />
          <meshStandardMaterial color="#20202a" roughness={0.5} metalness={0.6} />
        </mesh>
        <mesh position={[0, 0.02, 0]}>
          <cylinderGeometry args={[0.2, 0.22, 0.03, 20]} />
          <meshStandardMaterial color="#20202a" roughness={0.5} metalness={0.6} />
        </mesh>
      </group>

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
