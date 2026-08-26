import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { listVoices } from "../net/liveSource.js";

/* Writing the brief. The board behind it shows what has been decided; this is
   where you decide it, and the button at the end is the one that actually
   starts the run.

   It posts to the same endpoint every other front end uses, and the room then
   attaches to the run it gets back - so commissioning and watching are one
   continuous thing rather than a form on one page and a feed on another. */

export default function BoardPanel({ brief, setBrief, onStart, starting, error, live }) {
  const [voices, setVoices] = useState({});

  useEffect(() => {
    listVoices().then(setVoices);
  }, []);

  function setField(key, value) {
    setBrief((current) => ({ ...current, [key]: value }));
  }

  function setUrl(index, value) {
    setBrief((current) => {
      const urls = [...current.referenceUrls];
      urls[index] = value;
      return { ...current, referenceUrls: urls };
    });
  }

  if (live) {
    return (
      <motion.div
        className="board-panel"
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 22 }}
      >
        <div className="board-eyebrow">commissioned</div>
        <p className="board-say">
          The studio has it. Watch the desks — work lands on them in order, and
          anything that needs you comes up on the screen by the table.
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      className="board-panel"
      initial={{ opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 22 }}
    >
      <div className="board-eyebrow">commission a video</div>

      <div className="board-grid">
        <label>
          <span>Niche</span>
          <input
            value={brief.niche}
            onChange={(e) => setField("niche", e.target.value)}
            placeholder="industrial history"
          />
        </label>

        <label>
          <span>Topic <i>optional</i></span>
          <input
            value={brief.topic}
            onChange={(e) => setField("topic", e.target.value)}
            placeholder="leave empty and it finds one"
          />
        </label>

        <label className="wide">
          <span>Reference videos or channels <i>structure and pacing only</i></span>
          {brief.referenceUrls.map((url, i) => (
            <input
              key={i}
              value={url}
              onChange={(e) => setUrl(i, e.target.value)}
              placeholder="https://youtube.com/…"
            />
          ))}
          <button
            type="button"
            className="board-add"
            onClick={() => setField("referenceUrls", [...brief.referenceUrls, ""])}
          >
            + another
          </button>
        </label>

        <label>
          <span>Voice</span>
          <select
            value={brief.voiceProfileId || ""}
            onChange={(e) => {
              const id = e.target.value;
              setBrief((current) => ({
                ...current,
                voiceProfileId: id || null,
                voiceName: id ? voices[id]?.name : "",
              }));
            }}
          >
            <option value="">the default voice</option>
            {Object.entries(voices).map(([id, profile]) => (
              <option key={id} value={id}>{profile.name}</option>
            ))}
          </select>
        </label>

        <label>
          <span>Minutes</span>
          <input
            type="number"
            min="1"
            value={brief.minutes}
            onChange={(e) => setField("minutes", Number(e.target.value) || 1)}
          />
        </label>

        <label className="wide">
          <span>Review</span>
          <div className="board-seg">
            {[
              ["autonomous", "Run it through"],
              ["checkpoints", "Stop at checkpoints"],
            ].map(([value, text]) => (
              <button
                key={value}
                type="button"
                className={brief.reviewMode === value ? "on" : ""}
                onClick={() => setField("reviewMode", value)}
              >
                {text}
              </button>
            ))}
          </div>
        </label>
      </div>

      {error && <p className="board-say bad">{error}</p>}

      <div className="board-row">
        <button className="roll" onClick={onStart} disabled={starting || !brief.niche.trim()}>
          {starting ? "Handing it over…" : "Hand it to the studio"}
        </button>
      </div>
    </motion.div>
  );
}
