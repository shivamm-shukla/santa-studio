import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import SeatedFigure from "./SeatedFigure.jsx";
import LaptopScreen from "./LaptopScreen.jsx";
import NamePlate from "./NamePlate.jsx";

/* One workstation. Local +Z points at the room's centre, and everything is
   laid out from the person outwards: they sit at z=0 in the chair, their desk
   is in front of them at +Z, and the laptop lid faces back towards their own
   face. That means the wide orbit view shows you a room of people at work,
   and reading someone's screen means going round behind their shoulder —
   which is exactly the "looking over a colleague's shoulder" framing the
   in-screen email is meant to have. */

const DESK_Y = 0.75;

export default function AgentDesk({ agent, agentState, roster, stage, focused, lightMode, showPlate, onSelect }) {
  const spill = useRef();
  const lamp = useRef();
  const lampGlow = useRef();

  // Everyone wears their own accent, muted towards office-clothes grey so a
  // room of twelve doesn't read as a colour chart.
  const shirt = useMemo(
    () => "#" + new THREE.Color(agent.color).lerp(new THREE.Color("#404050"), 0.42).getHexString(),
    [agent.color]
  );
  // Spill is pulled towards white — a lit screen throws mostly white light,
  // and a saturated accent turns the whole desk into a colour swatch.
  const spillColor = useMemo(
    () => "#" + new THREE.Color(agent.color).lerp(new THREE.Color("#ffffff"), 0.55).getHexString(),
    [agent.color]
  );
  const working = agentState.status === "working" || agent.screen === "board";
  const awake = agentState.status !== "idle" || agent.screen === "board";

  useFrame((_, dt) => {
    const k = Math.min(1, dt * 4);
    // Screen glow on the desk and on the face. In the dark this is most of
    // the light there is; with the room lit it barely registers, same as life.
    if (spill.current) {
      const target = awake ? (lightMode ? 0.35 : 1.4) : 0;
      spill.current.intensity += (target - spill.current.intensity) * k;
    }
    // Desk lamps belong to the lit room; they come on with the ceiling.
    const lampTarget = lightMode ? 1 : 0;
    if (lamp.current) lamp.current.intensity += (lampTarget * 1.6 - lamp.current.intensity) * k;
    if (lampGlow.current)
      lampGlow.current.emissiveIntensity +=
        (lampTarget - lampGlow.current.emissiveIntensity) * k;
  });

  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        onSelect(agent.id);
      }}
      onPointerOver={() => (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      {/* generous invisible click volume so a desk is easy to hit from any angle */}
      <mesh position={[0, 0.9, 0.35]} visible={false}>
        <boxGeometry args={[1.9, 1.9, 2.1]} />
        <meshBasicMaterial />
      </mesh>

      {/* ---- desk ---- */}
      <mesh position={[0, DESK_Y - 0.025, 0.8]} castShadow receiveShadow>
        <boxGeometry args={[1.7, 0.05, 0.75]} />
        <meshStandardMaterial color="#5a4433" roughness={0.55} metalness={0.05} />
      </mesh>
      {[
        [-0.78, 0.5],
        [0.78, 0.5],
        [-0.78, 1.1],
        [0.78, 1.1],
      ].map(([x, z], i) => (
        <mesh key={i} position={[x, 0.36, z]} castShadow>
          <boxGeometry args={[0.05, 0.72, 0.05]} />
          <meshStandardMaterial color="#26262f" roughness={0.4} metalness={0.6} />
        </mesh>
      ))}
      {/* modesty panel, so the desk reads as furniture rather than a floating slab */}
      <mesh position={[0, 0.5, 1.14]} receiveShadow>
        <boxGeometry args={[1.6, 0.42, 0.03]} />
        <meshStandardMaterial color="#33333f" roughness={0.8} />
      </mesh>

      {/* ---- laptop ---- */}
      <mesh position={[0, DESK_Y + 0.008, 0.72]} castShadow>
        <boxGeometry args={[0.5, 0.016, 0.34]} />
        <meshStandardMaterial color="#15151b" roughness={0.5} metalness={0.55} />
      </mesh>
      {/* keyboard well and trackpad, so the base isn't a blank slab */}
      <mesh position={[0, DESK_Y + 0.018, 0.655]}>
        <boxGeometry args={[0.44, 0.004, 0.16]} />
        <meshStandardMaterial color="#0b0b0f" roughness={0.95} />
      </mesh>
      <mesh position={[0, DESK_Y + 0.018, 0.79]}>
        <boxGeometry args={[0.17, 0.004, 0.11]} />
        <meshStandardMaterial color="#121218" roughness={0.6} metalness={0.3} />
      </mesh>
      <group position={[0, DESK_Y + 0.016, 0.885]} rotation={[0.3, 0, 0]}>
        <mesh position={[0, 0.16, 0.012]} castShadow>
          <boxGeometry args={[0.52, 0.34, 0.016]} />
          <meshStandardMaterial color="#1b1b22" roughness={0.35} metalness={0.7} />
        </mesh>
        <mesh position={[0, 0.16, -0.001]} rotation={[0, Math.PI, 0]}>
          <planeGeometry args={[0.47, 0.29]} />
          <LaptopScreen
            agent={agent}
            agentState={agentState}
            roster={roster}
            stage={stage}
            focused={focused}
          />
        </mesh>
      </group>
      <pointLight
        ref={spill}
        position={[0, DESK_Y + 0.22, 0.6]}
        color={spillColor}
        intensity={0}
        distance={2.6}
        decay={2}
      />

      {/* ---- desk lamp ---- */}
      <group position={[-0.68, DESK_Y, 0.95]}>
        <mesh position={[0, 0.01, 0]}>
          <cylinderGeometry args={[0.06, 0.07, 0.02, 12]} />
          <meshStandardMaterial color="#2b2b35" roughness={0.5} metalness={0.5} />
        </mesh>
        <mesh position={[0, 0.16, 0]} rotation={[0.25, 0, 0]}>
          <cylinderGeometry args={[0.008, 0.008, 0.32, 8]} />
          <meshStandardMaterial color="#2b2b35" roughness={0.5} metalness={0.5} />
        </mesh>
        <group position={[0, 0.32, -0.1]} rotation={[0.9, 0, 0]}>
          <mesh>
            <coneGeometry args={[0.08, 0.11, 14, 1, true]} />
            <meshStandardMaterial color="#3a3a45" roughness={0.6} metalness={0.3} side={0} />
          </mesh>
          <mesh>
            <coneGeometry args={[0.077, 0.107, 14, 1, true]} />
            <meshStandardMaterial
              ref={lampGlow}
              color="#2e2e38"
              emissive="#ffd9a0"
              emissiveIntensity={0}
              side={1}
              toneMapped={false}
            />
          </mesh>
        </group>
        <pointLight
          ref={lamp}
          position={[0, 0.28, -0.16]}
          color="#ffd9a0"
          intensity={0}
          distance={2.4}
          decay={2}
        />
      </group>

      {/* ---- mug ---- */}
      <mesh position={[0.52, DESK_Y + 0.045, 0.7]} castShadow>
        <cylinderGeometry args={[0.045, 0.04, 0.09, 14]} />
        <meshStandardMaterial color={agent.color} roughness={0.45} />
      </mesh>

      {/* ---- chair ---- */}
      <group>
        <mesh position={[0, 0.44, 0]} castShadow>
          <cylinderGeometry args={[0.25, 0.25, 0.07, 20]} />
          <meshStandardMaterial color="#2a2a34" roughness={0.85} />
        </mesh>
        <mesh position={[0, 0.72, -0.24]} rotation={[-0.14, 0, 0]} castShadow>
          <boxGeometry args={[0.44, 0.52, 0.06]} />
          <meshStandardMaterial color="#2a2a34" roughness={0.85} />
        </mesh>
        <mesh position={[0, 0.24, 0]}>
          <cylinderGeometry args={[0.035, 0.035, 0.34, 10]} />
          <meshStandardMaterial color="#191920" roughness={0.4} metalness={0.7} />
        </mesh>
        {[0, 1, 2, 3, 4].map((i) => {
          const a = (i / 5) * Math.PI * 2;
          return (
            <mesh
              key={i}
              position={[Math.sin(a) * 0.13, 0.06, Math.cos(a) * 0.13]}
              rotation={[0, -a, 0]}
            >
              <boxGeometry args={[0.04, 0.03, 0.26]} />
              <meshStandardMaterial color="#191920" roughness={0.4} metalness={0.7} />
            </mesh>
          );
        })}
      </group>

      <SeatedFigure seed={agent.name.length + agent.id.length} shirt={shirt} working={working} />

      {showPlate && (
        <NamePlate
          label={agent.name}
          color={agent.color}
          status={agentState.status}
          position={[0, 1.62, 0.6]}
        />
      )}
    </group>
  );
}
