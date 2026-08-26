import {
  BENCH_POS, BENCH_ROT, BOARD_POS, BOARD_ROT, BOOTH_POS, DOOR_ANGLE,
  RACK_POS, RACK_ROT, deskAngle, screenPos,
} from "./layout.js";

/* A shot list, so the studio can be filmed rather than screen-recorded.

   Every pose here is the same {target, az, pol, dist} the rig already speaks,
   which means a move between two of them is a real camera move: change dist
   and it dollies, change az and it orbits, change pol and it cranes. Holding
   the target and swinging az is the shot a drone flies round a building.

   The whole film is a pure function of time. That matters more than it looks:
   frames are captured one at a time by a headless browser that renders far
   slower than real time, so nothing can depend on how long a frame took. Ask
   for t = 12.5 and you get exactly the same frame every run.

   `ease` is per shot. Cuts are hard where the edit wants a cut; within a shot
   the movement is eased at both ends the way a shoulder or a gimbal does. */

const easeInOut = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
const easeOut = (x) => 1 - Math.pow(1 - x, 3);
const linear = (x) => x;

const pose = (target, az, pol, dist) => ({ target, az, pol, dist });

/* Standing in the doorway, looking in. */
const DOOR_VIEW = pose([0, 1.2, 0], DOOR_ANGLE, 0.11, 11.2);

const SHOTS = [
  {
    // 1. The push in. Wide from the door, moving toward the middle of the
    //    room while barely turning - the establishing shot.
    name: "arrive",
    seconds: 3.0,
    ease: easeOut,
    from: DOOR_VIEW,
    to: pose([0, 1.15, 0], DOOR_ANGLE - 0.18, 0.16, 10.4),
  },
  {
    // 2. The drone. Up and over, orbiting a third of the way round while
    //    climbing - the shot that says the room is a room.
    name: "drone",
    seconds: 5.4,
    ease: easeInOut,
    from: pose([0, 1.15, 0], DOOR_ANGLE - 0.18, 0.16, 10.4),
    to: pose([0, 1.0, 0], DOOR_ANGLE - 2.5, 0.72, 13.2),
  },
  {
    // 3. Descent onto a desk. The crane comes down out of the orbit and
    //    finds one screen, which is where the work actually is.
    name: "desk",
    seconds: 3.0,
    ease: easeInOut,
    from: pose([0, 1.0, 0], DOOR_ANGLE - 2.5, 0.72, 13.2),
    to: pose(screenPos(2), deskAngle(2) + 0.42, 0.36, 1.15),
  },
  {
    // 4. A slow push along the desk. Nearly still, so the screen can be read.
    name: "read",
    seconds: 1.8,
    ease: linear,
    from: pose(screenPos(2), deskAngle(2) + 0.42, 0.36, 1.15),
    to: pose(screenPos(2), deskAngle(2) + 0.26, 0.30, 0.92),
  },
  {
    // 5. Cut to the board, arriving on a small orbit rather than parked.
    name: "board",
    seconds: 2.6,
    ease: easeOut,
    from: pose(BOARD_POS, BOARD_ROT + 0.62, 0.16, 4.4),
    to: pose(BOARD_POS, BOARD_ROT + 0.06, 0.07, 2.7),
  },
  {
    // 6. The television, same move the other way.
    name: "bench",
    seconds: 2.8,
    ease: easeOut,
    from: pose(BENCH_POS, BENCH_ROT - 0.66, 0.18, 5.0),
    to: pose(BENCH_POS, BENCH_ROT - 0.05, 0.06, 3.2),
  },
  {
    // 7. The voice rack.
    name: "rack",
    seconds: 2.2,
    ease: easeOut,
    from: pose(RACK_POS, RACK_ROT + 0.5, 0.16, 3.4),
    to: pose(RACK_POS, RACK_ROT + 0.04, 0.06, 2.0),
  },
  {
    // 8. Through the door into the booth, on one continuous move. This is
    //    the shot the room was built for - you can walk into the thing.
    name: "enter-booth",
    seconds: 3.6,
    ease: easeInOut,
    from: pose([BOOTH_POS[0], 1.3, BOOTH_POS[2]], DOOR_ANGLE + Math.PI, 0.10, 7.6),
    to: pose([BOOTH_POS[0], 1.28, BOOTH_POS[2]], DOOR_ANGLE + Math.PI + 0.30, 0.06, 1.5),
  },
  {
    // 9. Round the microphone.
    name: "mic",
    seconds: 2.4,
    ease: easeInOut,
    from: pose([BOOTH_POS[0], 1.28, BOOTH_POS[2]], DOOR_ANGLE + Math.PI + 0.30, 0.06, 1.5),
    to: pose([BOOTH_POS[0], 1.24, BOOTH_POS[2]], DOOR_ANGLE + Math.PI - 0.55, 0.14, 1.25),
  },
  {
    // 10. Pull all the way out, back through the door and up. The last thing
    //     you see is the whole studio, which is the thing being sold.
    name: "leave",
    seconds: 3.8,
    ease: easeInOut,
    from: pose([0, 1.2, 0], DOOR_ANGLE, 0.12, 8.0),
    to: pose([0, 1.0, 0], DOOR_ANGLE + 1.15, 0.62, 19.5),
  },
];

/* Where each shot starts on the timeline, and how long the film runs. */
export const CUTS = SHOTS.reduce(
  (acc, shot) => [...acc, acc[acc.length - 1] + shot.seconds],
  [0]
);
export const FILM_SECONDS = CUTS[CUTS.length - 1];
export const FILM_SHOTS = SHOTS;

const mix = (a, b, k) => a + (b - a) * k;

/** The camera pose at time `t`, and which shot it belongs to. */
export function filmPose(t) {
  const time = Math.max(0, Math.min(t, FILM_SECONDS - 0.001));
  let i = 0;
  while (i < SHOTS.length - 1 && time >= CUTS[i + 1]) i += 1;

  const shot = SHOTS[i];
  const k = shot.ease((time - CUTS[i]) / shot.seconds);

  return {
    shot: shot.name,
    index: i,
    // How far into this shot we are, for anything that wants to fade on a cut.
    within: (time - CUTS[i]) / shot.seconds,
    target: [
      mix(shot.from.target[0], shot.to.target[0], k),
      mix(shot.from.target[1], shot.to.target[1], k),
      mix(shot.from.target[2], shot.to.target[2], k),
    ],
    az: mix(shot.from.az, shot.to.az, k),
    pol: mix(shot.from.pol, shot.to.pol, k),
    dist: mix(shot.from.dist, shot.to.dist, k),
  };
}

/* Which place the room should be lit and focused for during each shot, so the
   screens that shot is about are the ones that are awake. */
export const SHOT_FOCUS = {
  arrive: { kind: "room", id: null },
  drone: { kind: "room", id: null },
  desk: { kind: "desk", id: 2 },
  read: { kind: "desk", id: 2 },
  board: { kind: "board", id: null },
  bench: { kind: "bench", id: null },
  rack: { kind: "rack", id: null },
  "enter-booth": { kind: "booth", id: null },
  mic: { kind: "booth", id: null },
  leave: { kind: "room", id: null },
};

/* The lights, as a beat rather than a setting.

   The reel opens on the studio dark - lit by its own screens, which is what
   the place actually looks like when it is working - and the room fills in
   during the drone shot. Both states are in the film because both are real,
   and the moment one becomes the other is the shot people stop scrolling for.
   Returns 0 for off, 1 for on, easing across the middle of shot two. */
const LIGHTS_FROM = 4.6;
const LIGHTS_TO = 7.4;

export function filmLights(t) {
  if (t <= LIGHTS_FROM) return 0;
  if (t >= LIGHTS_TO) return 1;
  const k = (t - LIGHTS_FROM) / (LIGHTS_TO - LIGHTS_FROM);
  return k * k * (3 - 2 * k);   // smoothstep: a dimmer being turned, not a switch
}
