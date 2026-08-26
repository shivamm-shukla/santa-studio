import { useCallback, useEffect, useRef, useState } from "react";

/* The cutting bench, which is a whole product on one screen.

   A video comes in - from a finished run, a file, or a YouTube link - and
   ranked vertical clips come out, to be rendered for each platform and then
   kept, downloaded, or put out. Everything a clip needs after it exists is
   here too, because walking to another surface to publish something you just
   cut is the seam this is meant not to have.

   Cutting is a job rather than a request: it downloads, transcribes and scores
   before a project exists at all. So it is started, polled, and only then
   opened. That shape is the reason this is a hook - the screen can say "still
   cutting" without knowing how the work is run.

   Every call here is one the clips API already offered. */

const POLL_MS = 1200;

export default function useBench() {
  const [sources, setSources] = useState([]);       // finished runs to cut from
  const [projects, setProjects] = useState([]);     // the library
  const [project, setProject] = useState(null);     // the one on the bench
  const [selected, setSelected] = useState(null);
  const [platforms, setPlatforms] = useState({});
  const [status, setStatus] = useState("idle");     // idle | cutting | ready | failed
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [youtube, setYoutube] = useState(null);
  const [published, setPublished] = useState(null);
  const polling = useRef(null);

  const loadLibrary = useCallback(() => {
    fetch("/api/clips").then((r) => (r.ok ? r.json() : [])).then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    fetch("/api/clips/platforms").then((r) => (r.ok ? r.json() : {})).then(setPlatforms).catch(() => {});
    // Only finished runs can be cut: a run still assembling has no video yet.
    fetch("/api/runs/finished").then((r) => (r.ok ? r.json() : [])).then(setSources).catch(() => {});
    fetch("/api/publish/youtube/status").then((r) => (r.ok ? r.json() : null)).then(setYoutube).catch(() => {});
    loadLibrary();
  }, [loadLibrary]);

  useEffect(() => () => clearInterval(polling.current), []);

  const open = useCallback(async (projectId) => {
    setNote("");
    setPublished(null);
    try {
      const response = await fetch(`/api/clips/${projectId}`);
      if (!response.ok) throw new Error("That project is gone.");
      const data = await response.json();
      setProject(data);
      setSelected(data.selected_clip_id || data.candidates?.[0]?.clip_id || null);
      setStatus("ready");
    } catch (e) {
      setNote(e.message);
      setStatus("failed");
    }
  }, []);

  const close = useCallback(() => {
    setProject(null);
    setSelected(null);
    setStatus("idle");
    setNote("");
    setPublished(null);
    loadLibrary();
  }, [loadLibrary]);

  /* One way in for all three sources. A file is stored first and then cut from
     its path, so an upload and a link differ only in what `target` is. */
  const cut = useCallback(
    async ({ sourceType, target, file, count = 3 }) => {
      setStatus("cutting");
      setPublished(null);

      try {
        let source = target;
        if (file) {
          setNote(`Uploading ${file.name}…`);
          const form = new FormData();
          form.append("file", file);
          const up = await fetch("/api/clips/upload", { method: "POST", body: form });
          if (!up.ok) throw new Error("That file would not upload.");
          source = (await up.json()).path;
        }
        if (!source) throw new Error("Nothing to cut.");

        setNote("Reading the video and listening to it…");
        const response = await fetch("/api/clips", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_type: sourceType,
            source_target: source,
            target_count: count,
            render_previews: true,
          }),
        });
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          throw new Error(detail.detail || "The bench would not take it.");
        }
        const { job_id: jobId } = await response.json();

        clearInterval(polling.current);
        polling.current = setInterval(async () => {
          try {
            const job = await (await fetch(`/api/clips/jobs/${jobId}`)).json();
            if (job.detail) setNote(job.detail);
            if (job.status === "done" && job.project_id) {
              clearInterval(polling.current);
              await open(job.project_id);
              loadLibrary();
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
    [open, loadLibrary]
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

  /* Publishing. `when` is a local datetime-local string; YouTube wants RFC3339
     in UTC, and will only schedule a video that is private until then. */
  const publish = useCallback(
    async ({ clipId, title, description, tags, privacy = "private", when = "", dryRun = false }) => {
      if (!project || !clipId) return;
      setBusy(true);
      setPublished(null);
      setNote(when ? "Scheduling it…" : "Uploading to YouTube…");
      try {
        const response = await fetch(`/api/clips/${project.project_id}/publish`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            clip_id: clipId,
            title: title || null,
            description: description || "",
            tags: tags?.length ? tags : null,
            privacy_status: privacy,
            publish_at: when ? new Date(when).toISOString() : null,
            dry_run: dryRun,
          }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "That did not go out.");
        setPublished({ ...data, scheduled: !!when, when });
        setNote("");
      } catch (e) {
        setNote(e.message);
      } finally {
        setBusy(false);
      }
    },
    [project]
  );

  const clip = project?.candidates?.find((c) => c.clip_id === selected) ?? null;

  return {
    sources, projects, project, clip, selected, select: setSelected,
    platforms, status, note, busy, youtube, published,
    cut, open, close, bundle, publish, loadLibrary,
  };
}
