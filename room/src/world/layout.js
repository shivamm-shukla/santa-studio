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

/* The recording room, which is a room and not a corner.

   The booth was first put on the studio floor and it stood in front of a desk
   and hid the person at it - a booth needs its own four walls anyway, which is
   the whole reason real studios have one. So there is a doorway in the wall,
   between two desks where nothing else is, and a room on the other side of it.

   Everything here is derived from the door's angle, so moving the door moves
   the room, the corridor and the camera together and they cannot disagree. */
export const DOOR_ANGLE = deskAngle(6) + Math.PI / AGENTS.length;
export const DOOR_WIDTH = 2.4;
export const DOOR_H = 2.75;
/* The arc the doorway takes out of the wall, as an angle. */
export const DOOR_ARC = 2 * Math.asin(DOOR_WIDTH / 2 / ROOM_R);

export const BOOTH_ROOM = { width: 7.4, depth: 8.2, height: 3.5 };
export const CORRIDOR = 1.6;

/** Straight out through the door: the direction the recording room lies in. */
export const doorDir = [Math.sin(DOOR_ANGLE), Math.cos(DOOR_ANGLE)];

/** Centre of the recording room, in world space. */
export const BOOTH_ROOM_POS = [
  doorDir[0] * (ROOM_R + CORRIDOR + BOOTH_ROOM.depth / 2),
  0,
  doorDir[1] * (ROOM_R + CORRIDOR + BOOTH_ROOM.depth / 2),
];

/* The microphone stands towards the far end, so walking in puts it in front
   of you rather than beside you. */
export const BOOTH_POS = [
  doorDir[0] * (ROOM_R + CORRIDOR + BOOTH_ROOM.depth * 0.72),
  0,
  doorDir[1] * (ROOM_R + CORRIDOR + BOOTH_ROOM.depth * 0.72),
];
export const BOOTH_ROT = DOOR_ANGLE + Math.PI;

/* The board a run is commissioned at. On the wall between two desks, facing
   into the room, so briefing the studio is something you walk up to rather
   than a form on another page. */
export const BOARD_ANGLE = deskAngle(0) + Math.PI / AGENTS.length;
export const BOARD_R = ROOM_R - 0.35;
export const BOARD_POS = [
  Math.sin(BOARD_ANGLE) * BOARD_R,
  1.75,
  Math.cos(BOARD_ANGLE) * BOARD_R,
];
export const BOARD_ROT = BOARD_ANGLE + Math.PI;

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
    // Standing at the microphone, inside the recording room, facing back
    // towards the door you came through.
    return {
      target: [BOOTH_POS[0], 1.3, BOOTH_POS[2]],
      az: DOOR_ANGLE,
      pol: 0.05,
      dist: 1.7,
      min: 0.9,
      max: 6,
    };
  }
  if (focus.kind === "board") {
    // Standing at the board, close enough to read it and to work at it.
    return {
      target: BOARD_POS,
      az: BOARD_ANGLE,
      pol: 0.06,
      dist: 2.6,
      min: 1.4,
      max: 8,
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
