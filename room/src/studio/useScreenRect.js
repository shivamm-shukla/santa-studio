import { useEffect, useMemo, useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { useStudio } from "../store.js";

/* Where a panel in the room lands on your actual screen, in CSS pixels.

   The screens in this studio run real software, and real software needs text
   fields, file pickers and video elements - none of which a canvas texture can
   hold. So the interface is HTML, and this is what stops that being a cheat:
   the mesh measures itself through the camera every frame and the HTML is laid
   into exactly that rectangle. Walk closer and the app grows with the screen;
   turn away and it goes with it; zoom the browser and nothing comes unstuck,
   because there is no fixed size anywhere in the chain.

   Returns a ref to attach to the screen plane. Writes the rectangle into the
   store under `place`, and clears it the moment the panel is not being used
   or has left the frame. */

const CORNERS = [[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]];

export default function useScreenRect(place, width, height, active) {
  const screen = useRef();
  const last = useRef(null);
  const { camera, size } = useThree();
  const setScreenRect = useStudio((s) => s.setScreenRect);
  const point = useMemo(() => new THREE.Vector3(), []);

  useEffect(() => () => setScreenRect(place, null), [place, setScreenRect]);

  useFrame(() => {
    if (!active || !screen.current) {
      if (last.current) {
        last.current = null;
        setScreenRect(place, null);
      }
      return;
    }

    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    let gone = false;

    for (const [sx, sy] of CORNERS) {
      point.set(sx * width, sy * height, 0);
      screen.current.localToWorld(point);
      // Standing inside the panel is not a view of it.
      if (point.distanceTo(camera.position) < 0.05) gone = true;
      point.project(camera);
      // Past the far plane, or behind the camera entirely.
      if (point.z > 1) gone = true;
      const x = ((point.x + 1) / 2) * size.width;
      const y = ((1 - point.y) / 2) * size.height;
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }

    const rect = gone ? null : { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
    const was = last.current;

    /* Only when it has actually moved. This runs every frame, and every write
       re-renders the whole flat layer - half a pixel of drift is not worth
       that, and a camera that has come to rest should stop writing entirely. */
    const moved =
      !rect !== !was ||
      (rect && was &&
        (Math.abs(rect.x - was.x) > 0.5 || Math.abs(rect.y - was.y) > 0.5 ||
         Math.abs(rect.w - was.w) > 0.5 || Math.abs(rect.h - was.h) > 0.5));

    if (moved) {
      last.current = rect;
      setScreenRect(place, rect);
    }
  });

  return screen;
}

/** Lays a flat panel into one of those rectangles, as one uniform scale.

    The interface is laid out once at a fixed logical size and then scaled to
    fit, exactly the way a picture is. Sizing it in `em` instead looked right
    at rest and wrong in motion: the text grew but the layout reflowed around
    it, so walking towards a screen read as the content zooming rather than as
    the screen coming closer. A single transform cannot reflow, which is why
    this is the version that feels like an object in the room.

    The logical size has the same aspect as the panel in the room, so one
    scale factor serves both axes and nothing is ever stretched. `width` and
    `height` here are that logical size, not the size on screen. */
export function fitToScreen(rect, base) {
  if (!rect) return null;
  return {
    left: 0,
    top: 0,
    width: base.w,
    height: base.h,
    transformOrigin: "0 0",
    transform: `translate(${rect.x}px, ${rect.y}px) scale(${rect.w / base.w})`,
  };
}
