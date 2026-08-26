import { useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { WALL_H } from "./layout.js";

/* Dark and light are not a CSS skin here: they are the room's own lights
   being switched off and on. Dark leaves the place lit by screens; light
   brings up the ceiling rig, the pendant over the table and every desk lamp,
   and the whole space visibly fills in. */

const NIGHT_BG = new THREE.Color("#07070b");
const DAY_BG = new THREE.Color("#c9c8d2");

/* Ambient goes warm and near-white with the lights on: the cold blue that
   reads as moonlight in the dark state is what kept the lit room looking
   like an evening. */
const NIGHT_AMBIENT = new THREE.Color("#8d90a8");
const DAY_AMBIENT = new THREE.Color("#fff4e6");

const CEILING = [
  [4.6, 0], [0, 4.6], [-4.6, 0], [0, -4.6],
  [7.4, 7.4], [-7.4, 7.4], [7.4, -7.4], [-7.4, -7.4],
];

export default function Lighting({ lightMode, at, photo, film }) {
  const { scene } = useThree();
  const ambient = useRef();
  const hemi = useRef();
  const key = useRef();
  const lamps = useRef([]);
  const panels = useRef([]);
  const pendant = useRef();
  const pendantShade = useRef();
  const bg = useRef(NIGHT_BG.clone());
  const here = useRef();

  useFrame((_, dt) => {
    const k = film ? 1 : 1 - Math.exp(-dt * 3.2);
    const t = lightMode ? 1 : 0;

    /* Filming has its own rig, the way a shoot does. It keeps the night look
       - this is a studio at night and that is the point of it - but lifts the
       floor enough that the camera sees the room rather than a black frame.
       `k` is 1 above, so it lands on the first frame: a recorder seeks to a
       time and captures immediately, and has no seconds to spare waiting for
       a light to ease up. */
    if (film) {
      if (ambient.current) {
        ambient.current.intensity = 0.62;
        ambient.current.color.copy(NIGHT_AMBIENT);
      }
      if (hemi.current) hemi.current.intensity = 0.42;
      if (key.current) key.current.intensity = 0.75;
      lamps.current.forEach((l) => { if (l) l.intensity = 22; });
      panels.current.forEach((p) => { if (p) p.emissiveIntensity = 0.55; });
      if (pendant.current) pendant.current.intensity = 6.5;
      if (pendantShade.current) pendantShade.current.emissiveIntensity = 0.9;
      if (here.current) here.current.intensity = at ? 34 : 0;
      if (bg.current) {
        bg.current.copy(NIGHT_BG);
        scene.background = bg.current;
        if (scene.fog) scene.fog.color.copy(bg.current);
      }
      return;
    }

    /* Lights on has to look like a lit room, not like a slightly less dark
       one. The numbers here were tuned against the dark state and left the
       bright state reading as dusk - which makes the switch feel broken even
       though it is doing something. */
    if (ambient.current) {
      ambient.current.intensity += (THREE.MathUtils.lerp(0.16, 2.7, t) - ambient.current.intensity) * k;
      ambient.current.color.lerp(lightMode ? DAY_AMBIENT : NIGHT_AMBIENT, k);
    }
    if (hemi.current)
      hemi.current.intensity += (THREE.MathUtils.lerp(0.09, 2.0, t) - hemi.current.intensity) * k;
    if (key.current)
      key.current.intensity += (THREE.MathUtils.lerp(0.12, 3.4, t) - key.current.intensity) * k;

    lamps.current.forEach((l) => {
      // Desk lamps stay on a little in the dark: an office at night has
      // lamps burning at the desks people are still working at.
      if (l) l.intensity += ((9 + t * 27) - l.intensity) * k;
    });
    panels.current.forEach((p) => {
      if (p) p.emissiveIntensity += (THREE.MathUtils.lerp(0.02, 1.15, t) - p.emissiveIntensity) * k;
    });
    // The pendant over the Ludo table is the one light that never goes fully
    // out — you can always see the board you're playing on.
    if (pendant.current)
      pendant.current.intensity += (THREE.MathUtils.lerp(2.4, 7, t) - pendant.current.intensity) * k;
    if (pendantShade.current)
      pendantShade.current.emissiveIntensity +=
        (THREE.MathUtils.lerp(0.35, 1.1, t) - pendantShade.current.emissiveIntensity) * k;

    /* Wherever you are standing gets a practical.

       Somewhere you have walked up to has to be lit well enough to read, and
       with the lights off the room's own rig does not reach into a corner or
       through a wall - so a screen you had gone to look at was a black
       rectangle in a black room. It follows the focus rather than being one
       lamp per place, so every place gets it, including the ones added next. */
    if (here.current) {
      /* Enough to read what you have walked up to, and no more. The first
         try at this was far too weak to do anything; the second was strong
         enough to light the whole room, which made "lights off" mean nothing.
         Off should be off - the screens are what you see by. */
      /* Photography gets its own light, because the two jobs disagree. In the
         app, lights off has to mean off - you see by the screens, which is
         the whole point of the switch. In a picture of the place, off that
         dark is an unreadable rectangle. A real studio lights a room for the
         camera too. */
      const target = at ? (photo ? 120 : lightMode ? 26 : 15) : 0;
      here.current.intensity += (target - here.current.intensity) * k;
      if (at) {
        here.current.position.set(at[0], at[1] + 0.9, at[2]);
      }
    }

    bg.current.lerp(lightMode ? DAY_BG : NIGHT_BG, k);
    scene.background = bg.current;
    if (scene.fog) {
      scene.fog.color.copy(bg.current);
      scene.fog.near = THREE.MathUtils.lerp(scene.fog.near, lightMode ? 26 : 15, k);
      scene.fog.far = THREE.MathUtils.lerp(scene.fog.far, lightMode ? 60 : 40, k);
    }
  });

  return (
    <group>
      {/* See the note in the frame loop: this is the light that makes a place
          you have walked up to readable, whatever the switch says. */}
      <pointLight
        ref={here}
        intensity={0}
        distance={photo || film ? 22 : 7}
        decay={photo || film ? 1.1 : 1.5}
        color="#ffe9d2"
      />

      <ambientLight ref={ambient} intensity={0.24} color="#8d90a8" />
      <hemisphereLight ref={hemi} intensity={0.13} color="#cfd6ff" groundColor="#3a2c22" />
      <directionalLight
        ref={key}
        position={[6, 11, 4]}
        intensity={0.25}
        color="#fff3e2"
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-camera-near={1}
        shadow-camera-far={40}
        shadow-camera-left={-14}
        shadow-camera-right={14}
        shadow-camera-top={14}
        shadow-camera-bottom={-14}
      />

      {/* ceiling rig */}
      {CEILING.map(([x, z], i) => (
        <group key={i} position={[x, WALL_H - 0.14, z]}>
          {/* the lit diffuser, hung just below its housing so the two can't
              fight over the same plane */}
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.55, 28]} />
            <meshStandardMaterial
              ref={(el) => (panels.current[i] = el)}
              color="#f3f0e6"
              emissive="#fff1d8"
              emissiveIntensity={0.02}
              toneMapped={false}
            />
          </mesh>
          <mesh position={[0, 0.09, 0]}>
            <cylinderGeometry args={[0.6, 0.6, 0.16, 28]} />
            <meshStandardMaterial color="#5a5a68" roughness={0.5} metalness={0.4} />
          </mesh>
          <pointLight
            ref={(el) => (lamps.current[i] = el)}
            position={[0, -0.25, 0]}
            intensity={0}
            distance={16}
            decay={2}
            color="#fff0d6"
          />
        </group>
      ))}

      {/* pendant over the Ludo table */}
      <group position={[0, 2.95, 0]}>
        <mesh position={[0, 0.7, 0]}>
          <cylinderGeometry args={[0.012, 0.012, 1.4, 8]} />
          <meshStandardMaterial color="#1c1c24" />
        </mesh>
        <mesh castShadow>
          <coneGeometry args={[0.52, 0.42, 28, 1, true]} />
          <meshStandardMaterial color="#31313d" roughness={0.55} metalness={0.3} side={0} />
        </mesh>
        {/* the inside of the shade is what you actually see glowing */}
        <mesh>
          <coneGeometry args={[0.5, 0.4, 28, 1, true]} />
          <meshStandardMaterial
            ref={pendantShade}
            color="#2a2a33"
            emissive="#ffe3b8"
            emissiveIntensity={0.35}
            side={1}
            toneMapped={false}
          />
        </mesh>
        <mesh position={[0, -0.14, 0]}>
          <sphereGeometry args={[0.07, 12, 10]} />
          <meshStandardMaterial color="#fff3dd" emissive="#ffe3b8" emissiveIntensity={1.4} toneMapped={false} />
        </mesh>
        <pointLight
          ref={pendant}
          position={[0, -0.2, 0]}
          intensity={2.4}
          distance={11}
          decay={2}
          color="#ffe0b2"
        />
      </group>
    </group>
  );
}
