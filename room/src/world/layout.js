import { AGENTS } from "../sim/agents.js";
import { SEAT_POS } from "../ludo/LudoTable.jsx";
import { YOU } from "../ludo/useLudoGame.js";

/* One place that knows where everything physically is, so the camera and the
   furniture can never disagree about it. */

export const ROOM_R = 12;
export const DESK_R = 8.2;
export const WALL_H = 4.3;

export const deskAngle = (i) => (i / AGENTS.length) * Math.PI * 2;

/** A desk sits on the perimeter with its local +Z aimed at the room's centre. */
export function deskPose(i) {
  const a = deskAngle(i);
  return {
    angle: a,
    position: [Math.sin(a) * DESK_R, 0, Math.cos(a) * DESK_R],
    rotationY: a + Math.PI,
  };
}

/** World position of a desk's laptop panel (local z 0.885, y 1.02). */
export function screenPos(i) {
  const a = deskAngle(i);
  const r = DESK_R - 0.885;
  return [Math.sin(a) * r, 1.02, Math.cos(a) * r];
}

/* The vocal booth. Off the studio floor rather than in the middle of it,
   because that is where a booth goes - you step away from the desks to record.
   Far enough round the perimeter to have its own wall, and angled back into
   the room so walking to it reads as turning a corner. */
export const BOOTH_ANGLE = Math.PI * 0.72;
export const BOOTH_R = DESK_R - 1.9;
export const BOOTH_POS = [
  Math.sin(BOOTH_ANGLE) * BOOTH_R,
  0,
  Math.cos(BOOTH_ANGLE) * BOOTH_R,
];
export const BOOTH_ROT = BOOTH_ANGLE + Math.PI;

export const APPROVAL_POS = [2.62, 0, -1.42];
export const APPROVAL_PANEL_Y = 1.66;
export const APPROVAL_ROT = Math.atan2(
  SEAT_POS[YOU][0] - APPROVAL_POS[0],
  SEAT_POS[YOU][1] - APPROVAL_POS[2]
);

/* Camera poses. Every one is target + (azimuth, polar, distance), so the same
   orbit-drag and scroll-zoom work wherever you are — focusing somewhere moves
   you there, it doesn't hand you a different set of controls. */
export function cameraPose(focus) {
  if (focus.kind === "desk") {
    const i = AGENTS.findIndex((a) => a.id === focus.id);
    const a = deskAngle(i);
    // Close in over the shoulder and high enough to clear their head: near
    // enough that the screen is genuinely readable, which is the whole point
    // of putting the mail on it rather than in a toast.
    return { target: screenPos(i), az: a + 0.4, pol: 0.4, dist: 1.05, min: 0.5, max: 4 };
  }
  if (focus.kind === "table") {
    const [x, z] = SEAT_POS[YOU];
    // Far enough back that your own shoulders sit in the bottom of frame —
    // you are at the table, not hovering over it.
    return { target: [0, 0.92, 0], az: Math.atan2(x, z), pol: 0.47, dist: 5.4, min: 2.6, max: 9 };
  }
  if (focus.kind === "approval") {
    return {
      target: [APPROVAL_POS[0], APPROVAL_PANEL_Y, APPROVAL_POS[2]],
      az: APPROVAL_ROT,
      pol: 0.1,
      dist: 3.1,
      min: 1.8, max: 7,
    };
  }
  if (focus.kind === "booth") {
    // Standing at the microphone: close, level with it, and near enough that
    // the stand is in front of you rather than across the room.
    return {
      target: [BOOTH_POS[0], 1.28, BOOTH_POS[2]],
      az: BOOTH_ROT + Math.PI,
      pol: 0.06,
      dist: 1.5,
      min: 0.8,
      max: 5,
    };
  }
  if (focus.kind === "entrance") {
    // Where you arrive. Wide and low, taking in the whole floor at once,
    // before anything has been chosen.
    return { target: [0, 1.2, 0], az: 2.1, pol: 0.12, dist: 15.5, min: 3.5, max: 24 };
  }
  // Standing at the back of the room, under the ceiling rather than above
  // it — the point is to be inside the place, not to inspect a model of it.
  // Zooming out past the wall still works, and gives a dollhouse view.
  return { target: [0, 1.05, 0], az: 0.55, pol: 0.22, dist: 11.5, min: 3.5, max: 24 };
}
