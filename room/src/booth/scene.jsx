import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

/* The booth you are standing in.

   The camera sits where your head would be, a little back from the mic and
   slightly above it, so the stand reads as being in front of you rather than
   on a stage you are watching. Nothing here is a diagram of a booth - the
   panels are on the walls because a vocal booth has panels on the walls, and
   the key light is off to one side because that is where a light goes.

   Everything that moves is driven by what the microphone is actually hearing,
   passed down as a ref and read per frame. That is the whole point of doing
   this in 3D: the room answers your voice. */

const ACCENT = "#ff6b35";

function Panels({ z, count = 5, width = 1.05 }) {
  // Acoustic foam, as a staggered grid. Depth varies per tile so the light
  // catches them unevenly, which is what stops it reading as wallpaper.
  const tiles = useMemo(() => {
    const out = [];
    for (let x = 0; x < count; x++) {
      for (let y = 0; y < 4; y++) {
        out.push({
          key: `${x}-${y}`,
          position: [(x - (count - 1) / 2) * width, y * width - 1.2, 0],
          depth: 0.05 + ((x * 7 + y * 3) % 4) * 0.018,
        });
      }
    }
    return out;
  }, [count, width]);

  return (
    <group position={[0, 0, z]}>
      {tiles.map((tile) => (
        <mesh key={tile.key} position={tile.position} castShadow receiveShadow>
          <boxGeometry args={[width * 0.94, width * 0.94, tile.depth]} />
          <meshStandardMaterial color="#1b1b22" roughness={0.96} metalness={0} />
        </mesh>
      ))}
    </group>
  );
}

function Microphone({ level, live }) {
  const body = useRef();
  const glow = useRef();
  const rings = useRef([]);

  useFrame(({ clock }, dt) => {
    const loudness = live ? Math.min(1, level.current * 5.5) : 0;

    if (body.current) {
      // A capsule mic does not bounce. It sits still and the light on it
      // moves, which is what a real one looks like when you speak into it.
      body.current.position.y = 0.02 * Math.sin(clock.elapsedTime * 0.7);
    }
    if (glow.current) {
      const target = live ? 0.25 + loudness * 2.6 : 0.12;
      glow.current.intensity += (target - glow.current.intensity) * Math.min(1, dt * 9);
    }

    // Rings leaving the mic, sized by how loud you are. They are the reading
    // you would otherwise have to put in a meter somewhere off to the side.
    rings.current.forEach((ring, i) => {
      if (!ring) return;
      const phase = (clock.elapsedTime * 0.55 + i / rings.current.length) % 1;
      const scale = 0.4 + phase * (1.1 + loudness * 2.4);
      ring.scale.setScalar(scale);
      ring.material.opacity = live ? (1 - phase) * (0.16 + loudness * 0.5) : 0;
    });
  });

  return (
    <group position={[0, 0.1, -1.5]}>
      {/* stand */}
      <mesh position={[0, -1.15, 0]} castShadow>
        <cylinderGeometry args={[0.3, 0.34, 0.05, 28]} />
        <meshStandardMaterial color="#101016" roughness={0.6} metalness={0.35} />
      </mesh>
      <mesh position={[0, -0.62, 0]} castShadow>
        <cylinderGeometry args={[0.028, 0.032, 1.05, 16]} />
        <meshStandardMaterial color="#15151c" roughness={0.45} metalness={0.6} />
      </mesh>

      {/* shock mount */}
      <mesh rotation={[Math.PI / 2, 0, 0]}>
        <torusGeometry args={[0.2, 0.012, 10, 40]} />
        <meshStandardMaterial color="#1d1d26" roughness={0.5} metalness={0.5} />
      </mesh>

      {/* the mic itself */}
      <group ref={body}>
        <mesh castShadow>
          <capsuleGeometry args={[0.115, 0.26, 8, 24]} />
          <meshStandardMaterial color="#24242e" roughness={0.32} metalness={0.75} />
        </mesh>
        <mesh position={[0, 0.1, 0.001]}>
          <sphereGeometry args={[0.113, 24, 18, 0, Math.PI * 2, 0, Math.PI / 2]} />
          <meshStandardMaterial color="#3a3a46" roughness={0.5} metalness={0.9} wireframe />
        </mesh>
        {/* the live lamp */}
        <mesh position={[0, -0.16, 0.1]}>
          <sphereGeometry args={[0.018, 10, 8]} />
          <meshBasicMaterial color={live ? ACCENT : "#3a3a46"} />
        </mesh>
      </group>

      <pointLight ref={glow} color={ACCENT} distance={5} intensity={0.12} position={[0, 0, 0.4]} />

      {[0, 1, 2, 3].map((i) => (
        <mesh key={i} ref={(el) => (rings.current[i] = el)} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.3, 0.006, 8, 48]} />
          <meshBasicMaterial color={ACCENT} transparent opacity={0} depthWrite={false} />
        </mesh>
      ))}
    </group>
  );
}

export default function BoothScene({ level, live }) {
  return (
    <>
      {/* A key off to one side and a cold fill behind, the way a booth is lit. */}
      <ambientLight intensity={0.22} />
      <spotLight
        position={[2.6, 3.2, 1.4]}
        angle={0.7}
        penumbra={0.85}
        intensity={38}
        color="#ffd9c2"
        castShadow
      />
      <pointLight position={[-2.8, 1.4, -2.6]} intensity={9} color="#2f4f8a" />

      <Panels z={-2.6} count={7} />
      <group rotation={[0, Math.PI / 2, 0]} position={[-3.2, 0, 0]}>
        <Panels z={0} count={5} />
      </group>
      <group rotation={[0, -Math.PI / 2, 0]} position={[3.2, 0, 0]}>
        <Panels z={0} count={5} />
      </group>

      {/* floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.3, 0]} receiveShadow>
        <planeGeometry args={[16, 16]} />
        <meshStandardMaterial color="#0c0c11" roughness={0.94} />
      </mesh>

      <Microphone level={level} live={live} />
    </>
  );
}
