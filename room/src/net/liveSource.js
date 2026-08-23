/* The real pipeline, wired to the room.

   `pipelineSim.js` and this file are interchangeable: both speak the
   vocabulary in events.js and neither knows anything about the scene. The
   difference is only where the events come from — a timer, or a run that is
   actually happening.

   SSE rather than a WebSocket because the room only ever watches. Decisions
   travel the other way as an ordinary POST to the same endpoint every other
   frontend uses, so the gate on the screen beside the table and the button on
   the dashboard resolve a run identically. */

import { applyEvent } from "./events.js";

const json = { "Content-Type": "application/json" };

/** Starts a new run and returns its id. */
export async function startRun({ niche, topic, reviewMode = "autonomous", minutes = 5 }) {
  const res = await fetch("/api/runs", {
    method: "POST",
    headers: json,
    body: JSON.stringify({
      niche,
      user_topic: topic || null,
      review_mode: reviewMode,
      target_length_minutes: minutes,
    }),
  });
  if (!res.ok) throw new Error(`Could not start a run: ${res.status}`);
  return (await res.json()).run_id;
}

/** Answers whichever gate the run is currently paused on. */
export async function answerGate(runId, decision) {
  const res = await fetch(`/api/runs/${runId}/decision`, {
    method: "POST",
    headers: json,
    body: JSON.stringify({ decision }),
  });
  if (!res.ok) throw new Error(`Decision rejected: ${res.status}`);
  return res.json();
}

/* Attaches the room to a run's live feed.

   Returns a disconnect function, so it drops straight into a useEffect.

   EventSource reconnects on its own when a laptop wakes or a proxy drops the
   connection, and the server replays its buffer to every new connection — so
   a reconnect would otherwise re-deliver work the room has already drawn.
   Every event carries a sequence number for exactly that reason: anything
   not newer than what we have already applied is dropped. */
export function connectRun(store, runId, { onStatus } = {}) {
  let lastSeq = 0;
  let closed = false;

  const source = new EventSource(`/api/runs/${runId}/events`);

  source.onopen = () => onStatus?.("live");

  source.onerror = () => {
    // Not fatal: the browser retries by itself. Say so rather than showing
    // the room as connected when it is not.
    if (!closed) onStatus?.("reconnecting");
  };

  source.onmessage = (message) => {
    let event;
    try {
      event = JSON.parse(message.data);
    } catch {
      return;
    }
    if (typeof event.seq === "number") {
      if (event.seq <= lastSeq) return;
      lastSeq = event.seq;
    }
    applyEvent(store, event, {
      onGateAnswer: (choice) => answerGate(runId, choice).catch(() => {}),
    });
  };

  return () => {
    closed = true;
    source.close();
    onStatus?.("offline");
  };
}
