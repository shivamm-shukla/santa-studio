import { useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";

import BoothScene from "./scene.jsx";
import { MIN_SECONDS, useRecorder } from "./useRecorder.js";

/* Standing at the microphone.

   The controls are deliberately few and always in the same place: this is one
   task - say something for long enough, listen back, keep it - and a booth
   with a control surface all over it is a mixing desk, not a booth.

   The floor of MIN_SECONDS is the same one the sample analysis judges against
   (providers/voice/repair.py). There is no ceiling; the clock keeps counting
   past it and the ring simply stays full. */

function timecode(seconds) {
  const whole = Math.floor(seconds);
  return `${String(Math.floor(whole / 60)).padStart(2, "0")}:${String(whole % 60).padStart(2, "0")}`;
}

export default function Booth() {
  const { status, seconds, clip, error, level, connect, start, stop, again, enough } = useRecorder();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(null);
  const [failure, setFailure] = useState("");

  useEffect(() => {
    document.documentElement.dataset.theme = "dark";
  }, []);

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
      setSaved(await response.json());
    } catch (e) {
      setFailure(e.message);
    } finally {
      setSaving(false);
    }
  }

  const live = status === "recording";
  const progress = Math.min(1, seconds / MIN_SECONDS);

  return (
    <>
      <div className="stage">
        <Canvas
          shadows
          camera={{ fov: 55, position: [0, 0.35, 1.5], near: 0.1, far: 40 }}
          dpr={[1, 2]}
        >
          <color attach="background" args={["#08080c"]} />
          <fog attach="fog" args={["#08080c", 4, 14]} />
          <BoothScene level={level} live={live} />
        </Canvas>
      </div>

      <header className="top">
        <span className="wordmark">Santa Studio</span>
        <nav>
          <a href="/">Home</a>
          <a href="/dashboard">Dashboard</a>
          <a href="/voice-studio">All voices</a>
          <a href="/room/">The Room</a>
        </nav>
      </header>

      <div className="console">
        {saved ? (
          <div className="panel">
            <div className="eyebrow">kept</div>
            <h2>{saved.name}</h2>
            <p className="say">
              {saved.score && saved.score.grade
                ? `The recording came out ${saved.score.grade}.`
                : "Saved."}
            </p>
            {saved.score && saved.score.problems && saved.score.problems.length > 0 && (
              <ul className="notes">
                {saved.score.problems.slice(0, 3).map((problem, i) => (
                  <li key={i}>
                    <b>{problem.message}</b>
                    <span>{problem.fix}</span>
                  </li>
                ))}
              </ul>
            )}
            <div className="row">
              <a className="btn primary" href="/voice-studio">Give it a mood</a>
              <button className="btn ghost" onClick={() => { setSaved(null); again(); }}>
                Record another
              </button>
            </div>
          </div>
        ) : (
          <div className="panel">
            {status === "idle" && (
              <>
                <div className="eyebrow">the booth</div>
                <h2>Say something in your own voice.</h2>
                <p className="say">
                  About {MIN_SECONDS} seconds is the floor — {`${MIN_SECONDS * 2}`} or more
                  and it sounds noticeably more like you. Talk the way you would
                  in a video, not the way you would read a card.
                </p>
                <div className="row">
                  <button className="btn primary" onClick={connect}>Turn the mic on</button>
                </div>
              </>
            )}

            {status === "denied" && (
              <>
                <div className="eyebrow bad">no microphone</div>
                <h2>It could not listen.</h2>
                <p className="say">{error}</p>
                <div className="row">
                  <button className="btn primary" onClick={connect}>Try again</button>
                </div>
              </>
            )}

            {(status === "ready" || live) && (
              <>
                <div className={"eyebrow" + (live ? " rec" : "")}>{live ? "recording" : "ready"}</div>
                <h2 className="clock">{timecode(seconds)}</h2>
                <div className="meter" aria-hidden="true">
                  <i style={{ width: `${progress * 100}%` }} />
                  <span className={enough ? "mark done" : "mark"}>{MIN_SECONDS}s</span>
                </div>
                <p className="say">
                  {live
                    ? enough
                      ? "That is enough to work with. Keep going for a better match."
                      : "Keep talking."
                    : "Press when you are ready. The mic in front of you is live."}
                </p>
                <div className="row">
                  {live ? (
                    <button className="btn primary" onClick={stop} disabled={!enough}>
                      {enough ? "Stop" : `Keep going…`}
                    </button>
                  ) : (
                    <button className="btn primary" onClick={start}>Record</button>
                  )}
                </div>
              </>
            )}

            {status === "recorded" && clip && (
              <>
                <div className="eyebrow">listen back</div>
                <h2 className="clock">{timecode(seconds)}</h2>
                <audio className="playback" controls src={clip.url} />
                <input
                  className="name"
                  placeholder="Name this voice (e.g. Main voice)"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
                {failure && <p className="say bad">{failure}</p>}
                <div className="row">
                  <button className="btn primary" onClick={keep} disabled={saving}>
                    {saving ? "Keeping…" : "Keep it"}
                  </button>
                  <button className="btn ghost" onClick={again} disabled={saving}>
                    Do it again
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
