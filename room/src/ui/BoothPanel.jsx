import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MIN_SECONDS } from "../studio/useRecorder.js";

/* The only flat thing the booth needs: the words, and the two buttons. It sits
   at the bottom of the screen while you are standing at the microphone and is
   gone the moment you walk away, like every other panel in the room. */

function timecode(seconds) {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

export default function BoothPanel({ mic, onDone }) {
  const { status, seconds, clip, error, connect, start, stop, again, enough } = mic;
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [failure, setFailure] = useState("");

  async function keep() {
    if (!clip) return;
    setSaving(true);
    setFailure("");

    const form = new FormData();
    form.append("name", name.trim() || "My voice");
    form.append("file", clip.blob, "take.webm");

    try {
      const response = await fetch("/api/voice/profiles", { method: "POST", body: form });
      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "That take could not be used.");
      }
      const profile = await response.json();
      setSaved(profile);
      onDone?.(profile);
    } catch (e) {
      setFailure(e.message);
    } finally {
      setSaving(false);
    }
  }

  /* Everything up to this point is on the screen in the booth and on the
     button on the stand. Naming a take needs a keyboard, so this is the one
     step that is still flat - and it only appears when there is something to
     name. */
  if (status !== "recorded" || !clip) return null;

  return (
    <motion.div
      className="booth-panel"
      initial={{ opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 22 }}
    >
      {saved ? (
        <>
          <div className="booth-eyebrow">kept</div>
          <h3>{saved.name}</h3>
          <p className="booth-say">
            {saved.score?.grade ? `The recording came out ${saved.score.grade}.` : "Saved."}
          </p>
          {saved.score?.problems?.length > 0 && (
            <ul className="booth-notes">
              {saved.score.problems.slice(0, 2).map((problem, i) => (
                <li key={i}>
                  <b>{problem.message}</b>
                  <span>{problem.fix}</span>
                </li>
              ))}
            </ul>
          )}
          <div className="booth-row">
            <button className="roll" onClick={() => { setSaved(null); setName(""); again(); }}>
              Record another
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="booth-eyebrow">keep this take?</div>
          <audio className="booth-playback" controls src={clip.url} />
          <input
            className="booth-name"
            placeholder="Name this voice"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          {failure && <p className="booth-say bad">{failure}</p>}
          <div className="booth-row">
            <button className="roll" onClick={keep} disabled={saving}>
              {saving ? "Keeping…" : "Keep it"}
            </button>
            <button className="chip" onClick={again} disabled={saving}>
              Do it again
            </button>
          </div>
        </>
      )}
    </motion.div>
  );
}
