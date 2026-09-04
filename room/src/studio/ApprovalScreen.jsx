import { useEffect, useMemo, useRef, useState } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { AW, AH, buttonRects, drawApproval, VIDEO_PANE, DOWNLOAD_CHIP } from "./approvalDraw.js";
import { ACCENT } from "../theme.js";

/* A large display on a stand beside the Ludo table — built as an actual
   monitor: a thin anodised bezel, a glass front with a real reflection on it,
   and a standby LED in the chin. Nothing about the hardware glows. When a
   decision is waiting, the *panel* lights up and throws light into the room,
   which is what a screen in a dark studio actually does.

   Clicks are hit-tested against the very same button rectangles the painter
   uses, so the buttons are part of the screen rather than HTML floating over
   it — and because that works at any range, a decision can be answered from
   the seat at the table. */

const PANEL_W = 2.1;
const PANEL_H = (AH / AW) * PANEL_W;
const BEZEL = 0.035;

/* A soft diagonal band, sitting a couple of millimetres in front of the
   pixels — the giveaway that there is glass over them. */
function makeSheen() {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 320;
  const x = c.getContext("2d");
  const g = x.createLinearGradient(0, 0, 512, 320);
  g.addColorStop(0, "rgba(255,255,255,0.16)");
  g.addColorStop(0.22, "rgba(255,255,255,0.05)");
  g.addColorStop(0.42, "rgba(255,255,255,0)");
  g.addColorStop(0.72, "rgba(255,255,255,0)");
  g.addColorStop(0.88, "rgba(255,255,255,0.035)");
  g.addColorStop(1, "rgba(255,255,255,0.09)");
  x.fillStyle = g;
  x.fillRect(0, 0, 512, 320);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

export default function ApprovalScreen({ request, stage, onAnswer, onSelect, ...props }) {
  const { ctx, texture } = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = AW;
    canvas.height = AH;
    const c = canvas.getContext("2d");
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    return { ctx: c, texture: tex };
  }, []);
  const sheen = useMemo(makeSheen, []);

  const [hovered, setHovered] = useState(null);
  const [hotSpot, setHotSpot] = useState(null);
  const [playing, setPlaying] = useState(false);
  const spill = useRef();
  const led = useRef();
  const video = useRef(null);

  /* The cut itself, when the decision is about one.

     A detached element would draw fine but plays no sound in some browsers,
     so it is parked in the page at no size - the picture goes to the panel in
     the room, and the audio comes out of the page it is already running in.
     Nothing autoplays: the first click on the pane is the gesture the browser
     wants, and an approval screen that started shouting on its own would be
     worse anyway. */
  const source = request?.payload?.video_url || null;
  useEffect(() => {
    if (!source) return undefined;
    const element = document.createElement("video");
    element.src = source;
    element.preload = "metadata";
    element.playsInline = true;
    element.crossOrigin = "anonymous";
    element.style.cssText = "position:fixed;width:1px;height:1px;opacity:0;pointer-events:none";
    element.addEventListener("play", () => setPlaying(true));
    element.addEventListener("pause", () => setPlaying(false));
    element.addEventListener("ended", () => setPlaying(false));
    document.body.appendChild(element);
    video.current = element;
    return () => {
      element.pause();
      element.removeAttribute("src");
      element.load();
      element.remove();
      video.current = null;
      setPlaying(false);
    };
  }, [source]);

  useFrame(({ clock }, dt) => {
    const pulse = request ? (Math.sin(clock.elapsedTime * 2.4) + 1) / 2 : 0;
    drawApproval(ctx, {
      request,
      stage,
      pulse,
      hovered,
      video: source ? video.current : null,
      playing,
      hotVideo: hotSpot === "video",
      hotDownload: hotSpot === "download",
    });
    texture.needsUpdate = true;

    const k = Math.min(1, dt * 5);
    // A lit panel is a light source. That, and only that, is how this screen
    // asks for attention from across the room.
    if (spill.current) {
      const target = request ? 2.6 + pulse * 0.8 : 0.12;
      spill.current.intensity += (target - spill.current.intensity) * k;
      spill.current.color.lerp(new THREE.Color(request ? "#ffe4d4" : "#8fa4c8"), k);
    }
    if (led.current) {
      led.current.color.set(request ? ACCENT : "#5f6b7a");
      led.current.emissive.set(request ? ACCENT : "#4a5665");
      led.current.emissiveIntensity = request ? 1.4 + pulse * 1.2 : 0.5;
    }
  });

  const inside = (r, x, y) => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;

  /* What is under the pointer: an option, the video pane, or the download
     chip. The pane and the chip are only there when there is a cut to watch,
     and neither is a decision - watching something is not answering for it. */
  const hit = (e) => {
    if (!request || !e.uv) return null;
    const x = e.uv.x * AW;
    const y = (1 - e.uv.y) * AH;

    const rects = buttonRects(request.options.length);
    const i = rects.findIndex((r) => inside(r, x, y));
    if (i !== -1) return { kind: "option", index: i };
    if (source && inside(DOWNLOAD_CHIP, x, y)) return { kind: "download" };
    if (source && inside(VIDEO_PANE, x, y)) return { kind: "video" };
    return null;
  };

  const toggle = () => {
    const element = video.current;
    if (!element) return;
    if (element.paused) element.play().catch(() => {});
    else element.pause();
  };

  return (
    <group {...props}>
      {/* stand */}
      <mesh position={[0, 0.024, 0.03]} castShadow receiveShadow>
        <cylinderGeometry args={[0.36, 0.42, 0.048, 32]} />
        <meshStandardMaterial color="#1e1e25" roughness={0.32} metalness={0.85} />
      </mesh>
      <mesh position={[0, 0.5, 0]} castShadow>
        <boxGeometry args={[0.11, 0.95, 0.055]} />
        <meshStandardMaterial color="#23232b" roughness={0.3} metalness={0.85} />
      </mesh>

      <group position={[0, 1.0 + PANEL_H / 2, 0]}>
        {/* bezel: anodised aluminium, with a chin like a real monitor */}
        <mesh castShadow>
          <boxGeometry args={[PANEL_W + BEZEL * 2, PANEL_H + BEZEL * 2 + 0.05, 0.045]} />
          <meshStandardMaterial color="#26262e" roughness={0.42} metalness={0.9} />
        </mesh>
        {/* the black behind the glass, so the panel has depth even when off */}
        <mesh position={[0, 0.025, 0.0225]}>
          <planeGeometry args={[PANEL_W + 0.006, PANEL_H + 0.006]} />
          <meshBasicMaterial color="#040406" toneMapped={false} />
        </mesh>

        {/* the panel itself */}
        <mesh
          position={[0, 0.025, 0.0235]}
          onClick={(e) => {
            e.stopPropagation();
            const spot = hit(e);
            if (spot === null) onSelect();
            else if (spot.kind === "option") onAnswer(request.options[spot.index].id);
            else if (spot.kind === "video") toggle();
            else if (request.payload?.download_url) {
              // A download is a navigation, not a fetch - the browser saves
              // the file rather than the room holding it in memory.
              window.open(request.payload.download_url, "_blank");
            }
          }}
          onPointerMove={(e) => {
            const spot = hit(e);
            setHovered(spot?.kind === "option" ? spot.index : null);
            setHotSpot(spot && spot.kind !== "option" ? spot.kind : null);
          }}
          onPointerOut={() => {
            setHovered(null);
            setHotSpot(null);
            document.body.style.cursor = "auto";
          }}
          onPointerOver={() => (document.body.style.cursor = "pointer")}
        >
          <planeGeometry args={[PANEL_W, PANEL_H]} />
          <meshBasicMaterial map={texture} toneMapped={false} />
        </mesh>

        {/* glass over the pixels */}
        <mesh position={[0, 0.025, 0.0265]} raycast={() => null}>
          <planeGeometry args={[PANEL_W, PANEL_H]} />
          <meshBasicMaterial
            map={sheen}
            transparent
            opacity={0.5}
            blending={THREE.AdditiveBlending}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>

        {/* standby LED in the chin */}
        <mesh position={[PANEL_W / 2 - 0.09, -PANEL_H / 2 - 0.035, 0.024]}>
          <circleGeometry args={[0.011, 12]} />
          <meshStandardMaterial ref={led} color="#5f6b7a" emissive="#4a5665" emissiveIntensity={0.5} toneMapped={false} />
        </mesh>
      </group>

      <pointLight
        ref={spill}
        position={[0, 1.5, 0.55]}
        color="#8fa4c8"
        intensity={0.12}
        distance={7}
        decay={2}
      />
    </group>
  );
}
