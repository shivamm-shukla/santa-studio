/* A complete, standard Ludo ruleset. No rendering, no React, no randomness
   except roll() — so the whole game can be exercised from a script.

   Board model (the real one, not a loop):
     - 15x15 grid, four 6x6 yards, a 52-cell shared ring, and per-player home
       lanes of 5 cells leading into the centre.
     - A token's position is a *relative* step count from its own start square:
         -1        still in the yard
         0..50     on the shared ring (51 cells travelled)
         51..55    the player's own home lane
         56        home (the centre triangle)
       Relative counts are what make "you must roll exactly" fall out for free:
       any move past 56 simply isn't legal. */

/* The ring, in (row, col), clockwise from the top-left player's start square.
   Consecutive cells turn the corner of the centre square diagonally, which is
   how the track runs on a physical board. */
export const RING = [
  [6, 1], [6, 2], [6, 3], [6, 4], [6, 5],
  [5, 6], [4, 6], [3, 6], [2, 6], [1, 6], [0, 6],
  [0, 7], [0, 8],
  [1, 8], [2, 8], [3, 8], [4, 8], [5, 8],
  [6, 9], [6, 10], [6, 11], [6, 12], [6, 13], [6, 14],
  [7, 14], [8, 14],
  [8, 13], [8, 12], [8, 11], [8, 10], [8, 9],
  [9, 8], [10, 8], [11, 8], [12, 8], [13, 8], [14, 8],
  [14, 7], [14, 6],
  [13, 6], [12, 6], [11, 6], [10, 6], [9, 6],
  [8, 5], [8, 4], [8, 3], [8, 2], [8, 1], [8, 0],
  [7, 0], [6, 0],
];

export const RING_LEN = 52;
export const LANE_LEN = 5;      // home-lane cells before the centre
export const HOME = 51 + LANE_LEN; // 56: exact count required to finish
export const TOKENS = 4;

/* The four seats. Two are used in this build; the other two are here so the
   board is genuinely the standard one and a 4-player game is a config change. */
export const SEATS = {
  red: {
    id: "red", start: 0, color: "#E2483D", corner: "top-left",
    lane: [[7, 1], [7, 2], [7, 3], [7, 4], [7, 5]],
    yard: [[1.6, 1.6], [1.6, 3.4], [3.4, 1.6], [3.4, 3.4]],
  },
  green: {
    id: "green", start: 13, color: "#37A85B", corner: "top-right",
    lane: [[1, 7], [2, 7], [3, 7], [4, 7], [5, 7]],
    yard: [[1.6, 10.6], [1.6, 12.4], [3.4, 10.6], [3.4, 12.4]],
  },
  yellow: {
    id: "yellow", start: 26, color: "#E8B62C", corner: "bottom-right",
    lane: [[7, 13], [7, 12], [7, 11], [7, 10], [7, 9]],
    yard: [[10.6, 10.6], [10.6, 12.4], [12.4, 10.6], [12.4, 12.4]],
  },
  blue: {
    id: "blue", start: 39, color: "#2E7FD4", corner: "bottom-left",
    lane: [[13, 7], [12, 7], [11, 7], [10, 7], [9, 7]],
    yard: [[10.6, 1.6], [10.6, 3.4], [12.4, 1.6], [12.4, 3.4]],
  },
};

/* Start squares plus the four stars. Tokens sharing one of these are safe,
   opposing or not. */
export const SAFE = new Set([0, 8, 13, 21, 26, 34, 39, 47]);

export const isSafe = (abs) => SAFE.has(abs);

/** Absolute ring index for a player's relative position (ring positions only). */
export function absOf(seat, rel) {
  return (SEATS[seat].start + rel) % RING_LEN;
}

/** Where a token physically sits, in grid coordinates. */
export function cellOf(seat, rel, tokenIndex) {
  const s = SEATS[seat];
  if (rel < 0) return { kind: "yard", row: s.yard[tokenIndex][0], col: s.yard[tokenIndex][1] };
  if (rel <= 50) {
    const [row, col] = RING[absOf(seat, rel)];
    return { kind: "ring", row, col, abs: absOf(seat, rel) };
  }
  if (rel < HOME) {
    const [row, col] = s.lane[rel - 51];
    return { kind: "lane", row, col };
  }
  if (rel >= HOME) {
    // Finished tokens rest in the centre, nudged toward their own corner so
    // four of them don't stack into one blob.
    const dr = s.corner.startsWith("top") ? -0.42 : 0.42;
    const dc = s.corner.endsWith("left") ? -0.42 : 0.42;
    return { kind: "home", row: 7 + dr + (tokenIndex % 2) * dc * 0.5, col: 7 + dc };
  }
  // Anything else is not a position on this board. Park it in the yard rather
  // than letting a bad value read as "finished" in the middle of the table.
  return { kind: "yard", row: s.yard[tokenIndex][0], col: s.yard[tokenIndex][1] };
}

export const roll = () => 1 + Math.floor(Math.random() * 6);

export function createGame(seats = ["red", "yellow"]) {
  return {
    seats,
    tokens: Object.fromEntries(seats.map((s) => [s, Array(TOKENS).fill(-1)])),
    turn: seats[0],
    die: null,
    sixStreak: 0,
    winner: null,
  };
}

/** Every token index this player may legally move with this die. */
export function legalMoves(game, seat, die) {
  const mine = game.tokens[seat];
  const moves = [];
  for (let i = 0; i < TOKENS; i++) {
    const rel = mine[i];
    if (rel === HOME) continue;                 // already home, never moves
    if (rel < 0) {
      if (die === 6) moves.push(i);             // only a six opens the yard
      continue;
    }
    if (rel + die <= HOME) moves.push(i);       // overshooting the centre is illegal
  }
  return moves;
}

/** Apply a move. Returns a new game plus what the move did. */
export function applyMove(game, seat, tokenIndex, die) {
  const tokens = Object.fromEntries(
    Object.entries(game.tokens).map(([k, v]) => [k, [...v]])
  );
  const from = tokens[seat][tokenIndex];
  const to = from < 0 ? 0 : from + die;
  tokens[seat][tokenIndex] = to;

  const captures = [];
  if (to <= 50) {
    const abs = absOf(seat, to);
    if (!isSafe(abs)) {
      for (const other of game.seats) {
        if (other === seat) continue;
        tokens[other].forEach((rel, i) => {
          if (rel >= 0 && rel <= 50 && absOf(other, rel) === abs) {
            tokens[other][i] = -1;              // straight back to the yard
            captures.push({ seat: other, tokenIndex: i });
          }
        });
      }
    }
  }

  const finished = to === HOME;
  const won = tokens[seat].every((r) => r === HOME);
  const streak = die === 6 ? game.sixStreak + 1 : 0;
  // Standard Ludo: a six repeats your turn, but three in a row forfeits it.
  const extraTurn = !won && die === 6 && streak < 3;
  // The streak belongs to the turn, not to the game: handing it to the next
  // player would eat the extra roll their own six has just earned them.
  const sixStreak = extraTurn ? streak : 0;

  return {
    game: {
      ...game,
      tokens,
      sixStreak,
      winner: won ? seat : game.winner,
      turn: extraTurn ? seat : nextSeat(game, seat),
      die: null,
    },
    from,
    to,
    captures,
    finished,
    won,
    extraTurn,
  };
}

export function nextSeat(game, seat) {
  const i = game.seats.indexOf(seat);
  return game.seats[(i + 1) % game.seats.length];
}

/** Turn passes with no move: three sixes, or nothing legal to play. */
export function passTurn(game, seat) {
  return { ...game, turn: nextSeat(game, seat), die: null, sixStreak: 0 };
}

/* ---- opponent -----------------------------------------------------------
   Not clever, but never silly: take a capture, otherwise finish a token,
   otherwise open the yard on a six, otherwise advance the one closest home. */
export function chooseMove(game, seat, die, moves) {
  if (moves.length === 1) return moves[0];
  const score = (i) => {
    const rel = game.tokens[seat][i];
    const to = rel < 0 ? 0 : rel + die;
    if (to === HOME) return 1000;
    if (to <= 50 && !isSafe(absOf(seat, to))) {
      const abs = absOf(seat, to);
      const hits = game.seats
        .filter((s) => s !== seat)
        .reduce(
          (n, s) =>
            n + game.tokens[s].filter((r) => r >= 0 && r <= 50 && absOf(s, r) === abs).length,
          0
        );
      if (hits) return 900 + hits * 10 + to;
    }
    if (rel < 0) return 500;                    // getting out is nearly always right
    if (to > 50) return 400 + to;               // safe inside the home lane
    return to + (isSafe(absOf(seat, to)) ? 30 : 0);
  };
  return moves.reduce((best, i) => (score(i) > score(best) ? i : best), moves[0]);
}
