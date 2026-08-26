/* The shot list for the laptop sequence, cut to the music.

   128 BPM, so a bar is 1.875 seconds and every cut here lands on one. The
   camera work is meant to read as a camera rather than as an animation: each
   shot is already moving when it starts and still moving when it ends, so
   there is no moment where the picture sits still and asks to be looked at.

   `az` is the direction from the target to the camera, the same convention
   the studio's rig uses. The laptop faces +Z, so the camera lives on that
   side of it and everything here is a variation on that. */

const BAR = 1.875;

const shot = (name, bars, from, to, opts = {}) => ({
  name,
  seconds: bars * BAR,
  from,
  to,
  ease: opts.ease ?? "inOut",
  lights: opts.lights ?? "off",
  // Whether the machine is awake. A dark screen is not the same as no screen:
  // it still catches the room, which is what makes the moment it lights read.
  screen: opts.screen ?? true,
  video: opts.video ?? null,   // where in the landing capture this shot plays
});

const pose = (target, az, pol, dist, fov = 34) => ({ target, az, pol, dist, fov });

/* The screen sits around y = 0.44 with the lid open. */
const SCREEN = [0, 0.44, 0.06];
const DECK = [0, 0.06, 0.34];

/* The distances are worked out rather than guessed. The lid is 1.32 wide and
   the frame is vertical, so the horizontal field is the narrow one: at fov 34
   and 9:16, half the horizontal angle has a tangent of about 0.17, which puts
   "the whole laptop, comfortably in frame" near 4 metres and "close enough to
   read the screen" near 1. Every earlier number here was a tenth of that, and
   every shot was a macro of one corner, and the second pass was still
   inside that distance. */
/* The distances are worked out rather than guessed. The lid is 1.32 wide and
   the frame is vertical, so the horizontal field is the narrow one: at fov 34
   and 9:16, half the horizontal angle has a tangent of about 0.17, which puts
   "the whole laptop, comfortably in frame" past four metres and "close enough
   to read the screen" near two. The first two passes at this were inside that
   distance and every shot was a macro of one corner.

   Eight shots, one to a bar, and the sequence has a hinge in the middle: the
   first four are a dark room and a machine that is asleep, and on the fifth -
   which is where the music drops - the lights come up and the site is on the
   screen. That is the whole pitch in one cut, so it gets the loudest bar. */
export const SHOTS = [
  /* --- asleep: a dark desk, one edge of light on the lid --------------- */
  shot(
    "wake",
    1,
    pose([0, 0.24, 0.10], 0.42, 0.055, 7.20, 32),
    pose([0, 0.26, 0.10], 0.28, 0.075, 5.90, 32),
    { lights: "off", screen: false }
  ),
  shot(
    // Low three-quarter, drifting right. Still nothing on the screen.
    "profile",
    1,
    pose([0, 0.26, 0.08], 1.02, 0.10, 5.60, 34),
    pose([0, 0.28, 0.08], 0.72, 0.07, 4.60, 34),
    { lights: "off", screen: false }
  ),
  shot(
    // Down the barrel, pushing in on the dark glass.
    "approach",
    1,
    pose([0, 0.30, 0.08], 0.02, 0.05, 5.60, 34),
    pose([0, 0.30, 0.08], -0.05, 0.04, 4.20, 34),
    { ease: "out", lights: "off", screen: false }
  ),
  shot(
    // The last dark bar: a slow rise over the closed dark of it, waiting.
    "hold",
    1,
    pose([0, 0.22, 0.16], -0.16, 0.14, 4.30, 34),
    pose([0, 0.26, 0.12], -0.06, 0.30, 3.90, 34),
    { ease: "inOut", lights: "off", screen: false }
  ),

  /* --- the drop: lights up, and the site is on it ---------------------- */
  shot(
    // The frame the kick lands on. Square on, pushing in, everything alight.
    "on",
    1,
    pose([0, 0.30, 0.08], 0.00, 0.045, 5.20, 34),
    pose([0, 0.30, 0.08], -0.04, 0.035, 4.00, 34),
    { ease: "out", lights: "on", video: 0.0 }
  ),
  shot(
    // Round the right shoulder, low, the way you walk past a desk.
    "shoulder",
    1,
    pose([0, 0.28, 0.12], 0.95, 0.13, 5.20, 36),
    pose([0, 0.30, 0.10], 0.42, 0.08, 4.30, 36),
    { lights: "on", video: 2.0 }
  ),
  shot(
    // Over the top of the lid and down onto the deck.
    "over",
    1,
    pose([0, 0.16, 0.30], -0.34, 0.82, 4.60, 40),
    pose([0, 0.20, 0.24], 0.10, 0.42, 3.80, 40),
    { lights: "on", video: 4.0 }
  ),
  shot(
    // Hard in on the screen, drifting sideways. Close enough to read.
    "read",
    1,
    pose([0.14, 0.44, 0.06], -0.22, 0.02, 1.95, 30),
    pose([-0.12, 0.42, 0.06], 0.16, 0.04, 1.72, 30),
    { ease: "linear", lights: "on", video: 6.0 }
  ),
];

/* Act seven: the film the pipeline actually made, playing on the same machine
   the demo opened on. Different job, so different shots - the audience is
   reading a screen now rather than being shown an object, so these are slower,
   longer and closer, and none of them crosses in front of the picture. Twelve
   bars, which is the slot the edit gives it. */
export const FILM_SHOTS = [
  shot(
    // Settle onto the screen from slightly off axis.
    "settle",
    3,
    pose([0, 0.42, 0.06], 0.24, 0.06, 2.60, 32),
    pose([0, 0.43, 0.06], 0.08, 0.045, 2.05, 32),
    { ease: "out", lights: "on", video: 0.0 }
  ),
  shot(
    // Square on and almost still. Let it play.
    "watch",
    4,
    pose([0, 0.43, 0.06], 0.05, 0.04, 2.00, 30),
    pose([0, 0.43, 0.06], -0.02, 0.035, 1.86, 30),
    { ease: "linear", lights: "on", video: 3.0 }
  ),
  shot(
    // A slow drift in, close enough that the captions are legible.
    "closer",
    3,
    pose([0.04, 0.44, 0.06], -0.05, 0.03, 1.86, 30),
    pose([-0.04, 0.43, 0.06], 0.06, 0.035, 1.62, 30),
    { ease: "linear", lights: "on", video: 7.0 }
  ),
  shot(
    // Ease back out, leaving the machine on a desk again.
    "sit-back",
    2,
    pose([0, 0.40, 0.08], 0.10, 0.05, 1.80, 32),
    pose([0, 0.34, 0.10], 0.40, 0.09, 3.40, 34),
    { ease: "inOut", lights: "on", video: 10.0 }
  ),
];

/* ?shots=film swaps the whole list. The recorder picks it for act seven. */
export const ACTIVE =
  typeof location !== "undefined" &&
  new URLSearchParams(location.search).get("shots") === "film"
    ? FILM_SHOTS
    : SHOTS;

export const CUTS = ACTIVE.reduce((acc, s) => [...acc, acc[acc.length - 1] + s.seconds], [0]);
export const TOTAL = CUTS[CUTS.length - 1];

const EASE = {
  linear: (x) => x,
  out: (x) => 1 - Math.pow(1 - x, 3),
  inOut: (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2),
};

const mix = (a, b, k) => a + (b - a) * k;

/** The camera, the lights and the frame of the picture at time `t`. */
export function shotAt(t) {
  const time = Math.max(0, Math.min(t, TOTAL - 0.001));
  let i = 0;
  while (i < ACTIVE.length - 1 && time >= CUTS[i + 1]) i += 1;

  const s = ACTIVE[i];
  const within = (time - CUTS[i]) / s.seconds;
  const k = EASE[s.ease](within);

  return {
    name: s.name,
    index: i,
    within,
    lightsOn: s.lights === "on",
    screenOn: s.screen,
    videoTime: s.video === null ? null : s.video + within * s.seconds,
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
