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

  const live = status === "recording";
  const progress = Math.min(1, seconds / MIN_SECONDS);

  return (
    <motion.div
      className="booth-panel"
      initial={{ opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 22 }}
    >
      <AnimatePresence mode="wait">
        {saved ? (
          <motion.div key="saved" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div className="booth-eyebrow">kept</div>
            <h3>{saved.name}</h3>
            <p className="booth-say">
              {saved.score?.grade
                ? `The recording came out ${saved.score.grade}.`
                : "Saved."}
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
              <a className="chip" href="/voice-studio">Give it a mood</a>
            </div>
          </motion.div>
        ) : (
          <motion.div key={status} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            {status === "idle" && (
              <>
                <div className="booth-eyebrow">the booth</div>
                <h3>Say something in your own voice.</h3>
                <p className="booth-say">
                  {MIN_SECONDS} seconds is the floor, {MIN_SECONDS * 2} or more sounds
                  noticeably more like you. Talk the way you would in a video.
                </p>
                <div className="booth-row">
                  <button className="roll" onClick={connect}>Turn the mic on</button>
                </div>
              </>
            )}

            {status === "denied" && (
              <>
                <div className="booth-eyebrow bad">no microphone</div>
                <h3>It could not listen.</h3>
                <p className="booth-say">{error}</p>
                <div className="booth-row">
                  <button className="roll" onClick={connect}>Try again</button>
                </div>
              </>
            )}

            {(status === "ready" || live) && (
              <>
                <div className={"booth-eyebrow" + (live ? " rec" : "")}>
                  {live ? "recording" : "ready"}
                </div>
                <h3 className="booth-clock">{timecode(seconds)}</h3>
                <div className="booth-meter" aria-hidden="true">
                  <i style={{ width: `${progress * 100}%` }} />
                </div>
                <p className="booth-say">
                  {live
                    ? enough
                      ? "Enough to work with. Keep going for a closer match."
                      : `Keep talking — ${Math.ceil(MIN_SECONDS - seconds)}s to go.`
                    : "The mic in front of you is live."}
                </p>
                <div className="booth-row">
                  {live ? (
                    <button className="roll" onClick={stop} disabled={!enough}>
                      {enough ? "Stop" : "Keep going…"}
                    </button>
                  ) : (
                    <button className="roll" onClick={start}>Record</button>
                  )}
                </div>
              </>
            )}

            {status === "recorded" && clip && (
              <>
                <div className="booth-eyebrow">listen back</div>
                <h3 className="booth-clock">{timecode(seconds)}</h3>
                <audio className="booth-playback" controls src={clip.url} />
                <input
                  className="booth-name"
                  placeholder="Name this voice"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
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
        )}
      </AnimatePresence>
    </motion.div>
  );
}
