import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";

/* A seated person, built from primitives and proportioned like a human:
   head, neck, torso, two arms with elbows, two legs with knees, feet on the
   floor. Origin is on the floor directly under the hips; the figure faces
   +Z, which is the direction of their own desk. */

const SKINS = ["#e0ac7e", "#c68a5a", "#8d5524", "#f1c9a5", "#a56a43", "#6b4226"];
const HAIRS = ["#1a1410", "#2b1d14", "#0d0b0a", "#4a3520", "#5b5b60"];

export default function SeatedFigure({
  seed = 0,
  shirt = "#3a3a48",
  working = false,
  typing = true,
}) {
  const skin = SKINS[seed % SKINS.length];
  const hair = HAIRS[(seed * 3) % HAIRS.length];
  const pants = seed % 2 ? "#232330" : "#2c2c3a";

  const torso = useRef();
  const head = useRef();
  const hands = useRef([]);
  const arms = useRef([]);
  const posture = useRef(0);   // 0 = hands on the keyboard, 1 = hands in the lap
  const phase = useMemo(() => Math.random() * Math.PI * 2, []);

  const mats = useMemo(
    () => ({
      skin: { color: skin, roughness: 0.72, metalness: 0 },
      hair: { color: hair, roughness: 0.9, metalness: 0 },
      shirt: { color: shirt, roughness: 0.78, metalness: 0 },
      pants: { color: pants, roughness: 0.85, metalness: 0 },
      shoe: { color: "#15151b", roughness: 0.6, metalness: 0.1 },
    }),
    [skin, hair, shirt, pants]
  );

  useFrame(({ clock }, dt) => {
    const t = clock.elapsedTime;
    const k = Math.min(1, dt * 3.5);

    // Waiting for work means sitting back with your hands off the keys; being
    // given work means leaning in. It should be obvious across the room which
    // of the twelve are actually busy.
    posture.current += ((working ? 0 : 1) - posture.current) * k;
    arms.current.forEach((a) => {
      if (a) a.rotation.x = posture.current * 0.82;
    });

    // Breathing, always. Everyone in the room is alive, working or not.
    if (torso.current) {
      torso.current.scale.setScalar(1 + Math.sin(t * 1.1 + phase) * 0.012);
      torso.current.rotation.x = 0.1 - posture.current * 0.17;
    }
    // Idle agents look around the room; working agents keep their eyes on
    // the screen and their hands moving.
    if (head.current) {
      head.current.rotation.y = working
        ? Math.sin(t * 0.6 + phase) * 0.05
        : Math.sin(t * 0.35 + phase) * 0.5;
      head.current.rotation.x = working ? 0.16 : Math.sin(t * 0.5 + phase) * 0.06;
    }
    hands.current.forEach((h, i) => {
      if (!h) return;
      const active = working && typing;
      h.position.y = -0.162 + (active ? Math.abs(Math.sin(t * 9 + i * 2.1 + phase)) * 0.02 : 0);
    });
  });

  return (
    <group>
      {/* hips */}
      <mesh position={[0, 0.5, 0.04]} castShadow>
        <capsuleGeometry args={[0.15, 0.1, 6, 12]} />
        <meshStandardMaterial {...mats.pants} />
      </mesh>

      {/* torso, leaning very slightly into the desk */}
      <group ref={torso} position={[0, 0.55, 0.02]} rotation={[0.1, 0, 0]}>
        <mesh position={[0, 0.22, 0]} castShadow>
          <capsuleGeometry args={[0.165, 0.26, 8, 16]} />
          <meshStandardMaterial {...mats.shirt} />
        </mesh>
        {/* shoulders */}
        <mesh position={[0, 0.4, 0]} scale={[1.25, 0.6, 0.9]} castShadow>
          <sphereGeometry args={[0.17, 16, 12]} />
          <meshStandardMaterial {...mats.shirt} />
        </mesh>
        {/* neck */}
        <mesh position={[0, 0.5, 0.005]}>
          <cylinderGeometry args={[0.05, 0.055, 0.09, 10]} />
          <meshStandardMaterial {...mats.skin} />
        </mesh>
      </group>

      {/* head */}
      <group ref={head} position={[0, 1.16, 0.07]}>
        <mesh castShadow>
          <sphereGeometry args={[0.113, 20, 18]} />
          <meshStandardMaterial {...mats.skin} />
        </mesh>
        {/* jaw gives the head a front, so we can tell which way they face */}
        <mesh position={[0, -0.04, 0.03]} scale={[0.86, 0.78, 0.92]}>
          <sphereGeometry args={[0.1, 16, 14]} />
          <meshStandardMaterial {...mats.skin} />
        </mesh>
        {/* hair cap, open at the face */}
        <mesh position={[0, 0.016, -0.012]} rotation={[-0.22, 0, 0]}>
          <sphereGeometry args={[0.119, 20, 14, 0, Math.PI * 2, 0, Math.PI / 1.85]} />
          <meshStandardMaterial {...mats.hair} />
        </mesh>
        {[-1, 1].map((s) => (
          <mesh key={s} position={[s * 0.045, 0.005, 0.1]}>
            <sphereGeometry args={[0.017, 10, 8]} />
            <meshStandardMaterial color="#1b1b22" roughness={0.35} />
          </mesh>
        ))}
        {[-1, 1].map((s) => (
          <mesh key={"ear" + s} position={[s * 0.108, -0.005, 0]} scale={[0.5, 1, 0.7]}>
            <sphereGeometry args={[0.032, 10, 8]} />
            <meshStandardMaterial {...mats.skin} />
          </mesh>
        ))}
      </group>

      {/* arms, hinged at the shoulder so the whole limb swings between
          typing and resting in one rotation */}
      {[-1, 1].map((s, i) => (
        <group
          key={"arm" + s}
          ref={(el) => (arms.current[i] = el)}
          position={[s * 0.2, 0.95, 0.02]}
        >
          <mesh position={[0, -0.085, 0.04]} rotation={[0.5, 0, s * 0.12]} castShadow>
            <capsuleGeometry args={[0.048, 0.19, 6, 10]} />
            <meshStandardMaterial {...mats.shirt} />
          </mesh>
          <mesh position={[s * -0.02, -0.168, 0.27]} rotation={[Math.PI / 2, 0, s * 0.06]} castShadow>
            <capsuleGeometry args={[0.043, 0.22, 6, 10]} />
            <meshStandardMaterial {...mats.skin} />
          </mesh>
          <mesh
            ref={(el) => (hands.current[i] = el)}
            position={[s * -0.035, -0.162, 0.43]}
            scale={[1, 0.55, 1.25]}
          >
            <sphereGeometry args={[0.052, 12, 10]} />
            <meshStandardMaterial {...mats.skin} />
          </mesh>
        </group>
      ))}

      {/* legs: thighs forward along the seat, shins down to the floor */}
      {[-1, 1].map((s) => (
        <group key={"leg" + s}>
          <mesh position={[s * 0.095, 0.5, 0.22]} rotation={[Math.PI / 2, 0, 0]} castShadow>
            <capsuleGeometry args={[0.072, 0.28, 6, 10]} />
            <meshStandardMaterial {...mats.pants} />
          </mesh>
          <mesh position={[s * 0.095, 0.27, 0.4]} rotation={[0.12, 0, 0]} castShadow>
            <capsuleGeometry args={[0.062, 0.3, 6, 10]} />
            <meshStandardMaterial {...mats.pants} />
          </mesh>
          <mesh position={[s * 0.095, 0.045, 0.45]} castShadow>
            <boxGeometry args={[0.11, 0.075, 0.24]} />
            <meshStandardMaterial {...mats.shoe} />
          </mesh>
        </group>
      ))}
    </group>
  );
}
