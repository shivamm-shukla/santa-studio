import { AGENTS } from "../agents.js";
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

/* Where the recording room's walls are, in the booth group's own coordinates.
   Everything that stands in that room is placed off these rather than off a
   number somebody liked the look of - which is how the foam ended up floating
   a metre clear of the wall it was supposed to be glued to. */
const BOOTH_ALONG = BOOTH_ROOM.depth * 0.72 - BOOTH_ROOM.depth / 2;
export const BOOTH_LOCAL = {
  farZ: -(BOOTH_ROOM.depth / 2 - BOOTH_ALONG),
  doorZ: BOOTH_ROOM.depth / 2 + BOOTH_ALONG,
  sideX: BOOTH_ROOM.width / 2,
  ceilingY: BOOTH_ROOM.height,
};

/* The rack of voices, on the side wall of the recording room. Choosing a mood
   belongs where the recording was made, not on a page somewhere else. */
export const RACK_POS = [
  BOOTH_ROOM_POS[0] + Math.cos(DOOR_ANGLE) * (BOOTH_ROOM.width / 2 - 0.14),
  1.6,
  BOOTH_ROOM_POS[2] - Math.sin(DOOR_ANGLE) * (BOOTH_ROOM.width / 2 - 0.14),
];
export const RACK_ROT = DOOR_ANGLE - Math.PI / 2;

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

/* The cutting bench, on the wall opposite the board: a run is commissioned at
   one end of the room and cut up at the other. */
export const BENCH_ANGLE = deskAngle(3) + Math.PI / AGENTS.length;
export const BENCH_POS = [
  Math.sin(BENCH_ANGLE) * (ROOM_R - 0.35),
  1.7,
  Math.cos(BENCH_ANGLE) * (ROOM_R - 0.35),
];
export const BENCH_ROT = BENCH_ANGLE + Math.PI;

export const APPROVAL_POS = [2.62, 0, -1.42];
export const APPROVAL_PANEL_Y = 1.66;
export const APPROVAL_ROT = Math.atan2(
  SEAT_POS[YOU][0] - APPROVAL_POS[0],
  SEAT_POS[YOU][1] - APPROVAL_POS[2]
);

/* Where to stand to photograph a place, as opposed to where to stand to work
   at it. A working pose is square-on and close, which is right when you are
   using the thing and wrong in a picture - it fills the frame with one panel
   and shows none of the room, so the room looks like it is not there. These
   are three-quarter views from further back, taking in the place and its
   surroundings together. Used by shoot.mjs via ?at=<place>&shot=1. */
export function photoPose(place) {
  /* Each of these is checked against the face it is looking at rather than
     written by eye - the first attempt pointed the board's camera outward
     through the wall and photographed the black back of the panel. The rule
     is the same every time: a panel's front points somewhere, and the camera
     has to be on that side of it, offset for a three-quarter view. */
  if (place === "booth") {
    /* From just inside the door, square enough to take in the treated wall,
       the mic and the screen together. The three-quarter version of this put
       the near wall across two thirds of the frame - a picture of a corner
       rather than of a booth. */
    return {
      target: [BOOTH_POS[0], 1.2, BOOTH_POS[2]],
      az: DOOR_ANGLE + Math.PI + 0.16,
      pol: 0.12,
      dist: 4.4,
      min: 0.4,
      max: 16,
    };
  }
  if (place === "rack") {
    return {
      target: [RACK_POS[0], 1.4, RACK_POS[2]],
      az: RACK_ROT + 0.7,
      pol: 0.14,
      dist: 3.5,
      min: 0.4,
      max: 16,
    };
  }
  if (place === "board") {
    return {
      target: [BOARD_POS[0], 1.55, BOARD_POS[2]],
      az: BOARD_ROT + 0.55,
      pol: 0.14,
      dist: 4.6,
      min: 0.6,
      max: 18,
    };
  }
  if (place === "bench") {
    return {
      target: [BENCH_POS[0], 1.55, BENCH_POS[2]],
      az: BENCH_ROT + 0.55,
      pol: 0.14,
      dist: 4.6,
      min: 0.6,
      max: 18,
    };
  }
  return null;
}

/** Where a place physically is, for anything that needs to point at it. */
export function placePosition(focus) {
  if (focus.kind === "booth") return [BOOTH_POS[0], 1.5, BOOTH_POS[2]];
  if (focus.kind === "rack") return [RACK_POS[0], RACK_POS[1], RACK_POS[2]];
  if (focus.kind === "board") return [BOARD_POS[0], BOARD_POS[1], BOARD_POS[2]];
  if (focus.kind === "bench") return [BENCH_POS[0], BENCH_POS[1], BENCH_POS[2]];
  if (focus.kind === "approval") return [APPROVAL_POS[0], APPROVAL_PANEL_Y, APPROVAL_POS[2]];
  if (focus.kind === "desk") {
    const i = AGENTS.findIndex((a) => a.id === focus.id);
    return i >= 0 ? screenPos(i) : null;
  }
  return null;
}

/* Camera poses. Every one is target + (azimuth, polar, distance), so the same
   orbit-drag and scroll-zoom work wherever you are — focusing somewhere moves
   you there, it doesn't hand you a different set of controls. */
/* The panels that are screens, and how big they are in the room. Used to work
   out how close you can get before one fills the window. */
export const SCREEN_SIZE = {
  bench: [3.2, 1.8],
  board: [2.42, 1.5],
  rack: [1.42, 2.08],
};

/** The closest you can stand to a screen before it overflows the window.

    Zooming in on a screen should end with it filling your display exactly -
    not short of the edges, and not spilling past them, which is what a fixed
    minimum distance gave: it was right on one window and wrong on every other.
    So it is computed from the actual viewport instead. */
export function fitDistance(place, camera, aspect) {
  const size = SCREEN_SIZE[place];
  if (!size || !camera) return null;
  const [w, h] = size;
  const half = Math.tan((camera.fov * Math.PI) / 360);
  // Whichever axis runs out first is the one that decides.
  return Math.max(w / (2 * half * aspect), h / (2 * half));
}

export function cameraPose(focus) {
  if (focus.photo) {
    const pose = photoPose(focus.photo);
    if (pose) return pose;
  }
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
    /* Standing in front of the microphone, between it and the door.

       `az` is the direction from the target *to the camera*, which is the
       thing to get right here: DOOR_ANGLE points out through the door and
       away from the room, so using it put the camera past the mic and into
       the far wall - facing back at a foam panel with the mic behind it.
       The half turn puts the camera on the door side, where you would stand. */
    return {
      target: [BOOTH_POS[0], 1.3, BOOTH_POS[2]],
      az: DOOR_ANGLE + Math.PI,
      pol: 0.05,
      dist: 1.9,
      // Close enough to read the model of the capsule, far enough back to see
      // the whole room and out through its window. The old ceiling of 6 was
      // barely past the far wall, which is why nothing in here could be
      // looked at properly.
      min: 0.35,
      max: 16,
    };
  }
  if (focus.kind === "bench") {
    /* Standing in the room facing the set, not out in the car park behind it.

       `az` is the direction from the target to the camera. The bench is ON the
       wall at BENCH_ANGLE, so that angle points straight out through it: the
       camera was landing at radius 14.25 in a room of radius 12, outside the
       building, looking at the black back of the panel through the wall.
       BENCH_ROT is where the screen faces, which is where a viewer stands. */
    return {
      target: BENCH_POS,
      az: BENCH_ROT,
      pol: 0.06,
      // Far enough back that the set reads as a set - bezel, standby light and
      // the wall it hangs on - rather than as a rectangle of pixels. Close
      // enough, at the near end, that the picture fills the whole window.
      dist: 3.6,
      min: 1.35,
      max: 18,
    };
  }
  if (focus.kind === "rack") {
    /* Standing in the room, facing the rack on its side wall.

       `az` is the direction from the target to the camera, and the rack is ON
       a wall - so the camera has to go towards the middle of the room, not
       away from it. The half turn that looks symmetrical put it 5.76 across a
       room whose half-width is 3.70: outside the wall, looking at the back of
       the geometry, which renders as nothing at all. */
    return {
      target: RACK_POS,
      az: RACK_ROT,
      pol: 0.05,
      dist: 2.0,
      min: 0.45,
      max: 16,
    };
  }
  if (focus.kind === "board") {
    // Standing at the board, close enough to read it and to work at it.
    // BOARD_ROT rather than BOARD_ANGLE for the same reason as the bench: the
    // angle points out through the wall, the rotation points at the reader.
    return {
      target: BOARD_POS,
      az: BOARD_ROT,
      pol: 0.06,
      dist: 2.6,
      min: 1.1,
      max: 18,
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
