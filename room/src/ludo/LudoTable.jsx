import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { SEATS, cellOf } from "./engine.js";
import { makeBoardTexture, gridToLocal, BOARD_SIZE, TOKEN_R } from "./boardTexture.js";
import { YOU, AI } from "./useLudoGame.js";
import SeatedFigure from "../studio/SeatedFigure.jsx";
import Buzzer from "./Buzzer.jsx";

export const TABLE_TOP = 0.78;
const BOARD_Y = TABLE_TOP + 0.012;

/* The board is turned on the table. Nothing about the game cares, but it
   swings the seats round so the decision screen falls inside the player's
   eyeline rather than off at the edge of it — you can read the screen, and
   click its buttons, without getting up. */
export const BOARD_ROT = 0.44;
const COS = Math.cos(BOARD_ROT);
const SIN = Math.sin(BOARD_ROT);
const toWorld = ([x, z]) => [x * COS + z * SIN, -x * SIN + z * COS];

/* Where the two players sit. The user takes the red corner, so their own
   yard and home lane are the ones nearest them across the board. */
export const SEAT_POS = {
  [YOU]: toWorld([-1.95, -1.95]),
  [AI]: toWorld([1.95, 1.95]),
};

const BUZZER_AT = {
  [YOU]: [-1.52, -0.86],
  [AI]: [1.52, 0.86],
};

function numberTexture(n) {
  const c = document.createElement("canvas");
  c.width = c.height = 128;
  const x = c.getContext("2d");
  x.fillStyle = "rgba(10,10,15,0.82)";
  x.beginPath();
  x.arc(64, 64, 52, 0, Math.PI * 2);
  x.fill();
  x.strokeStyle = "#FF6B35";
  x.lineWidth = 7;
  x.stroke();
  x.font = "700 68px Inter, system-ui, sans-serif";
  x.fillStyle = "#F5F3EF";
  x.textAlign = "center";
  x.textBaseline = "middle";
  x.fillText(String(n), 64, 68);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

/* A token walks the track. Each step of the roll is its own tween that starts
   and finishes on a square — no chasing lerp, so the piece actually lands on
   every cell it passes through instead of gliding across the board and
   cutting the corners. A long move (being sent home) lifts higher, the way
   you'd pick a piece up rather than slide it. */
const HOP_FRACTION = 0.78;   // land, then hold a beat before the next step

function Token({ seat, index, rel, offset, selectable, onPick, stepMs }) {
  const group = useRef();
  const from = useMemo(() => new THREE.Vector3(), []);
  const to = useMemo(() => new THREE.Vector3(), []);
  const t = useRef(1);
  const arc = useRef(0.075);
  const key = useRef(null);
  const color = SEATS[seat].color;
  const hopSec = (stepMs / 1000) * HOP_FRACTION;

  useFrame((_, dt) => {
    const g = group.current;
    if (!g) return;
    const cell = cellOf(seat, rel, index);
    const [cx, cz] = gridToLocal(cell.row, cell.col);
    // Tokens sharing a safe square stand beside each other rather than inside
    // each other, so a stack is always countable.
    const x = cx + offset[0];
    const z = cz + offset[1];

    const k = `${x.toFixed(3)}|${z.toFixed(3)}`;
    if (k !== key.current) {
      const first = key.current === null;
      key.current = k;
      to.set(x, BOARD_Y, z);
      if (first) {
        g.position.copy(to);
        t.current = 1;
      } else {
        from.set(g.position.x, BOARD_Y, g.position.z);
        arc.current = Math.min(0.075 + from.distanceTo(to) * 0.075, 0.3);
        t.current = 0;
      }
    }

    if (t.current < 1) {
      t.current = Math.min(1, t.current + dt / hopSec);
      const e = t.current;
      const ease = e < 0.5 ? 2 * e * e : 1 - Math.pow(-2 * e + 2, 2) / 2;
      g.position.x = from.x + (to.x - from.x) * ease;
      g.position.z = from.z + (to.z - from.z) * ease;
      g.position.y = BOARD_Y + Math.sin(e * Math.PI) * arc.current;
    } else {
      // standing on the square, exactly on it
      g.position.x = to.x;
      g.position.z = to.z;
      g.position.y = BOARD_Y;
    }

    // A pickable token bobs and turns; everything else sits still.
    if (selectable) {
      g.rotation.y += dt * 2.2;
      g.position.y += 0.012 + Math.sin(performance.now() * 0.006 + index) * 0.012;
    } else g.rotation.y = 0;
  });

  return (
    <group
      ref={group}
      position={[0, BOARD_Y, 0]}
      onClick={(e) => {
        if (!selectable) return;
        e.stopPropagation();
        onPick(index);
      }}
      onPointerOver={() => selectable && (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      <mesh castShadow position={[0, 0.026, 0]}>
        <cylinderGeometry args={[TOKEN_R * 0.9, TOKEN_R * 1.05, 0.05, 16]} />
        <meshStandardMaterial color={color} roughness={0.32} metalness={0.15} />
      </mesh>
      <mesh position={[0, 0.062, 0]}>
        <cylinderGeometry args={[TOKEN_R * 0.42, TOKEN_R * 0.8, 0.05, 16]} />
        <meshStandardMaterial color={color} roughness={0.32} metalness={0.15} />
      </mesh>
      <mesh castShadow position={[0, 0.104, 0]}>
        <sphereGeometry args={[TOKEN_R * 0.62, 16, 12]} />
        <meshStandardMaterial
          color={color}
          roughness={0.25}
          metalness={0.2}
          emissive={color}
          emissiveIntensity={selectable ? 0.55 : 0.05}
        />
      </mesh>
    </group>
  );
}

/* Pip faces, in BoxGeometry's material order: +X -X +Y -Y +Z -Z. */
const FACE_VALUES = [1, 6, 2, 5, 3, 4];
const PIPS = {
  1: [[0.5, 0.5]],
  2: [[0.28, 0.28], [0.72, 0.72]],
  3: [[0.26, 0.26], [0.5, 0.5], [0.74, 0.74]],
  4: [[0.28, 0.28], [0.72, 0.28], [0.28, 0.72], [0.72, 0.72]],
  5: [[0.28, 0.28], [0.72, 0.28], [0.5, 0.5], [0.28, 0.72], [0.72, 0.72]],
  6: [[0.28, 0.25], [0.72, 0.25], [0.28, 0.5], [0.72, 0.5], [0.28, 0.75], [0.72, 0.75]],
};
/* Euler angles that bring each value to the top face. */
const UPRIGHT = {
  1: [0, 0, Math.PI / 2],
  2: [0, 0, 0],
  3: [-Math.PI / 2, 0, 0],
  4: [Math.PI / 2, 0, 0],
  5: [Math.PI, 0, 0],
  6: [0, 0, -Math.PI / 2],
};

function Die({ value, rolling, position }) {
  const ref = useRef();
  const materials = useMemo(
    () =>
      FACE_VALUES.map((v) => {
        const c = document.createElement("canvas");
        c.width = c.height = 128;
        const x = c.getContext("2d");
        x.fillStyle = "#F7F3E8";
        x.fillRect(0, 0, 128, 128);
        x.fillStyle = "#1b1b22";
        for (const [px, py] of PIPS[v]) {
          x.beginPath();
          x.arc(px * 128, py * 128, 12, 0, Math.PI * 2);
          x.fill();
        }
        const tex = new THREE.CanvasTexture(c);
        tex.colorSpace = THREE.SRGBColorSpace;
        return new THREE.MeshStandardMaterial({ map: tex, roughness: 0.4 });
      }),
    []
  );

  useFrame((_, dt) => {
    const d = ref.current;
    if (!d) return;
    if (rolling) {
      d.rotation.x += dt * 11;
      d.rotation.y += dt * 8;
      d.rotation.z += dt * 6;
      d.position.y = position[1] + 0.12 + Math.abs(Math.sin(performance.now() * 0.012)) * 0.1;
    } else {
      const [rx, ry, rz] = UPRIGHT[value || 1];
      const k = Math.min(1, dt * 9);
      d.rotation.x += (rx - d.rotation.x) * k;
      d.rotation.y += (ry - d.rotation.y) * k;
      d.rotation.z += (rz - d.rotation.z) * k;
      d.position.y += (position[1] - d.position.y) * k;
    }
  });

  return (
    <mesh ref={ref} position={position} material={materials} castShadow>
      <boxGeometry args={[0.13, 0.13, 0.13]} />
    </mesh>
  );
}

function Chair({ position, rotation }) {
  return (
    <group position={position} rotation={rotation}>
      <mesh position={[0, 0.44, 0]} castShadow>
        <boxGeometry args={[0.46, 0.06, 0.44]} />
        <meshStandardMaterial color="#4a3628" roughness={0.7} />
      </mesh>
      <mesh position={[0, 0.72, -0.2]} rotation={[-0.1, 0, 0]} castShadow>
        <boxGeometry args={[0.44, 0.5, 0.05]} />
        <meshStandardMaterial color="#4a3628" roughness={0.7} />
      </mesh>
      {[[-0.19, -0.18], [0.19, -0.18], [-0.19, 0.18], [0.19, 0.18]].map(([x, z], i) => (
        <mesh key={i} position={[x, 0.21, z]} castShadow>
          <boxGeometry args={[0.05, 0.42, 0.05]} />
          <meshStandardMaterial color="#3a2a20" roughness={0.7} />
        </mesh>
      ))}
    </group>
  );
}

export default function LudoTable({ ludo, focused, onSelect }) {
  const board = useMemo(() => makeBoardTexture(), []);
  const numbers = useMemo(() => [1, 2, 3, 4].map(numberTexture), []);
  const choosing = focused && ludo.phase === "choose";

  // Which tokens are sharing a square, and how far each should step aside.
  const offsets = useMemo(() => {
    const byCell = new Map();
    for (const seat of [YOU, AI]) {
      ludo.visual[seat].forEach((rel, i) => {
        const cell = cellOf(seat, rel, i);
        if (cell.kind === "yard" || cell.kind === "home") return; // already apart
        const key = `${cell.row},${cell.col}`;
        if (!byCell.has(key)) byCell.set(key, []);
        byCell.get(key).push(seat + i);
      });
    }
    const out = {};
    for (const ids of byCell.values()) {
      ids.forEach((id, k) => {
        const a = (k / ids.length) * Math.PI * 2;
        out[id] = ids.length > 1
          ? [Math.cos(a) * TOKEN_R * 0.62, Math.sin(a) * TOKEN_R * 0.62]
          : [0, 0];
      });
    }
    return out;
  }, [ludo.visual]);

  return (
    <group
      onClick={(e) => {
        e.stopPropagation();
        onSelect();
      }}
      onPointerOver={() => (document.body.style.cursor = "pointer")}
      onPointerOut={() => (document.body.style.cursor = "auto")}
    >
      {/* table */}
      <mesh position={[0, TABLE_TOP - 0.03, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[1.98, 1.98, 0.06, 56]} />
        <meshStandardMaterial color="#6b4f36" roughness={0.45} metalness={0.05} />
      </mesh>
      <mesh position={[0, 0.38, 0]} castShadow>
        <cylinderGeometry args={[0.22, 0.3, 0.74, 18]} />
        <meshStandardMaterial color="#3d2c1e" roughness={0.6} />
      </mesh>
      <mesh position={[0, 0.03, 0]} receiveShadow>
        <cylinderGeometry args={[0.7, 0.78, 0.06, 24]} />
        <meshStandardMaterial color="#3d2c1e" roughness={0.6} />
      </mesh>

      {/* everything that lives in board space turns together */}
      <group rotation={[0, BOARD_ROT, 0]}>
        <mesh position={[0, BOARD_Y, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[BOARD_SIZE, BOARD_SIZE]} />
          <meshStandardMaterial map={board} roughness={0.55} />
        </mesh>

        {[YOU, AI].map((seat) =>
          ludo.visual[seat].map((rel, i) => (
            <Token
              key={seat + i}
              seat={seat}
              index={i}
              rel={rel}
              offset={offsets[seat + i] ?? [0, 0]}
              stepMs={ludo.stepMs}
              selectable={choosing && seat === YOU && ludo.legal.includes(i)}
              onPick={ludo.pick}
            />
          ))
        )}

        {/* which key moves which token — only while a choice is open */}
        {choosing &&
          ludo.legal.map((i) => {
            const cell = cellOf(YOU, ludo.visual[YOU][i], i);
            const [cx, cz] = gridToLocal(cell.row, cell.col);
            const off = offsets[YOU + i] ?? [0, 0];
            return (
              <sprite
                key={"n" + i}
                position={[cx + off[0], BOARD_Y + 0.32, cz + off[1]]}
                scale={[0.19, 0.19, 1]}
              >
                <spriteMaterial map={numbers[i]} transparent depthTest={false} />
              </sprite>
            );
          })}

        <Die
          value={ludo.die}
          rolling={ludo.phase === "rolling"}
          position={[1.66, TABLE_TOP + 0.065, 0]}
        />

        {/* One turn light per player. Green is "it is on you"; the press is
            the throw. When the game is over it is your light that comes back
            on, because starting the next one is your move. */}
        {[YOU, AI].map((seat) => {
          const over = ludo.phase === "over";
          const mine = seat === YOU;
          return (
            <Buzzer
              key={"buzz" + seat}
              position={[BUZZER_AT[seat][0], TABLE_TOP, BUZZER_AT[seat][1]]}
              live={over ? mine : ludo.game.turn === seat}
              pressing={ludo.phase === "rolling" && ludo.game.turn === seat}
              enabled={mine && focused && (over || (ludo.yourTurn && ludo.phase === "await-roll"))}
              onPress={over ? ludo.reset : ludo.roll}
            />
          );
        })}
      </group>

      {/* the two players */}
      {[YOU, AI].map((seat) => {
        const [x, z] = SEAT_POS[seat];
        const facing = Math.atan2(-x, -z);
        const chairAt = [x * 1.16, 0, z * 1.16];
        return (
          <group key={"p" + seat}>
            <Chair position={chairAt} rotation={[0, facing, 0]} />
            <group position={[x * 1.16, 0, z * 1.16]} rotation={[0, facing, 0]}>
              <SeatedFigure
                seed={seat === YOU ? 3 : 9}
                shirt={seat === YOU ? "#2A6FB0" : "#7A4B8C"}
                working={ludo.game.turn === seat}
                typing={false}
              />
            </group>
          </group>
        );
      })}

      {/* home counters, so the score reads from across the room */}
      {[YOU, AI].map((seat) => {
        const [x, z] = SEAT_POS[seat];
        return (
          <group key={"c" + seat} position={[x * 0.42, TABLE_TOP + 0.02, z * 0.42]}>
            {Array.from({ length: ludo.homeCount(seat) }).map((_, i) => (
              <mesh key={i} position={[i * 0.08 - 0.12, 0.01, 0]}>
                <cylinderGeometry args={[0.03, 0.03, 0.012, 12]} />
                <meshStandardMaterial
                  color={SEATS[seat].color}
                  emissive={SEATS[seat].color}
                  emissiveIntensity={0.5}
                />
              </mesh>
            ))}
          </group>
        );
      })}

      <pointLight position={[0, 1.9, 0]} intensity={1.1} distance={5} decay={2} color="#ffe6c4" />
    </group>
  );
}
