import { AnimatePresence, motion } from "framer-motion";
import { useStudio } from "../store.js";
import { AGENTS } from "../sim/agents.js";
import { YOU, AI } from "../ludo/useLudoGame.js";
import BoothPanel from "./BoothPanel.jsx";
import BoardPanel from "./BoardPanel.jsx";
import RackPanel from "./RackPanel.jsx";
import BenchPanel from "./BenchPanel.jsx";

/* Deliberately thin. The room does the talking: agent work lives on agent
   screens and decisions live on the approval screen, so the only things left
   for flat UI are the lights, the way back, and the dice you're holding. */

const nameOf = (id) => AGENTS.find((a) => a.id === id)?.name ?? id;

const FEED_LABEL = {
  sim: "nothing running",
  connecting: "connecting",
  live: "live",
  reconnecting: "reconnecting",
  offline: "no feed",
};

const FEED_TITLE = {
  sim: "No run attached — the desks are showing a rehearsal. Commission one to see the real thing.",
  connecting: "Attaching to the run",
  live: "Streaming from the pipeline",
  reconnecting: "Connection dropped, retrying",
  offline: "Not connected to a run",
};

export default function Hud({ ludo, mic, commission, voices, bench, bare }) {
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

  const atTable = focus.kind === "table";

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
        {!interacted && (
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
        {focus.kind === "booth" && <BoothPanel mic={mic} />}
        {focus.kind === "rack" && voices && <RackPanel {...voices} />}
        {focus.kind === "bench" && bench && <BenchPanel {...bench} />}
        {focus.kind === "board" && commission && (
          <BoardPanel
            brief={commission.brief}
            setBrief={commission.setBrief}
            onStart={commission.start}
            starting={commission.starting}
            error={commission.error}
            live={commission.live}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {atTable && (
          <motion.div
            className="ludo-bar"
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 24 }}
          >
            <div className="ludo-score">
              <span className="pip pip-you" /> you {ludo.homeCount(YOU)}/4
              <span className="pip pip-ai" /> opponent {ludo.homeCount(AI)}/4
            </div>

            <div className="ludo-msg">{ludo.message}</div>

            <div className="ludo-controls">
              {ludo.phase === "over" ? (
                <button className="roll" onClick={ludo.reset}>
                  Play again
                </button>
              ) : (
                <>
                  <div className={"die" + (ludo.phase === "rolling" ? " rolling" : "")}>
                    {ludo.die ?? "·"}
                  </div>
                  <button
                    className="roll"
                    onClick={ludo.roll}
                    disabled={!ludo.yourTurn || ludo.phase !== "await-roll"}
                  >
                    Roll <kbd>R</kbd>
                  </button>
                  <div className="tokens">
                    {[0, 1, 2, 3].map((i) => (
                      <button
                        key={i}
                        className={"token" + (ludo.legal.includes(i) ? " live" : "")}
                        disabled={!ludo.legal.includes(i)}
                        onClick={() => ludo.pick(i)}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
            {ludo.log.length > 0 && <div className="ludo-log">{ludo.log[ludo.log.length - 1]}</div>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
