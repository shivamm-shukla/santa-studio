import { AnimatePresence, motion } from "framer-motion";
import { useStudio } from "../store.js";
import { AGENTS } from "../agents.js";
import BoothPanel from "./BoothPanel.jsx";
import BoardPanel from "./BoardPanel.jsx";
import RackPanel from "./RackPanel.jsx";
import BenchPanel from "./BenchPanel.jsx";

/* Deliberately thin. The room does the talking: agent work lives on agent
   screens and decisions live on the approval screen, so the only things left
   for flat UI are the lights, the way back, and the dice you're holding. */

const nameOf = (id) => AGENTS.find((a) => a.id === id)?.name ?? id;

const FEED_LABEL = {
  idle: "nothing running",
  connecting: "connecting",
  live: "live",
  reconnecting: "reconnecting",
  offline: "no feed",
};

const FEED_TITLE = {
  idle: "No run in flight. Write a brief on the board to start one.",
  connecting: "Attaching to the run",
  live: "Streaming from the pipeline",
  reconnecting: "Connection dropped, retrying",
  offline: "Not connected to a run",
};

export default function Hud({ mic, commission, voices, bench, projects, bare }) {
  const theme = useStudio((s) => s.theme);
  const toggleTheme = useStudio((s) => s.toggleTheme);
  const focus = useStudio((s) => s.focus);
  const interacted = useStudio((s) => s.interacted);
  const stage = useStudio((s) => s.stage);
  const connection = useStudio((s) => s.connection);
  const approval = useStudio((s) => s.approval);
  const backToRoom = useStudio((s) => s.backToRoom);
  const focusApproval = useStudio((s) => s.focusApproval);
  const focusBooth = useStudio((s) => s.focusBooth);
  const focusBoard = useStudio((s) => s.focusBoard);
  const focusRack = useStudio((s) => s.focusRack);
  const focusBench = useStudio((s) => s.focusBench);

  return (
    <div className="hud">
      {/* Filming the demo: the panels stay, because they are the software on
          the screens now, but the top bar goes - it is chrome for a person
          using the room, and there is nobody using it in a film. */}
      {!bare && (
        <header className="hud-bar">
          <div className="brand">
            <div className="eyebrow">Santa Studio</div>
            <h1>The Room</h1>
          </div>
          <div className="hud-right">
            {/* Where you can go. Everything else in this bar is status. */}
            <nav className="places">
              <a className="chip" href="/" title="Back to the front door">Home</a>
              {focus.kind !== "board" && (
                <button className="chip" onClick={focusBoard}>Commission</button>
              )}
              {focus.kind !== "booth" && (
                <button className="chip" onClick={focusBooth}>Record</button>
              )}
              {focus.kind !== "rack" && (
                <button className="chip" onClick={focusRack}>Voices</button>
              )}
              {focus.kind !== "bench" && (
                <button className="chip" onClick={focusBench}>Clips</button>
              )}
              {focus.kind !== "room" && (
                <button className="chip" onClick={backToRoom}>← Room</button>
              )}
            </nav>
  
            <span className="stage-chip" title="Pipeline state">
              <i className="dot" />
              {stage}
            </span>
            <span className={"feed-chip feed-" + connection} title={FEED_TITLE[connection]}>
              {FEED_LABEL[connection] ?? connection}
            </span>
  
            <AnimatePresence>
              {approval && focus.kind !== "approval" && (
                <motion.button
                  className="chip chip-alert"
                  initial={{ opacity: 0, y: -6 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  onClick={focusApproval}
                >
                  A decision is waiting
                </motion.button>
              )}
            </AnimatePresence>
  
            <button className="chip chip-solid" onClick={toggleTheme}>
              {theme === "light" ? "Lights off" : "Lights on"}
            </button>
          </div>
        </header>
      )}

      <AnimatePresence>
        {/* The hint teaches a person how to move the camera. In a film the
            camera is already moving and nobody is holding the mouse, so it is
            just a caption nobody asked for across the bottom of the shot. */}
        {!interacted && !bare && (
          <motion.div className="hint" exit={{ opacity: 0 }}>
            Drag to look around · scroll to zoom · click a desk to read over their shoulder ·
            click the table to play
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {focus.kind === "desk" && (
          <motion.div
            className="whoami"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
          >
            Watching <strong>{nameOf(focus.id)}</strong>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {(focus.kind === "booth" || mic?.status === "recording") && (
          <BoothPanel mic={mic} />
        )}
        {focus.kind === "rack" && voices && <RackPanel {...voices} />}
        {focus.kind === "bench" && bench && <BenchPanel {...bench} />}
        {focus.kind === "board" && commission && (
          <BoardPanel
            brief={commission.brief}
            setBrief={commission.setBrief}
            projects={projects}
            onStart={commission.start}
            starting={commission.starting}
            error={commission.error}
            live={commission.live}
          />
        )}
      </AnimatePresence>

    </div>
  );
}
