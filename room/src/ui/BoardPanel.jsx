import { useEffect, useState } from "react";
import { listVoices } from "../net/liveSource.js";
import { useStudio } from "../store.js";
import { fitToScreen } from "../studio/useScreenRect.js";

/* Writing the brief. The board behind it shows what has been decided; this is
   where you decide it, and the button at the end is the one that actually
   starts the run.

   It posts to the same endpoint every other front end uses, and the room then
   attaches to the run it gets back - so commissioning and watching are one
   continuous thing rather than a form on one page and a feed on another. */

/* ---- what the studio has already made ----------------------------------- */

const STATE_WORDS = {
  IDLE: "not started",
  TOPIC_SELECTION: "picking a topic",
  REFERENCE_ANALYSIS: "studying references",
  RESEARCHING: "researching",
  FACT_CHECKING: "checking the claims",
  SCRIPTING: "writing",
  VOICE_GENERATION: "narrating",
  VISUAL_SELECTION: "finding footage",
  VIDEO_ASSEMBLY: "cutting",
  SHORTS_EXTRACTION: "cutting shorts",
  AWAITING_APPROVAL: "waiting for you",
  THUMBNAIL: "thumbnails",
  AWAITING_PUBLISH: "waiting for you",
  YOUTUBE_PUBLISH: "uploading",
  DONE: "finished",
};

function when(timestamp) {
  if (!timestamp) return "";
  const then = new Date(timestamp);
  const mins = Math.round((Date.now() - then.getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function Projects({ projects, remove, resume, busy, error }) {
  if (error) return <p className="board-say bad">{error}</p>;

  if (!projects.length) {
    return (
      <p className="board-say">
        Nothing made yet. Write a brief on the other tab and the studio starts
        on it — every project you commission shows up here.
      </p>
    );
  }

  const done = projects.filter((p) => p.current_state === "DONE").length;

  return (
    <>
      <p className="board-say">
        {projects.length} project{projects.length === 1 ? "" : "s"}
        {done ? `, ${done} finished` : ""}.
      </p>

      <div className="board-projects">
        {projects.map((p) => {
          const waiting = p.current_state?.startsWith("AWAITING");
          const finished = p.current_state === "DONE";
          return (
            <div key={p.run_id} className="board-project">
              <div className="board-project-main">
                <b>{p.topic || "untitled"}</b>
                <span className="board-project-meta">
                  {p.size}
                  {p.last_touched ? ` · ${when(p.last_touched)}` : ""}
                  {p.outputs?.video ? " · video" : ""}
                  {p.outputs?.short ? " · short" : ""}
                </span>
              </div>

              <span
                className={
                  "board-state" +
                  (finished ? " done" : waiting ? " waiting" : p.parked_until ? " parked" : "")
                }
              >
                {p.parked_until && !finished
                  ? "waiting for allowance"
                  : STATE_WORDS[p.current_state] ?? p.current_state}
              </span>

              <div className="board-project-row">
                {!finished && (
                  <button className="chip" onClick={() => resume(p.run_id)} disabled={busy}>
                    {waiting ? "Answer it" : "Carry on"}
                  </button>
                )}
                {finished && (
                  <button
                    className="chip"
                    onClick={() => (location.search = `?run=${p.run_id}`)}
                  >
                    Open
                  </button>
                )}
                <button
                  className="chip danger"
                  onClick={() => {
                    if (confirm(`Delete "${p.topic || "untitled"}" and everything in it?`))
                      remove(p.run_id);
                  }}
                  disabled={busy}
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}

export default function BoardPanel({ brief, setBrief, onStart, starting, error, live, projects }) {
  const [voices, setVoices] = useState({});
  const [tab, setTab] = useState("brief");

  /* Laid into the board's own picture on the wall, so what you are looking at
     is the screen rather than a card floating in front of it. The rectangle
     is measured through the camera every frame - see studio/useScreenRect.js
     - which is what lets it stay put while you walk up to it. */
  const rect = useStudio((s) => s.screenRects.board);
  const style = fitToScreen(rect, { w: 1024, h: 635 });

  useEffect(() => {
    listVoices().then(setVoices);
  }, []);

  // Off screen: nothing to draw. Hooks first, so this never changes their order.
  if (!style) return null;

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
      <div
        className="board-panel"
        style={style}
      >
        <div className="board-eyebrow">commissioned</div>
        <p className="board-say">
          The studio has it. Watch the desks — work lands on them in order, and
          anything that needs you comes up on the screen by the table.
        </p>
      </div>
    );
  }

  if (tab === "studio") {
    return (
      <div className="board-panel" style={style}>
        <div className="board-tabs">
          <button onClick={() => setTab("brief")}>Commission</button>
          <button className="on">The studio</button>
        </div>
        <Projects {...projects} />
      </div>
    );
  }

  return (
    <div
      className="board-panel"
        style={style}
    >
      <div className="board-tabs">
        <button className="on">Commission</button>
        <button onClick={() => setTab("studio")}>
          The studio
          {projects?.projects?.length ? ` (${projects.projects.length})` : ""}
        </button>
      </div>

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
    </div>
  );
}
