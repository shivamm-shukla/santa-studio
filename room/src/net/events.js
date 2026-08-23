/* The only vocabulary the room understands. The simulation speaks it today;
   a WebSocket from the FastAPI app is meant to speak the same thing tomorrow,
   so wiring up the real pipeline is a change of source, not of scene.

   { type: "stage",  state }                     pipeline entered a state
   { type: "assign", agent, email }              manager sent an agent work
   { type: "start",  agent }                     that agent opened it and began
   { type: "line",   agent, text, progress }     a line of their real output
   { type: "finish", agent }                     stage output accepted
   { type: "gate",   gate, resolve }             a human decision is required
   { type: "close" }                             gate answered, screen clears */

export function applyEvent(store, event) {
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
    case "gate":
      s.raiseApproval({ ...event.gate, onAnswer: event.resolve });
      return;
    case "close":
      s.raiseApproval(null);
      return;
    default:
      return;
  }
}
