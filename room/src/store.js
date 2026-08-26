import { create } from "zustand";
import { AGENTS } from "./sim/agents.js";

const blankAgent = () => ({
  /* idle -> incoming (an email has landed, not opened yet) -> working -> done */
  status: "idle",
  email: null,
  lines: [],
  progress: 0,
});

/* The lights are remembered, and the key is shared with the rest of the app
   (web/templates/base.html). Turning them on in the room and finding them off
   a click later is what makes two surfaces feel like two products. */
const THEME_KEY = "santa-studio-theme";

function savedTheme() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    return saved === "light" || saved === "dark" ? saved : "dark";
  } catch (e) {
    return "dark";
  }
}

export const useStudio = create((set, get) => ({
  theme: savedTheme(),
  toggleTheme: () =>
    set((s) => {
      const theme = s.theme === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(THEME_KEY, theme);
      } catch (e) { /* private window - the room still switches, just forgets */ }
      return { theme };
    }),

  /* Where the camera is pointed. `kind` drives the rig in world/CameraRig.jsx. */
  focus: { kind: "room", id: null },
  focusDesk: (id) => set({ focus: { kind: "desk", id }, interacted: true }),
  focusTable: () => set({ focus: { kind: "table", id: null }, interacted: true }),
  focusApproval: () => set({ focus: { kind: "approval", id: null }, interacted: true }),
  focusBooth: () => set({ focus: { kind: "booth", id: null }, interacted: true }),
  focusBoard: () => set({ focus: { kind: "board", id: null }, interacted: true }),
  focusRack: () => set({ focus: { kind: "rack", id: null }, interacted: true }),
  focusBench: () => set({ focus: { kind: "bench", id: null }, interacted: true }),
  focusEntrance: () => set({ focus: { kind: "entrance", id: null } }),
  backToRoom: () => set({ focus: { kind: "room", id: null }, interacted: true }),

  /* Auto-rotate runs until the user first touches the scene, then never again. */
  interacted: false,
  markInteracted: () => {
    if (!get().interacted) set({ interacted: true });
  },

  // The Manager is the state machine, so they are never idle — their screen
  // is the run board from the moment the room opens.
  agents: Object.fromEntries(
    AGENTS.map((a) => [a.id, a.id === "manager" ? { ...blankAgent(), status: "working" } : blankAgent()])
  ),
  patchAgent: (id, patch) =>
    set((s) => ({ agents: { ...s.agents, [id]: { ...s.agents[id], ...patch } } })),
  pushLine: (id, line) =>
    set((s) => {
      const a = s.agents[id];
      return { agents: { ...s.agents, [id]: { ...a, lines: [...a.lines, line].slice(-14) } } };
    }),

  /* The one and only channel for anything needing the human. Rendered on the
     free-standing screen beside the Ludo table, never as a toast or modal. */
  approval: null,
  raiseApproval: (req) => set({ approval: req }),
  answerApproval: (choice) => {
    const req = get().approval;
    if (req?.onAnswer) req.onAnswer(choice);
    set({ approval: null });
  },

  /* Coarse pipeline read-out for the room's own status board. */
  stage: "IDLE",
  setStage: (stage) => set({ stage }),

  /* Which run the room is showing, and whether its feed is actually
     connected. "sim" is the demo; the rest are states of a real connection,
     and the HUD says which so a stalled feed cannot be mistaken for a quiet
     pipeline. */
  runId: null,
  connection: "sim",
  setRun: (runId) => set({ runId }),
  setConnection: (connection) => set({ connection }),
}));
