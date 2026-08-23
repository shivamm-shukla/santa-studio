import { AnimatePresence, motion } from "framer-motion";
import { useStudio } from "../store.js";
import { AGENTS } from "../sim/agents.js";
import { YOU, AI } from "../ludo/useLudoGame.js";

/* Deliberately thin. The room does the talking: agent work lives on agent
   screens and decisions live on the approval screen, so the only things left
   for flat UI are the lights, the way back, and the dice you're holding. */

const nameOf = (id) => AGENTS.find((a) => a.id === id)?.name ?? id;

const FEED_LABEL = {
  sim: "demo run",
  connecting: "connecting",
  live: "live",
  reconnecting: "reconnecting",
  offline: "no feed",
};

const FEED_TITLE = {
  sim: "Simulated pipeline — pass ?run=<id> or ?start=<niche> to watch a real one",
  connecting: "Attaching to the run",
  live: "Streaming from the pipeline",
  reconnecting: "Connection dropped, retrying",
  offline: "Not connected to a run",
};

export default function Hud({ ludo }) {
  const theme = useStudio((s) => s.theme);
  const toggleTheme = useStudio((s) => s.toggleTheme);
  const focus = useStudio((s) => s.focus);
  const interacted = useStudio((s) => s.interacted);
  const stage = useStudio((s) => s.stage);
  const connection = useStudio((s) => s.connection);
  const approval = useStudio((s) => s.approval);
  const backToRoom = useStudio((s) => s.backToRoom);
  const focusApproval = useStudio((s) => s.focusApproval);

  const atTable = focus.kind === "table";

  return (
    <div className="hud">
      <header className="hud-bar">
        <div className="brand">
          <div className="eyebrow">Santa Studio</div>
          <h1>The Room</h1>
        </div>
        <div className="hud-right">
          <span className="stage-chip" title="Pipeline state">
            <i className="dot" />
            {stage}
          </span>
          {/* Where these events come from. A simulated run and a stalled feed
              both look like a quiet room otherwise. */}
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
                Decision waiting — take me to the screen
              </motion.button>
            )}
          </AnimatePresence>
          {focus.kind !== "room" && (
            <button className="chip" onClick={backToRoom}>
              ← Back to the room
            </button>
          )}
          <button className="chip chip-solid" onClick={toggleTheme}>
            {theme === "light" ? "Lights off" : "Lights on"}
          </button>
        </div>
      </header>

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
