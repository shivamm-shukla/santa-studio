/* The only vocabulary the room understands. Both sources speak it: the
   simulation in sim/pipelineSim.js, and a real run over SSE in liveSource.js.
   The scene knows about neither.

   { type: "stage",  state }                     pipeline entered a state
   { type: "assign", agent, email }              manager sent an agent work
   { type: "start",  agent }                     that agent opened it and began
   { type: "line",   agent, text, progress }     a line of their real output
   { type: "finish", agent }                     stage output accepted
   { type: "error",  agent, text }               that agent failed twice
   { type: "gate",   gate, resolve }             a human decision is required
   { type: "close" }                             gate answered, screen clears
   { type: "done",   video_path }                the run finished

   A gate has to be answerable, and how it is answered differs by source: the
   simulation resolves its own promise, while a real run posts a decision to
   the API. The source supplies `onGateAnswer` and the event carries
   `resolve`; either satisfies the screen. */

export function applyEvent(store, event, { onGateAnswer } = {}) {
  const s = store.getState();
  switch (event.type) {
    case "stage":
      s.setStage(event.state);
      return;
    case "assign":
      s.patchAgent(event.agent, { status: "incoming", email: event.email, lines: [], progress: 0 });
      return;
    case "start":
      s.patchAgent(event.agent, { status: "working", progress: 0 });
      return;
    case "line":
      s.pushLine(event.agent, event.text);
      s.patchAgent(event.agent, { progress: event.progress ?? 0 });
      return;
    case "finish":
      s.patchAgent(event.agent, { status: "done", progress: 1 });
      return;
    case "error":
      // The desk stays lit with the failure on it. A run that halted is
      // something to look at, not something to clear away.
      if (event.agent) {
        s.pushLine(event.agent, `FAILED: ${event.text}`);
        s.patchAgent(event.agent, { status: "failed" });
      }
      return;
    case "gate":
      s.raiseApproval({
        ...event.gate,
        onAnswer: event.resolve ?? onGateAnswer ?? (() => {}),
      });
      return;
    case "close":
      s.raiseApproval(null);
      return;
    case "done":
      s.setStage("DONE");
      s.raiseApproval(null);
      return;
    default:
      return;
  }
}
