import { AGENTS } from "./agents.js";
import { TASK_EMAILS, WORK_LINES, GATES } from "./feeds.js";
import { applyEvent } from "../net/events.js";

/* Walks the real STATE_SEQUENCE from manager.py and narrates it as events.
   It is a stand-in for the backend, not a toy: the ordering, the two approval
   gates and the mid-run disputed-claim call are the ones the state machine
   actually has. */

const STAGES = AGENTS.filter((a) => a.state);

const wait = (ms, signal) =>
  new Promise((resolve, reject) => {
    const id = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(id);
      reject(new DOMException("stopped", "AbortError"));
    });
  });

export function startSimulation(store, { speed = 1 } = {}) {
  const ctrl = new AbortController();
  const { signal } = ctrl;
  const emit = (e) => applyEvent(store, e);

  const gate = (key) =>
    new Promise((resolve, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("stopped", "AbortError")));
      emit({
        type: "gate",
        gate: GATES[key],
        resolve: (choice) => resolve(choice),
      });
    });

  (async () => {
    try {
      await wait(1600 / speed, signal);
      emit({ type: "stage", state: "TOPIC_SELECTION" });

      for (const agent of STAGES) {
        emit({ type: "stage", state: agent.state });
        emit({ type: "assign", agent: agent.id, email: TASK_EMAILS[agent.id] });

        // The email sits unopened for a beat — long enough that if you're
        // watching that desk you see it land before they start typing.
        await wait(3200 / speed, signal);
        emit({ type: "start", agent: agent.id });

        const lines = WORK_LINES[agent.id] ?? [];
        for (let i = 0; i < lines.length; i++) {
          await wait((900 + Math.random() * 700) / speed, signal);
          emit({
            type: "line",
            agent: agent.id,
            text: lines[i],
            progress: (i + 1) / lines.length,
          });
        }
        await wait(900 / speed, signal);
        emit({ type: "finish", agent: agent.id });

        // Fact-check raises its disputed claim before handing over.
        if (agent.id === "factcheck") {
          const choice = await gate("factcheck");
          emit({ type: "close" });
          emit({
            type: "line",
            agent: "factcheck",
            text: choice === "cut" ? "claim removed from the brief" : "claim kept, hedged in the script",
            progress: 1,
          });
          await wait(900 / speed, signal);
        }

        // "Is the video good?" sits between shorts and thumbnails, exactly
        // where AWAITING_APPROVAL sits in the real sequence.
        if (agent.id === "shorts") {
          emit({ type: "stage", state: "AWAITING_APPROVAL" });
          const choice = await gate("video");
          emit({ type: "close" });
          if (choice === "regenerate") {
            emit({ type: "assign", agent: "assembler", email: {
              from: "Manager",
              subject: "Re-run — assembly",
              preview: "The cut came back from review. Rebuild the timeline and re-render.",
            } });
            await wait(2600 / speed, signal);
            emit({ type: "start", agent: "assembler" });
            for (const text of ["rebuilding timeline", "re-rendering 1080p"]) {
              await wait(1400 / speed, signal);
              emit({ type: "line", agent: "assembler", text, progress: 1 });
            }
            emit({ type: "finish", agent: "assembler" });
          }
          await wait(900 / speed, signal);
        }

        if (agent.id === "thumbnail") {
          emit({ type: "stage", state: "AWAITING_PUBLISH" });
          let choice = await gate("publish");
          emit({ type: "close" });
          // Holding doesn't end the run, it parks it on the gate — same as the
          // real state machine — so the screen keeps asking until you answer.
          while (choice === "hold") {
            await wait(3000 / speed, signal);
            choice = await gate("publish");
            emit({ type: "close" });
          }
          await wait(700 / speed, signal);
        }
      }

      emit({ type: "stage", state: "DONE" });
    } catch (err) {
      if (err.name !== "AbortError") throw err;
    }
  })();

  return () => ctrl.abort();
}
