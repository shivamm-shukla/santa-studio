import { useState } from "react";
import { motion } from "framer-motion";

/* Working the bench: choose a finished video, cut it, judge the moments it
   found, render the ones worth keeping.

   Each candidate carries why it was chosen. A ranked list with a number
   against each row tells you the order and nothing about the judgement, and
   the judgement is the part you are checking. */

function clock(seconds) {
  const whole = Math.floor(seconds || 0);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export default function BenchPanel({
  sources, projects, project, clip, selected, select,
  platforms, status, note, busy, cut, open, bundle,
}) {
  const [source, setSource] = useState("");
  const [chosen, setChosen] = useState([]);

  const toggle = (platform) =>
    setChosen((current) =>
      current.includes(platform) ? current.filter((p) => p !== platform) : [...current, platform]
    );

  return (
    <motion.div
      className="bench-panel"
      initial={{ opacity: 0, y: 22 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 22 }}
    >
      <div className="bench-eyebrow">the cutting bench</div>

      {!project && (
        <>
          {sources.length === 0 && projects.length === 0 ? (
            <p className="bench-say">
              Nothing to cut yet. Finish a run and its video lands here.
            </p>
          ) : (
            <>
              {sources.length > 0 && (
                <div className="bench-start">
                  <select value={source} onChange={(e) => setSource(e.target.value)}>
                    <option value="">Choose a finished video…</option>
                    {sources.map((run) => (
                      <option key={run.run_id} value={run.run_id}>
                        {run.topic || run.niche || run.run_id.slice(0, 8)}
                      </option>
                    ))}
                  </select>
                  <button
                    className="roll"
                    disabled={!source || status === "cutting"}
                    onClick={() => cut({ sourceType: "studio_run", target: source })}
                  >
                    {status === "cutting" ? "Cutting…" : "Cut it"}
                  </button>
                </div>
              )}

              {projects.length > 0 && (
                <div className="bench-old">
                  <span>already cut</span>
                  <div className="bench-tabs">
                    {projects.map((p) => (
                      <button key={p.project_id} className="rack-tab" onClick={() => open(p.project_id)}>
                        {p.title || p.project_id.slice(0, 8)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
          {note && <p className={"bench-say" + (status === "failed" ? " bad" : "")}>{note}</p>}
        </>
      )}

      {project && (
        <>
          <div className="bench-head">
            <b>{project.source?.title || "Untitled"}</b>
            <button className="chip" onClick={() => window.location.reload()}>Cut something else</button>
          </div>

          <div className="bench-list">
            {(project.candidates || []).map((candidate) => (
              <button
                key={candidate.clip_id}
                className={"bench-clip" + (candidate.clip_id === selected ? " on" : "")}
                onClick={() => select(candidate.clip_id)}
              >
                <div className="bench-clip-top">
                  <span className="bench-time">{clock(candidate.start_time)}–{clock(candidate.end_time)}</span>
                  <span className="bench-score">{Math.round((candidate.score || 0) * 100)}</span>
                </div>
                <b>{candidate.hook_text || candidate.suggested_title || "Untitled moment"}</b>
                {candidate.reasons?.length > 0 && (
                  <span className="bench-why">{candidate.reasons.slice(0, 2).join(" · ")}</span>
                )}
              </button>
            ))}
          </div>

          {clip && (
            <div className="bench-detail">
              {clip.has_preview && (
                <video
                  className="bench-preview"
                  controls
                  src={`/api/clips/${project.project_id}/preview/${clip.clip_id}`}
                />
              )}

              <div className="bench-platforms">
                {platforms.map((platform) => (
                  <button
                    key={platform}
                    className={"chip-toggle" + (chosen.includes(platform) ? " active" : "")}
                    onClick={() => toggle(platform)}
                  >
                    {platform}
                  </button>
                ))}
              </div>

              <div className="bench-row">
                <button className="roll" onClick={() => bundle(chosen)} disabled={busy}>
                  {busy ? "Rendering…" : chosen.length ? `Render for ${chosen.length}` : "Render for all"}
                </button>
                {Object.entries(clip.downloads || {}).map(([platform, url]) => (
                  <a key={platform} className="chip" href={url}>{platform} ↓</a>
                ))}
              </div>
            </div>
          )}

          {note && <p className={"bench-say" + (status === "failed" ? " bad" : "")}>{note}</p>}
        </>
      )}
    </motion.div>
  );
}
