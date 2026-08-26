import { useEffect, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import Macbook from "./Macbook.jsx";
import { shotAt, TOTAL } from "./shots.js";

/* The laptop sequence: the site running on a machine on a desk, filmed.

   Driven entirely by window.__shotSeek(t), like the studio - the recorder
   asks for a time and gets exactly that frame, every run. Nothing here plays
   on its own, including the video on the screen: it is seeked, because a
   playing video and a browser rendering at one frame a second disagree about
   what time it is. */

function Rig({ time, onLights, onScreen }) {
  const { camera } = useThree();
  const look = useRef(new THREE.Vector3());

  useFrame(() => {
    const s = shotAt(time.current);
    onLights(s.lightsOn);
    onScreen(s.screenOn);

    const cp = Math.cos(s.pol);
    camera.position.set(
      s.target[0] + Math.sin(s.az) * cp * s.dist,
      s.target[1] + Math.sin(s.pol) * s.dist,
      s.target[2] + Math.cos(s.az) * cp * s.dist
    );
    camera.position.y = Math.max(0.035, camera.position.y);
    look.current.set(s.target[0], s.target[1], s.target[2]);
    camera.lookAt(look.current);

    if (camera.fov !== s.fov) {
      camera.fov = s.fov;
      camera.updateProjectionMatrix();
    }

  });

  return null;
}

function Lights({ on }) {
  const key = useRef();
  const fill = useRef();
  const rim = useRef();
  const amb = useRef();
  const { scene } = useThree();

  useFrame((_, dt) => {
    const k = 1 - Math.exp(-dt * 3.4);
    const t = on ? 1 : 0;
    /* Lights off is not black: it is one hard rim from behind and whatever
       the screen throws forward, which is what a desk at night looks like.
       Lights on brings up a soft key from above and in front. */
    if (amb.current) amb.current.intensity += (THREE.MathUtils.lerp(0.06, 0.5, t) - amb.current.intensity) * k;
    if (key.current) key.current.intensity += (THREE.MathUtils.lerp(0.15, 3.1, t) - key.current.intensity) * k;
    if (fill.current) fill.current.intensity += (THREE.MathUtils.lerp(0.05, 0.9, t) - fill.current.intensity) * k;
    if (rim.current) rim.current.intensity += (THREE.MathUtils.lerp(2.6, 3.4, t) - rim.current.intensity) * k;
    if (scene.fog) {
      const want = on ? 0.055 : 0.012;
      scene.fog.color.setScalar(want);
      scene.background = scene.fog.color;
    }
  });

  return (
    <>
      <ambientLight ref={amb} intensity={0.06} color="#9fb0d8" />
      <directionalLight
        ref={key}
        position={[1.6, 2.4, 2.0]}
        intensity={0.15}
        color="#fff2e2"
        castShadow
        shadow-mapSize={[1024, 1024]}
      />
      <directionalLight ref={fill} position={[-2.2, 1.1, 1.4]} intensity={0.05} color="#bcd0ff" />
      {/* The rim that draws the top edge of the lid out of the dark. */}
      <directionalLight ref={rim} position={[-1.1, 1.5, -2.6]} intensity={2.6} color="#ff9d5c" />
    </>
  );
}

export default function Laptop() {
  const time = useRef(0);
  const screenRef = useRef();
  const [lightsOn, setLightsOn] = useState(false);
  const [screenOn, setScreenOn] = useState(false);

  useEffect(() => {
    window.__shotSeconds = TOTAL;
    /* Seeking sets the camera and the picture together, and resolves only
       once the picture is actually on the screen - so the recorder can await
       it rather than guessing at a settle time. */
    window.__shotSeek = async (t) => {
      time.current = t;
      const { videoTime } = shotAt(t);
      if (videoTime !== null && screenRef.current) {
        await screenRef.current(videoTime * 30);
      }
    };
    window.__shotReady = () => !!screenRef.current;
    return () => {
      delete window.__shotSeek;
      delete window.__shotSeconds;
      delete window.__shotReady;
    };
  }, []);

  return (
    <Canvas
      shadows
      dpr={1}
      camera={{ fov: 34, near: 0.02, far: 60, position: [0, 0.4, 2.2] }}
      /* No preserveDrawingBuffer: at 1080x1920 with shadows it was enough to
         lose the context outright, and the recorder screenshots the page
         rather than reading the buffer, so nothing needs it. */
      gl={{ antialias: true, powerPreference: "high-performance" }}
      onCreated={({ scene, gl }) => {
        scene.fog = new THREE.Fog(new THREE.Color(0.012, 0.012, 0.012), 3.2, 9);
        scene.background = scene.fog.color;
        gl.toneMapping = THREE.ACESFilmicToneMapping;
        gl.toneMappingExposure = 1.15;
      }}
    >
      <Lights on={lightsOn} />
      <Macbook screenRef={screenRef} lightsOn={lightsOn} screenOn={screenOn} />
      <Rig time={time} onLights={setLightsOn} onScreen={setScreenOn} />
    </Canvas>
  );
}
