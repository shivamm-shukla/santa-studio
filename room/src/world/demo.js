import {
  BENCH_POS, BENCH_ROT, BOARD_POS, BOARD_ROT, BOOTH_POS, DOOR_ANGLE,
  RACK_POS, RACK_ROT, deskAngle, screenPos,
} from "./layout.js";

/* The long shot list: the studio as a place to be shown, not glanced at.

   film.js is thirty seconds and has to keep moving. This is the version for a
   demo film, where there is room to hold on something - so it has the shots
   the short one could not afford: a full turn around the outside, a low pass
   at desk height, a slow rise to the ceiling, and time at each place rather
   than a touch on the way past.

   Same conventions as everywhere else in the room. `az` is the direction from
   the target to the camera. `lights` is what the switch should be doing during
   the shot, because both states are worth showing and the moment one becomes
   the other is worth building to.

   Every shot is a whole number of bars at 128 BPM (1.875s), so the edit can
   cut on the beat without retiming anything.

   Two constraints that are easy to miss. The panels are wider than they look
   through a vertical frame - the horizontal field is the narrow one at 9:16,
   so the 3.2m television needs six metres of distance before the whole set is
   in shot, and every panel pose here is that number rather than a guess.

   And the walls are 4.3 high, so sin(pol) *
   dist has to stay under about 2.4 or the camera climbs over the top of the
   room and half the frame is the black outside it. Every high shot here sits
   just under that line. */

const BAR = 1.875;

const shot = (name, bars, from, to, opts = {}) => ({
  name,
  seconds: bars * BAR,
  from,
  to,
  ease: opts.ease ?? "inOut",
  lights: opts.lights ?? "dark",
  focus: opts.focus ?? { kind: "room", id: null },
});

const pose = (target, az, pol, dist, fov = 48) => ({ target, az, pol, dist, fov });

/* Aim at the height the work is at. A vertical frame pointed at the floor
   is a picture of a carpet with some furniture at the top of it. */
const MIDDLE = [0, 1.35, 0];

export const SHOTS = [
  /* --- arriving, dark ------------------------------------------------- */
  shot(
    // Through the door, low and slow. The room is lit by its own screens.
    "arrive",
    2,
    pose([0, 1.35, 0], DOOR_ANGLE, 0.09, 11.4, 50),
    pose([0, 1.35, 0], DOOR_ANGLE - 0.22, 0.12, 8.7, 50),
    { ease: "out", lights: "dark" }
  ),
  shot(
    // Desk height, drifting past the near desks. Faces lit by their own work.
    "pass",
    2,
    pose([0, 1.20, 0], DOOR_ANGLE - 0.9, 0.04, 7.2, 54),
    pose([0, 1.20, 0], DOOR_ANGLE - 1.7, 0.05, 6.6, 54),
    { ease: "linear", lights: "dark" }
  ),

  /* --- the lights ----------------------------------------------------- */
  shot(
    // The rise. It starts dark at floor level and ends lit near the ceiling,
    // and the switch happens underneath it.
    "raise",
    3,
    pose([0, 1.30, 0], DOOR_ANGLE - 2.2, 0.07, 8.0, 52),
    pose([0, 1.62, 0], DOOR_ANGLE - 3.1, 0.19, 12.2, 54),
    { ease: "inOut", lights: "rising" }
  ),

  /* --- the drone: all the way round ----------------------------------- */
  shot(
    // A full turn, high, lit. This is the shot that says how big the place is
    // and that everything in it is connected.
    "orbit",
    8,
    pose([0, 1.62, 0], DOOR_ANGLE - 3.1, 0.19, 12.6, 54),
    pose([0, 1.55, 0], DOOR_ANGLE - 3.1 - Math.PI * 2, 0.15, 10.8, 54),
    { ease: "linear", lights: "lit" }
  ),
  shot(
    // Dropping out of the turn towards the floor, still moving sideways.
    "descend",
    2,
    pose([0, 1.55, 0], DOOR_ANGLE - 3.3, 0.17, 10.6, 52),
    pose([0, 1.35, 0], DOOR_ANGLE - 4.0, 0.13, 6.8, 52),
    { ease: "inOut", lights: "lit" }
  ),

  /* --- the places ------------------------------------------------------ */
  shot(
    // The board, arriving on an arc rather than parked in front of it.
    "board-in",
    2,
    pose(BOARD_POS, BOARD_ROT + 0.72, 0.15, 7.4, 50),
    pose(BOARD_POS, BOARD_ROT + 0.10, 0.07, 5.4, 50),
    { ease: "out", lights: "lit", focus: { kind: "board", id: null } }
  ),
  shot(
    // Held on the board while the brief is written.
    "board-hold",
    3,
    pose(BOARD_POS, BOARD_ROT + 0.09, 0.06, 5.3, 50),
    pose(BOARD_POS, BOARD_ROT - 0.04, 0.05, 4.9, 50),
    { ease: "linear", lights: "lit", focus: { kind: "board", id: null } }
  ),
  shot(
    // A desk, over the shoulder, close enough to read the screen.
    "desk",
    3,
    pose(screenPos(2), deskAngle(2) + 0.52, 0.38, 1.5, 42),
    pose(screenPos(2), deskAngle(2) + 0.24, 0.30, 1.0, 42),
    { ease: "inOut", lights: "lit", focus: { kind: "desk", id: 2 } }
  ),
  shot(
    // A second desk, from the other side, so the room reads as staffed
    // rather than as one screen filmed twice.
    "desk-two",
    2,
    pose(screenPos(5), deskAngle(5) - 0.48, 0.34, 1.5, 42),
    pose(screenPos(5), deskAngle(5) - 0.20, 0.28, 1.05, 42),
    { ease: "inOut", lights: "lit", focus: { kind: "desk", id: 5 } }
  ),
  shot(
    // The rack of voices.
    "rack",
    3,
    pose(RACK_POS, RACK_ROT + 0.55, 0.14, 4.2, 50),
    pose(RACK_POS, RACK_ROT + 0.03, 0.05, 3.0, 50),
    { ease: "out", lights: "lit", focus: { kind: "rack", id: null } }
  ),
  shot(
    // Out of the room and into the booth, one continuous move through the
    // door - the shot the whole place was built to allow.
    "booth-in",
    4,
    pose([BOOTH_POS[0], 1.3, BOOTH_POS[2]], DOOR_ANGLE + Math.PI, 0.10, 8.2, 50),
    pose([BOOTH_POS[0], 1.28, BOOTH_POS[2]], DOOR_ANGLE + Math.PI + 0.28, 0.06, 1.6, 44),
    { ease: "inOut", lights: "lit", focus: { kind: "booth", id: null } }
  ),
  shot(
    // Around the microphone, held, while the voice plays.
    "mic",
    4,
    pose([BOOTH_POS[0], 1.28, BOOTH_POS[2]], DOOR_ANGLE + Math.PI + 0.30, 0.06, 1.5, 40),
    pose([BOOTH_POS[0], 1.22, BOOTH_POS[2]], DOOR_ANGLE + Math.PI - 0.62, 0.16, 1.3, 40),
    { ease: "inOut", lights: "lit", focus: { kind: "booth", id: null } }
  ),
  shot(
    // The television, arriving wide so the set reads as a set.
    "tv-in",
    2,
    pose(BENCH_POS, BENCH_ROT - 0.70, 0.16, 8.4, 50),
    pose(BENCH_POS, BENCH_ROT - 0.08, 0.06, 6.6, 50),
    { ease: "out", lights: "lit", focus: { kind: "bench", id: null } }
  ),
  shot(
    // Held on it while the app is worked.
    "tv-hold",
    4,
    pose(BENCH_POS, BENCH_ROT - 0.06, 0.055, 6.5, 50),
    pose(BENCH_POS, BENCH_ROT + 0.02, 0.05, 6.1, 50),
    { ease: "linear", lights: "lit", focus: { kind: "bench", id: null } }
  ),

  /* --- leaving --------------------------------------------------------- */
  shot(
    // Back out to the middle, low, turning.
    "back-out",
    2,
    pose([0, 1.45, 0], DOOR_ANGLE + 0.9, 0.09, 6.6, 52),
    pose([0, 1.50, 0], DOOR_ANGLE + 0.2, 0.17, 9.8, 52),
    { ease: "inOut", lights: "lit" }
  ),
  shot(
    // The crane out. Ends above the room looking down, which is the last
    // thing the film should leave you with.
    "crane",
    4,
    pose([0, 1.50, 0], DOOR_ANGLE + 0.2, 0.19, 10.2, 52),
    pose([0, 1.00, 0], DOOR_ANGLE + 1.5, 0.20, 15.5, 54),
    { ease: "inOut", lights: "lit" }
  ),
];

export const CUTS = SHOTS.reduce((acc, s) => [...acc, acc[acc.length - 1] + s.seconds], [0]);
export const TOTAL = CUTS[CUTS.length - 1];

const EASE = {
  linear: (x) => x,
  out: (x) => 1 - Math.pow(1 - x, 3),
  inOut: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
};

const mix = (a, b, k) => a + (b - a) * k;

/** The camera, the lights and the focus at time `t`. */
export function demoAt(t) {
  const time = Math.max(0, Math.min(t, TOTAL - 0.001));
  let i = 0;
  while (i < SHOTS.length - 1 && time >= CUTS[i + 1]) i += 1;

  const s = SHOTS[i];
  const within = (time - CUTS[i]) / s.seconds;
  const k = EASE[s.ease](within);

  /* "rising" is the switch being thrown mid shot rather than between shots:
     the room fills in while the camera is still moving, which is the only way
     that moment reads as one event instead of two. */
  const lights =
    s.lights === "lit" ? 1 : s.lights === "dark" ? 0 : Math.min(1, Math.max(0, (within - 0.22) / 0.42));

  return {
    shot: s.name,
    index: i,
    within,
    lights: lights * lights * (3 - 2 * lights),
    focus: s.focus,
    target: [
      mix(s.from.target[0], s.to.target[0], k),
      mix(s.from.target[1], s.to.target[1], k),
      mix(s.from.target[2], s.to.target[2], k),
    ],
    az: mix(s.from.az, s.to.az, k),
    pol: mix(s.from.pol, s.to.pol, k),
    dist: mix(s.from.dist, s.to.dist, k),
    fov: mix(s.from.fov, s.to.fov, k),
  };
}
