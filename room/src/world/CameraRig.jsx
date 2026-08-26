import { useEffect, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { cameraPose, fitDistance } from "./layout.js";
import { filmPose } from "./film.js";

/* Shared with the click handlers: a drag that happens to end on a desk must
   not also count as clicking that desk. */
export const pointer = { dragged: false };

const damp = (cur, goal, lambda, dt) => cur + (goal - cur) * (1 - Math.exp(-lambda * dt));

export default function CameraRig({ focus, interacted, onInteract }) {
  const { camera, gl } = useThree();
  const goal = useRef(cameraPose({ kind: "room" }));
  const cur = useRef({ ...goal.current, target: new THREE.Vector3(...goal.current.target) });
  const look = useRef(new THREE.Vector3());

  useEffect(() => {
    const pose = cameraPose(focus);
    // Keep the shortest way round, so a focus never spins the camera 350°.
    let az = pose.az;
    while (az - cur.current.az > Math.PI) az -= Math.PI * 2;
    while (az - cur.current.az < -Math.PI) az += Math.PI * 2;
    goal.current = { ...pose, az };
  }, [focus.kind, focus.id]);

  useEffect(() => {
    const el = gl.domElement;
    let down = false;
    let lx = 0;
    let ly = 0;

    const onDown = (e) => {
      down = true;
      pointer.dragged = false;
      lx = e.clientX;
      ly = e.clientY;
    };
    const onMove = (e) => {
      if (!down) return;
      const dx = e.clientX - lx;
      const dy = e.clientY - ly;
      lx = e.clientX;
      ly = e.clientY;
      if (Math.abs(dx) + Math.abs(dy) > 3) {
        pointer.dragged = true;
        onInteract();
      }
      goal.current.az -= dx * 0.005;
      goal.current.pol = THREE.MathUtils.clamp(goal.current.pol + dy * 0.004, -0.08, 1.15);
    };
    const onUp = () => {
      down = false;
      // let the click event that follows see the flag, then clear it
      setTimeout(() => (pointer.dragged = false), 0);
    };
    /* Zoom, from anywhere over the room - including over a screen.

       This used to be bound to the canvas alone, which was fine until the
       screens started running actual software: the app sits over the canvas,
       so the wheel never reached the camera and the one place you most want
       to lean in was the one place you could not. Now it is bound to the
       window, and gives way only when the pointer is over something that can
       genuinely still scroll in that direction - a long clip list keeps its
       own wheel, everything else moves the camera. */
    const canScroll = (node, delta) => {
      for (let el = node; el && el !== document.body; el = el.parentElement) {
        const style = getComputedStyle(el);
        if (!/(auto|scroll)/.test(style.overflowY)) continue;
        const room = el.scrollHeight - el.clientHeight;
        if (room <= 1) continue;
        if (delta > 0 && el.scrollTop < room - 1) return true;
        if (delta < 0 && el.scrollTop > 1) return true;
      }
      return false;
    };

    const onWheel = (e) => {
      if (canScroll(e.target, e.deltaY)) return;
      e.preventDefault();
      const g = goal.current;
      g.dist = THREE.MathUtils.clamp(g.dist + e.deltaY * 0.0045 * g.dist, g.min, g.max);
      onInteract();
    };

    el.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      el.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("wheel", onWheel);
    };
  }, [gl, onInteract]);

  useFrame((_, dt) => {
    if (import.meta.env.DEV) window.__rig = { cur: cur.current, goal: goal.current, cam: camera };

    /* Filming. The camera is put exactly where the shot list says it is at
       window.__filmT, with no damping in the way - the easing is in the shot
       and a spring on top of it would soften every move into the same one.
       Nothing here depends on how long the frame took, which is what lets a
       browser that renders at two frames a second still produce 30fps. */
    if (window.__filmT !== undefined) {
      const shot = filmPose(window.__filmT);
      const cp = Math.cos(shot.pol);
      camera.position.set(
        shot.target[0] + Math.sin(shot.az) * cp * shot.dist,
        shot.target[1] + Math.sin(shot.pol) * shot.dist,
        shot.target[2] + Math.cos(shot.az) * cp * shot.dist
      );
      camera.position.y = Math.max(0.35, camera.position.y);
      look.current.set(shot.target[0], shot.target[1], shot.target[2]);
      camera.lookAt(look.current);
      return;
    }

    const g = goal.current;
    const c = cur.current;
    // Slow drift on load so the room introduces itself; stops for good the
    // moment the user touches anything.
    if (!interacted && focus.kind === "room") g.az += dt * 0.045;

    /* If you are at a screen, the near end of the zoom is wherever that
       screen exactly fills this window - so the same gesture ends the same
       way on any display, rather than stopping short on a wide one and
       overflowing on a tall one. Recomputed each frame because the window can
       be resized underneath it. */
    const fit = fitDistance(focus.kind, camera, camera.aspect);
    if (fit) {
      g.min = fit;
      if (g.dist < fit) g.dist = fit;
    }

    const step = Math.min(dt, 0.1);
    c.az = damp(c.az, g.az, 4.2, step);
    c.pol = damp(c.pol, g.pol, 4.2, step);
    c.dist = damp(c.dist, g.dist, 4.2, step);
    c.target.x = damp(c.target.x, g.target[0], 4.2, step);
    c.target.y = damp(c.target.y, g.target[1], 4.2, step);
    c.target.z = damp(c.target.z, g.target[2], 4.2, step);

    const cp = Math.cos(c.pol);
    camera.position.set(
      c.target.x + Math.sin(c.az) * cp * c.dist,
      c.target.y + Math.sin(c.pol) * c.dist,
      c.target.z + Math.cos(c.az) * cp * c.dist
    );
    camera.position.y = Math.max(0.4, camera.position.y);
    look.current.copy(c.target);
    camera.lookAt(look.current);
  });

  return null;
}
