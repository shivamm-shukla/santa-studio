import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

/* A laptop on a desk, with the site running on it.

   Built out of boxes rather than imported, because the shot never gets close
   enough to a hinge for a model to earn its download - what sells it is the
   proportions, the bevel of light along the top edge of the lid, and the fact
   that the screen is genuinely emitting rather than being lit.

   The picture is the landing page, captured at the shape of this screen and
   played back as a video texture. It is seeked by frame, never played, so the
   recorder gets the same frame every run. */

const SCREEN_W = 1.32;
const SCREEN_H = SCREEN_W * (1050 / 1680);
const BEZEL = 0.018;
const LID_T = 0.012;
const BASE_H = 0.026;
const BASE_D = SCREEN_H * 0.94;

/* Open a little past upright, the way one on a desk actually sits. */
const LID_TILT = -0.30;

/* What is playing on the screen, and how long it is.

   Two things get shown on this machine over the course of the demo: the site,
   at the start, and the film the pipeline made, near the end. Both are frame
   sequences on disk under /room/reel/, so the only difference is which
   directory and how many frames - ?src= picks. */
const SOURCES = {
  landing: { dir: "landing", frames: 330 },
  film: { dir: "film", frames: 900 },
};

function chosenSource() {
  const want = new URLSearchParams(location.search).get("src") || "landing";
  return SOURCES[want] ?? SOURCES.landing;
}

export default function Macbook({ screenRef, lightsOn, screenOn }) {
  const glow = useRef();
  const screenMat = useRef();
  const lidGroup = useRef();

  /* The picture on the screen, as an image sequence rather than a video.

     A VideoTexture is the obvious way to do this and it cost an evening: at
     1080x1920 the decoder and the renderer together lost the WebGL context
     outright, every run, and a lost context renders a white page. The
     recorder is asking for one frame at a time anyway - it has no use for
     playback - so it asks for one image at a time instead, which has no
     decoder in it at all.

     Also more accurate. A seeked video lands on the nearest keyframe; this
     lands on the exact frame that was captured. */
  const { texture, canvas } = useMemo(() => {
    const surface = document.createElement("canvas");
    surface.width = 1680;
    surface.height = 1050;
    const context = surface.getContext("2d");
    context.fillStyle = "#07070b";
    context.fillRect(0, 0, surface.width, surface.height);
    const map = new THREE.CanvasTexture(surface);
    map.colorSpace = THREE.SRGBColorSpace;
    map.minFilter = THREE.LinearFilter;
    map.magFilter = THREE.LinearFilter;
    map.anisotropy = 8;
    return { texture: map, canvas: surface };
  }, []);

  useEffect(() => {
    const context = canvas.getContext("2d");
    const cache = new Map();
    const source = chosenSource();

    /* Draws the landing capture's frame `index`. Returns a promise so the
       recorder can wait for the picture before it photographs the room. */
    const show = (index) =>
      new Promise((resolve) => {
        const n = Math.max(0, Math.min(source.frames - 1, Math.round(index)));
        const draw = (image) => {
          context.drawImage(image, 0, 0, canvas.width, canvas.height);
          texture.needsUpdate = true;
          resolve();
        };
        if (cache.has(n)) return draw(cache.get(n));
        const image = new Image();
        image.onload = () => {
          // A handful either side is all that is ever wanted again.
          if (cache.size > 12) cache.delete(cache.keys().next().value);
          cache.set(n, image);
          draw(image);
        };
        image.onerror = () => resolve();
        image.src = `/room/reel/${source.dir}/f${String(n).padStart(5, "0")}.jpg`;
      });

    if (screenRef) screenRef.current = show;
    window.__screenFrame = show;
    return () => {
      delete window.__screenFrame;
    };
  }, [canvas, texture, screenRef]);

  useEffect(() => () => texture.dispose(), [texture]);

  useFrame((_, dt) => {
    const k = 1 - Math.exp(-dt * 4);
    // The screen's own light on the desk and the underside of the lid.
    // Asleep, the screen throws nothing and the lid is lit only by the room.
    const want = screenOn ? (lightsOn ? 1.1 : 1.5) : 0.0;
    if (glow.current) glow.current.intensity += (want - glow.current.intensity) * k;
    if (screenMat.current) {
      /* A screen in a dark room reads brighter than the same screen in a lit
         one, which is a fact about eyes rather than about screens - but a
         picture has to do the same thing or the dark shot looks flat.

         Asleep it is not black: it goes down to a few percent, so the glass
         still carries the rim light and you can tell there is a screen there
         to come on. Black glass reads as a hole in the lid. */
      const level = screenOn ? (lightsOn ? 1.0 : 1.35) : 0.045;
      screenMat.current.color.lerp(new THREE.Color(level, level, level), k * 0.75);
    }
  });

  return (
    <group>
      {/* The desk. Wide enough to fall out of frame on every shot, and matt
          enough that the screen's light sits on it rather than smearing. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.001, 0]} receiveShadow>
        <planeGeometry args={[24, 24]} />
        <meshStandardMaterial color="#141419" roughness={0.86} metalness={0.05} />
      </mesh>
      {/* A wall behind, so the wide shots end on something rather than on the
          clear colour. The fog is what makes it read as distance. */}
      <mesh position={[0, 2.4, -3.2]}>
        <planeGeometry args={[26, 9]} />
        <meshStandardMaterial color="#101015" roughness={0.95} metalness={0} />
      </mesh>

      {/* Base. */}
      <mesh position={[0, BASE_H / 2, BASE_D / 2]} castShadow receiveShadow>
        <boxGeometry args={[SCREEN_W + BEZEL * 2, BASE_H, BASE_D]} />
        <meshStandardMaterial color="#c8ccd2" roughness={0.34} metalness={0.86} />
      </mesh>
      {/* Keyboard well and trackpad, as two shallow insets. */}
      <mesh position={[0, BASE_H + 0.0005, BASE_D * 0.36]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[SCREEN_W * 0.86, BASE_D * 0.42]} />
        <meshStandardMaterial color="#1b1b21" roughness={0.72} metalness={0.2} />
      </mesh>
      <mesh position={[0, BASE_H + 0.0005, BASE_D * 0.76]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[SCREEN_W * 0.36, BASE_D * 0.26]} />
        <meshStandardMaterial color="#b9bec6" roughness={0.28} metalness={0.8} />
      </mesh>

      {/* Lid, hinged at the back edge of the base. */}
      <group ref={lidGroup} position={[0, BASE_H, 0]} rotation={[LID_TILT, 0, 0]}>
        <mesh position={[0, SCREEN_H / 2 + BEZEL, -LID_T / 2]} castShadow>
          <boxGeometry args={[SCREEN_W + BEZEL * 2, SCREEN_H + BEZEL * 2.6, LID_T]} />
          <meshStandardMaterial color="#c8ccd2" roughness={0.32} metalness={0.88} />
        </mesh>
        {/* The picture. */}
        <mesh position={[0, SCREEN_H / 2 + BEZEL, LID_T / 2 + 0.0006]}>
          <planeGeometry args={[SCREEN_W, SCREEN_H]} />
          <meshBasicMaterial ref={screenMat} map={texture} toneMapped={false} />
        </mesh>
        {/* What the screen throws back into the room. */}
        {/* What the screen throws forward. Kept short and steep: as a wide
            soft light it painted a metre of bloom across the desk and the
            shot stopped being a photograph of a laptop. */}
        <pointLight
          ref={glow}
          position={[0, SCREEN_H / 2, 0.30]}
          color="#8fb6ff"
          distance={1.5}
          decay={2.4}
          intensity={1.1}
        />
      </group>
    </group>
  );
}
