import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { MIN_SECONDS } from "../studio/useRecorder.js";

/* The only flat thing the booth needs: the words, and the two buttons. It sits
   at the bottom of the screen while you are standing at the microphone and is
   gone the moment you walk away, like every other panel in the room. */

function Meter({ level }) {
  const bar = useRef(null);

  useEffect(() => {
    let frame;
    const paint = () => {
      if (bar.current) {
        const loud = Math.min(1, (level?.current ?? 0) * 5.5);
        bar.current.style.width = `${Math.round(loud * 100)}%`;
      }
      frame = requestAnimationFrame(paint);
    };
    frame = requestAnimationFrame(paint);
    return () => cancelAnimationFrame(frame);
  }, [level]);

  return (
    <div className="booth-meter">
      <i ref={bar} style={{ width: "0%" }} />
    </div>
  );
}

function timecode(seconds) {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

export default function BoothPanel({ mic, onDone }) {
  const { status, seconds, clip, error, connect, start, stop, again, enough, level } = mic;
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

  /* While the microphone is live, this says so from wherever you happen to be
     looking.

     It used to appear only once there was a take to name, on the grounds that
     the clock and the level were already on the screen in the booth. They are
     - on the wall to your right, which is not where you are looking when you
     are facing a microphone and talking into it. So there was no way to tell
     whether the thing was recording, and the button that would have stopped it
     did nothing until eight seconds had passed. */
  if (status === "recording" || status === "ready" || status === "denied") {
    return (
      <motion.div
        className="booth-panel"
        initial={{ opacity: 0, y: 22 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 22 }}
      >
        {status === "denied" ? (
          <>
            <div className="booth-eyebrow bad">microphone</div>
            <p className="booth-say bad">{error || "No microphone was available."}</p>
            <div className="booth-row">
              <button className="roll" onClick={connect}>Try again</button>
            </div>
          </>
        ) : status === "ready" ? (
          <>
            <div className="booth-eyebrow">microphone is on</div>
            <p className="booth-say">
              Say a few sentences the way you would narrate them. {MIN_SECONDS} seconds is
              enough; longer is better.
            </p>
            <div className="booth-row">
              <button className="roll" onClick={start}>Start recording</button>
            </div>
          </>
        ) : (
          <>
            <div className="booth-eyebrow rec">recording</div>
            <h3 className="booth-clock">{timecode(seconds)}</h3>
            <Meter level={level} />
            <p className="booth-say">
              {enough
                ? "That is enough to clone from. Stop whenever you like."
                : `Keep going - ${Math.max(0, Math.ceil(MIN_SECONDS - seconds))}s more for a usable clone.`}
            </p>
            <div className="booth-row">
              <button className="roll" onClick={stop}>Stop</button>
            </div>
          </>
        )}
      </motion.div>
    );
  }

  /* Naming a take needs a keyboard, so this step was always flat. */
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
          <div className={enough ? "booth-eyebrow" : "booth-eyebrow bad"}>
            {enough ? "keep this take?" : "that one was too short"}
          </div>
          {!enough && (
            <p className="booth-say bad">
              A clone needs about {MIN_SECONDS} seconds and this is {timecode(seconds)}.
              Listen back if you like, then go again.
            </p>
          )}
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
            <button className="roll" onClick={keep} disabled={saving || !enough}>
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
