import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

/* The turn light on the table.

   Whose turn it is used to be a sentence in a bar along the bottom of the
   screen, which is the one thing a room like this should never need: you
   were reading the game instead of looking at it. There are two of these
   instead, one in front of each player. Green means the turn is yours;
   pressing it takes it. The other side's lights up when the turn crosses the
   table, the way a chess clock says the same thing without a word on it. */

const LIVE = new THREE.Color("#3ddc6b");
const DARK = new THREE.Color("#17311f");

export default function Buzzer({ position, live, pressing, enabled, onPress }) {
  const cap = useRef();
  const glow = useRef();
  const material = useRef();
  const ring = useRef();
  const held = useRef(0);

  useFrame((_, dt) => {
    // A live button breathes; a dead one sits at its floor. Pressing drives
    // the cap down hard and lets it come back up on its own.
    held.current = Math.max(0, held.current - dt * 3.4);
    const pulse = live ? 0.72 + Math.sin(performance.now() * 0.005) * 0.28 : 0.06;
    const down = pressing || held.current > 0 ? 1 : 0;

    if (cap.current) {
      const want = 0.028 - down * 0.014;
      cap.current.position.y += (want - cap.current.position.y) * Math.min(1, dt * 16);
    }
    if (material.current) {
      material.current.color.lerpColors(DARK, LIVE, live ? 1 : 0.12);
      material.current.emissive.lerpColors(DARK, LIVE, live ? 1 : 0.08);
      material.current.emissiveIntensity += (pulse * 1.6 - material.current.emissiveIntensity) * Math.min(1, dt * 8);
    }
    if (glow.current) {
      glow.current.intensity += ((live ? 0.5 + pulse * 0.5 : 0) - glow.current.intensity) * Math.min(1, dt * 8);
    }
    if (ring.current) {
      ring.current.emissiveIntensity += ((live ? 0.55 : 0.04) - ring.current.emissiveIntensity) * Math.min(1, dt * 8);
    }
  });

  return (
    <group
      position={position}
      onClick={(e) => {
        if (!enabled) return;
        e.stopPropagation();
        held.current = 1;
        onPress();
      }}
      onPointerOver={() => enabled && (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      {/* the housing it is screwed into */}
      <mesh position={[0, 0.011, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[0.105, 0.115, 0.022, 24]} />
        <meshStandardMaterial color="#23232b" roughness={0.45} metalness={0.6} />
      </mesh>

      {/* a thin lit collar, so the state reads from across the room */}
      <mesh position={[0, 0.023, 0]}>
        <torusGeometry args={[0.092, 0.008, 8, 28]} />
        <meshStandardMaterial
          ref={ring}
          color="#1d2b21"
          emissive="#3ddc6b"
          emissiveIntensity={0.04}
          roughness={0.4}
        />
      </mesh>

      {/* the cap you actually hit */}
      <mesh ref={cap} position={[0, 0.028, 0]} castShadow>
        <cylinderGeometry args={[0.078, 0.082, 0.032, 24]} />
        <meshStandardMaterial
          ref={material}
          color="#17311f"
          emissive="#17311f"
          emissiveIntensity={0.1}
          roughness={0.28}
          metalness={0.1}
          toneMapped={false}
        />
      </mesh>

      <pointLight ref={glow} position={[0, 0.11, 0]} intensity={0} distance={0.9} decay={2} color="#4dffa0" />
    </group>
  );
}
