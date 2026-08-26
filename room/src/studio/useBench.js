import { useCallback, useEffect, useRef, useState } from "react";

/* The cutting bench: a finished video in, ranked vertical clips out.

   Cutting is a job rather than a request - it reads the video, transcribes it,
   scores every candidate moment - so it is started, polled, and only then does
   a project exist. That shape is the whole reason this is a hook: the panel
   should be able to say "still cutting" without knowing how the work is run.

   Every call is the one the clips page already makes. Nothing new was added to
   the backend for this; it was all reachable and only ever reachable from
   another page. */

const POLL_MS = 1200;

export default function useBench() {
  const [sources, setSources] = useState([]);       // finished runs to cut from
  const [projects, setProjects] = useState([]);     // benches already cut
  const [project, setProject] = useState(null);     // the one on the bench
  const [selected, setSelected] = useState(null);
  const [platforms, setPlatforms] = useState([]);
  const [status, setStatus] = useState("idle");     // idle | cutting | ready | failed
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const polling = useRef(null);

  useEffect(() => {
    fetch("/api/clips/platforms").then((r) => (r.ok ? r.json() : [])).then(setPlatforms).catch(() => {});
    fetch("/api/clips").then((r) => (r.ok ? r.json() : [])).then(setProjects).catch(() => {});
    // Only finished runs can be cut: a run still assembling has no video yet.
    fetch("/api/runs/finished")
      .then((r) => (r.ok ? r.json() : []))
      .then(setSources)
      .catch(() => {});
  }, []);

  useEffect(() => () => clearInterval(polling.current), []);

  const open = useCallback(async (projectId) => {
    setNote("");
    try {
      const response = await fetch(`/api/clips/${projectId}`);
      if (!response.ok) throw new Error("That bench is gone.");
      const data = await response.json();
      setProject(data);
      setSelected(data.selected_clip_id || data.candidates?.[0]?.clip_id || null);
      setStatus("ready");
    } catch (e) {
      setNote(e.message);
      setStatus("failed");
    }
  }, []);

  const cut = useCallback(
    async ({ sourceType, target, count = 3 }) => {
      if (!target) return;
      setStatus("cutting");
      setNote("Reading the video and listening to it…");

      try {
        const response = await fetch("/api/clips", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_type: sourceType,
            source_target: target,
            target_count: count,
            render_previews: true,
          }),
        });
        if (!response.ok) throw new Error("The bench would not take it.");
        const { job_id: jobId } = await response.json();

        clearInterval(polling.current);
        polling.current = setInterval(async () => {
          try {
            const job = await (await fetch(`/api/clips/jobs/${jobId}`)).json();
            if (job.status === "done" && job.project_id) {
              clearInterval(polling.current);
              await open(job.project_id);
            } else if (job.status === "failed") {
              clearInterval(polling.current);
              setStatus("failed");
              setNote(job.error || "Cutting failed.");
            }
          } catch (e) { /* a dropped poll is not a failure; the next one retries */ }
        }, POLL_MS);
      } catch (e) {
        setStatus("failed");
        setNote(e.message);
      }
    },
    [open]
  );

  const bundle = useCallback(
    async (chosen) => {
      if (!project) return;
      setBusy(true);
      setNote("Rendering it for each platform…");
      try {
        const response = await fetch(`/api/clips/${project.project_id}/bundle`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ platforms: chosen?.length ? chosen : null }),
        });
        if (!response.ok) throw new Error("Could not render those.");
        await open(project.project_id);
        setNote("");
      } catch (e) {
        setNote(e.message);
      } finally {
        setBusy(false);
      }
    },
    [project, open]
  );

  const clip = project?.candidates?.find((c) => c.clip_id === selected) ?? null;

  return {
    sources, projects, project, clip, selected, select: setSelected,
    platforms, status, note, busy, cut, open, bundle,
  };
}
