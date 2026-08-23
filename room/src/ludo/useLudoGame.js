import { useCallback, useEffect, useRef, useState } from "react";
import {
  createGame, legalMoves, applyMove, passTurn, chooseMove, roll, HOME, TOKENS,
} from "./engine.js";

export const YOU = "red";
export const AI = "yellow";

const ROLL_MS = 520;

/* Drives a real game of Ludo and, separately, what the board should *look*
   like: `visual` lags `game` while a token is mid-walk, so the move can be
   animated cell by cell without the rules ever seeing a half-applied state. */
export default function useLudoGame({ stepMs = 190 } = {}) {
  // One cell per hop. Slow enough that you can count the squares out loud,
  // which is how you check a move in a real game.
  const STEP_MS = stepMs;
  const gameRef = useRef(createGame([YOU, AI]));
  const [game, setGame] = useState(gameRef.current);
  const [visual, setVisual] = useState(() => ({ [YOU]: Array(TOKENS).fill(-1), [AI]: Array(TOKENS).fill(-1) }));
  const [die, setDie] = useState(null);
  const [phase, setPhase] = useState("await-roll"); // await-roll | rolling | choose | moving | over
  const [legal, setLegal] = useState([]);
  const [moving, setMoving] = useState(null);       // {seat, index} currently hopping
  const [message, setMessage] = useState("Your turn — press R (or hit Roll) to throw.");
  const [log, setLog] = useState([]);

  const timers = useRef([]);
  const after = useCallback((ms, fn) => {
    const id = setTimeout(fn, ms);
    timers.current.push(id);
    return id;
  }, []);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const note = useCallback((line) => setLog((l) => [...l, line].slice(-6)), []);

  const commit = useCallback((next) => {
    gameRef.current = next;
    setGame(next);
  }, []);

  const walk = useCallback(
    (seat, index, from, to, done) => {
      setMoving({ seat, index });
      // Leaving the yard is one hop onto the start square; everything else
      // advances a single cell at a time, exactly as many times as you rolled.
      const stops = from < 0 ? [0] : Array.from({ length: to - from }, (_, i) => from + i + 1);
      let i = 0;
      const tick = () => {
        // Read the stop *now*. React runs the updater later, by which time `i`
        // has already moved on — reading stops[i] inside the closure skipped
        // squares and, on the last step, handed cellOf an undefined position.
        const square = stops[i];
        setVisual((v) => ({ ...v, [seat]: v[seat].map((r, k) => (k === index ? square : r)) }));
        i += 1;
        if (i < stops.length) after(STEP_MS, tick);
        else
          after(STEP_MS, () => {
            setMoving(null);
            done();
          });
      };
      after(STEP_MS, tick);
    },
    [after, STEP_MS]
  );

  const finishTurn = useCallback(
    (res, seat) => {
      commit(res.game);
      setDie(null);
      if (res.won) {
        setPhase("over");
        setMessage(seat === YOU ? "You win. All four home." : "The opponent wins this one.");
        return;
      }
      if (res.extraTurn) {
        setPhase("await-roll");
        setMessage(seat === YOU ? "A six — roll again." : "Opponent rolled a six and goes again.");
      } else {
        setPhase("await-roll");
        setMessage(seat === YOU ? "Opponent's turn." : "Your turn — press R (or hit Roll) to throw.");
      }
    },
    [commit]
  );

  const play = useCallback(
    (seat, index, value) => {
      const res = applyMove(gameRef.current, seat, index, value);
      setPhase("moving");
      walk(seat, index, res.from, res.to, () => {
        setVisual((v) => {
          const next = { ...v };
          for (const c of res.captures) {
            next[c.seat] = next[c.seat].map((r, k) => (k === c.tokenIndex ? -1 : r));
          }
          return next;
        });
        if (res.captures.length)
          note(seat === YOU ? "You sent one of theirs home." : "They sent one of yours home.");
        if (res.finished) note(seat === YOU ? "One of yours is home." : "One of theirs is home.");
        finishTurn(res, seat);
      });
    },
    [walk, finishTurn, note]
  );

  const spin = useCallback(
    (onValue) => {
      setPhase("rolling");
      let n = 0;
      const tick = () => {
        setDie(roll());
        n += 1;
        if (n < 7) after(ROLL_MS / 7, tick);
        else {
          const value = roll();
          setDie(value);
          after(180, () => onValue(value));
        }
      };
      tick();
    },
    [after]
  );

  const doRoll = useCallback(() => {
    if (phase !== "await-roll" || gameRef.current.turn !== YOU || gameRef.current.winner) return;
    spin((value) => {
      const moves = legalMoves(gameRef.current, YOU, value);
      if (!moves.length) {
        // Spelled out rather than silently skipped, so a passed turn never
        // looks like the game ignoring you.
        setPhase("moving");
        setMessage(
          value === 6
            ? "Rolled a 6 but every token is home or blocked — turn passes."
            : `Rolled ${value}. Nothing can legally move — turn passes.`
        );
        after(1200, () => {
          commit(passTurn(gameRef.current, YOU));
          setDie(null);
          setPhase("await-roll");
          setMessage("Opponent's turn.");
        });
        return;
      }
      setLegal(moves);
      setPhase("choose");
      setMessage(`Rolled ${value}. Pick a token — press ${moves.map((m) => m + 1).join(" / ")}, or click it.`);
    });
  }, [phase, spin, after, commit]);

  const pick = useCallback(
    (index) => {
      if (phase !== "choose" || !legal.includes(index)) return;
      setLegal([]);
      play(YOU, index, die);
    },
    [phase, legal, die, play]
  );

  /* The opponent plays itself. */
  useEffect(() => {
    if (phase !== "await-roll" || game.turn !== AI || game.winner) return;
    const id = setTimeout(() => {
      spin((value) => {
        const moves = legalMoves(gameRef.current, AI, value);
        if (!moves.length) {
          setPhase("moving");
          setMessage(`Opponent rolled ${value} and can't move.`);
          setTimeout(() => {
            commit(passTurn(gameRef.current, AI));
            setDie(null);
            setPhase("await-roll");
            setMessage("Your turn — press R (or hit Roll) to throw.");
          }, 1000);
          return;
        }
        play(AI, chooseMove(gameRef.current, AI, value, moves), value);
      });
    }, 750);
    timers.current.push(id);
    return () => clearTimeout(id);
  }, [phase, game.turn, game.winner, spin, play, commit]);

  const reset = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    const fresh = createGame([YOU, AI]);
    commit(fresh);
    setVisual({ [YOU]: Array(TOKENS).fill(-1), [AI]: Array(TOKENS).fill(-1) });
    setDie(null);
    setLegal([]);
    setMoving(null);
    setLog([]);
    setPhase("await-roll");
    setMessage("New game. Your turn — press R (or hit Roll) to throw.");
  }, [commit]);

  const homeCount = (seat) => game.tokens[seat].filter((r) => r === HOME).length;

  return {
    game, visual, die, phase, legal, moving, message, log, stepMs: STEP_MS,
    yourTurn: game.turn === YOU && !game.winner,
    roll: doRoll,
    pick,
    reset,
    homeCount,
  };
}
