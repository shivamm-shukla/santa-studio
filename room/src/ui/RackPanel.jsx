import { motion } from "framer-motion";
import { MOODS } from "../studio/useVoices.js";

/* Working the rack: pick a voice, hear it, give it a mood, hear that.

   Both takes are on screen together when there is a mood, because the only
   way to judge one is against the other - a filtered clip on its own tells you
   nothing about what the filter did. */

export default function RackPanel({ voices, order, selected, select, applyMood, clearMood, remove, busy, error }) {
  const profile = selected ? voices[selected] : null;

  return (
    <motion.div
      className="rack-panel"
      initial={{ opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 22 }}
    >
      <div className="rack-eyebrow">the rack</div>

      {!order.length ? (
        <p className="rack-say">
          Nothing on the rack yet. Step up to the microphone and record one —
          every video after that is read in it.
        </p>
      ) : (
        <>
          <div className="rack-tabs">
            {order.map((id) => (
              <button
                key={id}
                className={"rack-tab" + (id === selected ? " on" : "")}
                onClick={() => select(id)}
              >
                {voices[id]?.name || "Untitled"}
              </button>
            ))}
          </div>

          {profile && (
            <>
              <div className="rack-takes">
                <div>
                  <span>as recorded</span>
                  <audio controls src={`/api/voice/profiles/${selected}/audio/original`} />
                </div>
                {profile.filtered_path && (
                  <div>
                    <span className="hot">{profile.filter_preset}</span>
                    <audio controls src={`/api/voice/profiles/${selected}/audio/filtered`} />
                  </div>
                )}
              </div>

              <div className="rack-moods">
                {MOODS.map(([preset, note]) => (
                  <button
                    key={preset}
                    className={"rack-mood" + (profile.filter_preset === preset ? " on" : "")}
                    onClick={() => applyMood(selected, preset)}
                    disabled={busy}
                    title={note}
                  >
                    <b>{preset}</b>
                    <span>{note}</span>
                  </button>
                ))}
              </div>

              {error && <p className="rack-say bad">{error}</p>}

              <div className="rack-row">
                {profile.filter_preset && (
                  <button className="chip" onClick={() => clearMood(selected)} disabled={busy}>
                    Back to as recorded
                  </button>
                )}
                <button
                  className="chip danger"
                  onClick={() => {
                    if (confirm(`Take "${profile.name}" off the rack?`)) remove(selected);
                  }}
                  disabled={busy}
                >
                  Remove
                </button>
              </div>
            </>
          )}
        </>
      )}
    </motion.div>
  );
}
