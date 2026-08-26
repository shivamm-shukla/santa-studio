import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

/* The screen on the far wall is a television, and this is what is on it.

   Everything a short needs happens here and nowhere else: bring a video in,
   watch the bench find the moments worth keeping, render each one at the size
   its platform wants, then keep it, take it away, or put it out - now or at a
   time you choose. Three tabs, in the order the work actually happens:

     New      a video in, from a run, a file, or a link
     Library  what has been cut already, and every clip in it
     Publish  the one on the bench, out to YouTube, now or later

   The tabs are always reachable. Coming back from a finished project to start
   another one should not mean reloading the room, which is what it used to. */

const TABS = [
  ["new", "New project"],
  ["library", "Library"],
  ["publish", "Publish"],
];

function clock(seconds) {
  const whole = Math.floor(seconds || 0);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function duration(seconds) {
  const whole = Math.floor(seconds || 0);
  if (whole < 60) return `${whole}s`;
  const mins = Math.floor(whole / 60);
  return mins < 60 ? `${mins} min` : `${Math.floor(mins / 60)}h ${mins % 60}m`;
}

/* ---- bringing a video in ------------------------------------------------ */

function NewProject({ sources, status, note, cut }) {
  const [how, setHow] = useState("studio_run");
  const [run, setRun] = useState("");
  const [link, setLink] = useState("");
  const [file, setFile] = useState(null);
  const picker = useRef();

  const cutting = status === "cutting";
  const ready =
    (how === "studio_run" && run) || (how === "youtube" && link.trim()) || (how === "upload" && file);

  const start = () => {
    if (!ready || cutting) return;
    if (how === "studio_run") cut({ sourceType: "studio_run", target: run });
    else if (how === "youtube") cut({ sourceType: "youtube", target: link.trim() });
    else cut({ sourceType: "upload", file });
  };

  return (
    <div className="tv-body">
      <div className="tv-ways">
        {[
          ["studio_run", "From a run", "A video this studio already made"],
          ["upload", "Upload a file", "Anything on your machine"],
          ["youtube", "From a link", "Paste a YouTube URL"],
        ].map(([id, label, hint]) => (
          <button
            key={id}
            className={"tv-way" + (how === id ? " on" : "")}
            onClick={() => setHow(id)}
            disabled={cutting}
          >
            <b>{label}</b>
            <span>{hint}</span>
          </button>
        ))}
      </div>

      <div className="tv-take">
        {how === "studio_run" &&
          (sources.length ? (
            <select value={run} onChange={(e) => setRun(e.target.value)} disabled={cutting}>
              <option value="">Choose a finished video…</option>
              {sources.map((source) => (
                <option key={source.run_id} value={source.run_id}>
                  {source.topic || source.niche || source.run_id.slice(0, 8)}
                </option>
              ))}
            </select>
          ) : (
            <p className="tv-say">
              No finished runs yet. Commission one at the board, or bring a file instead.
            </p>
          ))}

        {how === "youtube" && (
          <input
            type="url"
            value={link}
            placeholder="https://www.youtube.com/watch?v=…"
            onChange={(e) => setLink(e.target.value)}
            disabled={cutting}
          />
        )}

        {how === "upload" && (
          <button className="tv-drop" onClick={() => picker.current?.click()} disabled={cutting}>
            <input
              ref={picker}
              type="file"
              accept="video/*"
              hidden
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? <b>{file.name}</b> : <span>Choose a video file</span>}
          </button>
        )}
      </div>

      <div className="tv-row">
        <button className="roll" onClick={start} disabled={!ready || cutting}>
          {cutting ? "Working…" : "Find the moments"}
        </button>
        {note && <span className={"tv-note" + (status === "failed" ? " bad" : "")}>{note}</span>}
      </div>

      {cutting && (
        <div className="tv-progress">
          <i />
        </div>
      )}
    </div>
  );
}

/* ---- what has been cut already ------------------------------------------ */

function Library({ projects, project, clip, selected, select, platforms, busy, note, open, close, bundle }) {
  const [chosen, setChosen] = useState([]);
  const names = Object.keys(platforms || {});

  const toggle = (platform) =>
    setChosen((current) =>
      current.includes(platform) ? current.filter((p) => p !== platform) : [...current, platform]
    );

  if (!project) {
    return (
      <div className="tv-body">
        {projects.length === 0 ? (
          <p className="tv-say">Nothing cut yet. Start a project and it will be kept here.</p>
        ) : (
          <div className="tv-shelf">
            {projects.map((entry) => (
              <button key={entry.project_id} className="tv-card" onClick={() => open(entry.project_id)}>
                <span className="tv-card-kind">{entry.source_type?.replace("_", " ") || "video"}</span>
                <b>{entry.title || entry.project_id.slice(0, 8)}</b>
                <span className="tv-card-meta">
                  {entry.candidates} clip{entry.candidates === 1 ? "" : "s"} · {duration(entry.duration)}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="tv-body tv-open">
      <div className="tv-head">
        <b>{project.source?.title || "Untitled"}</b>
        <button className="chip" onClick={close}>← All projects</button>
      </div>

      <div className="tv-split">
        <div className="tv-list">
          {(project.candidates || []).map((candidate) => (
            <button
              key={candidate.clip_id}
              className={"tv-clip" + (candidate.clip_id === selected ? " on" : "")}
              onClick={() => select(candidate.clip_id)}
            >
              <div className="tv-clip-top">
                <span>{clock(candidate.start_time)}–{clock(candidate.end_time)}</span>
                <span className="tv-score">{Math.round((candidate.score || 0) * 100)}</span>
              </div>
              <b>{candidate.hook_text || candidate.suggested_title || "Untitled moment"}</b>
              {candidate.reasons?.length > 0 && (
                <span className="tv-why">{candidate.reasons.slice(0, 2).join(" · ")}</span>
              )}
            </button>
          ))}
        </div>

        {clip && (
          <div className="tv-detail">
            {clip.has_preview ? (
              <video
                className="tv-preview"
                controls
                src={`/api/clips/${project.project_id}/preview/${clip.clip_id}`}
              />
            ) : (
              <p className="tv-say">No preview rendered for this one yet.</p>
            )}

            <div className="tv-chips">
              {names.map((platform) => (
                <button
                  key={platform}
                  className={"chip-toggle" + (chosen.includes(platform) ? " active" : "")}
                  onClick={() => toggle(platform)}
                >
                  {platform.replace("_", " ")}
                </button>
              ))}
            </div>

            <div className="tv-row">
              <button className="roll" onClick={() => bundle(chosen)} disabled={busy}>
                {busy ? "Rendering…" : chosen.length ? `Render for ${chosen.length}` : "Render for all"}
              </button>
              {Object.entries(clip.downloads || {}).map(([platform, url]) => (
                <a key={platform} className="chip" href={url} download>
                  {platform.replace("_", " ")} ↓
                </a>
              ))}
            </div>
            {note && <span className="tv-note">{note}</span>}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---- putting one out ----------------------------------------------------- */

function Publish({ project, clip, youtube, published, busy, note, publish, go }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [when, setWhen] = useState("");
  const [privacy, setPrivacy] = useState("private");

  // The clip's own suggestion is the starting point, not a placeholder you
  // have to retype - but only until you have typed something of your own.
  useEffect(() => {
    setTitle(clip?.suggested_title || clip?.hook_text || "");
  }, [clip?.clip_id]);

  if (!project || !clip) {
    return (
      <div className="tv-body">
        <p className="tv-say">
          Nothing on the bench. Open a project in the library and choose the clip you want to put out.
        </p>
        <button className="chip" onClick={() => go("library")}>Go to the library</button>
      </div>
    );
  }

  const rendered = Object.keys(clip.downloads || {}).length > 0;
  const connected = youtube?.connected;

  return (
    <div className="tv-body tv-publish">
      <div className="tv-split">
        <div className="tv-form">
          <label>
            Title
            <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={100} />
          </label>
          <label>
            Description
            <textarea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <div className="tv-two">
            <label>
              Visibility
              <select value={privacy} onChange={(e) => setPrivacy(e.target.value)} disabled={!!when}>
                <option value="private">Private</option>
                <option value="unlisted">Unlisted</option>
                <option value="public">Public</option>
              </select>
            </label>
            <label>
              Schedule for
              <input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
            </label>
          </div>
          {when && (
            <p className="tv-hint">
              A scheduled video stays private until then — that is YouTube's rule, not ours.
            </p>
          )}
        </div>

        <div className="tv-detail">
          {clip.has_preview && (
            <video
              className="tv-preview"
              controls
              src={`/api/clips/${project.project_id}/preview/${clip.clip_id}`}
            />
          )}

          {!rendered && (
            <p className="tv-note bad">
              This clip has not been rendered yet. Render it in the library first.
            </p>
          )}
          {!connected && (
            <p className="tv-note bad">
              YouTube is not connected{youtube?.detail ? ` — ${youtube.detail}` : ""}. You can still do a
              dry run.
            </p>
          )}

          <div className="tv-row">
            <button
              className="roll"
              disabled={busy || !rendered || !connected}
              onClick={() =>
                publish({ clipId: clip.clip_id, title, description, privacy, when })
              }
            >
              {busy ? "Sending…" : when ? "Schedule it" : "Publish now"}
            </button>
            <button
              className="chip"
              disabled={busy}
              onClick={() =>
                publish({ clipId: clip.clip_id, title, description, privacy, when, dryRun: true })
              }
            >
              Dry run
            </button>
          </div>

          {note && <span className="tv-note bad">{note}</span>}
          {published && (
            <div className="tv-done">
              <b>{published.dry_run ? "Dry run" : published.scheduled ? "Scheduled" : "Published"}</b>
              {published.video_url && (
                <a href={published.video_url} target="_blank" rel="noreferrer">
                  {published.video_url}
                </a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---- the set ------------------------------------------------------------- */

export default function BenchPanel(bench) {
  const [tab, setTab] = useState("new");

  // Finishing a cut is the moment the library becomes the interesting tab.
  useEffect(() => {
    if (bench.status === "ready" && bench.project) setTab("library");
  }, [bench.status, bench.project?.project_id]);

  return (
    <motion.div
      className="tv-panel"
      initial={{ opacity: 0, scale: 0.97, y: 18 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97, y: 18 }}
      transition={{ type: "spring", stiffness: 260, damping: 26 }}
    >
      <div className="tv-bar">
        <div className="tv-brand">
          <span className="tv-dot" />
          Santa Studio <b>Clips</b>
        </div>
        <nav className="tv-tabs">
          {TABS.map(([id, label]) => (
            <button key={id} className={"tv-tab" + (tab === id ? " on" : "")} onClick={() => setTab(id)}>
              {label}
            </button>
          ))}
        </nav>
      </div>

      <AnimatePresence mode="wait">
        <motion.div
          key={tab}
          initial={{ opacity: 0, x: 14 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -14 }}
          transition={{ duration: 0.18 }}
        >
          {tab === "new" && <NewProject {...bench} />}
          {tab === "library" && <Library {...bench} />}
          {tab === "publish" && <Publish {...bench} go={setTab} />}
        </motion.div>
      </AnimatePresence>
    </motion.div>
  );
}
