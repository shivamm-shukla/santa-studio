import { useCallback, useEffect, useState } from "react";

/* Every project the studio has, for the Manager's board.

   The room had no way to show you your own work. There was a flat /dashboard
   page that rendered the same list server-side, which is exactly the split
   this studio exists to close: the room is the product, so what you have made
   belongs on a screen in it rather than on a page beside it. */

export default function useProjects() {
  const [projects, setProjects] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/runs");
      if (!response.ok) throw new Error("Could not read the studio's projects.");
      setProjects(await response.json());
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
    // A run in flight changes state as it goes, and the board is the one
    // screen showing all of them at once.
    const timer = setInterval(refresh, 8000);
    return () => clearInterval(timer);
  }, [refresh]);

  const remove = useCallback(
    async (runId) => {
      setBusy(true);
      setError("");
      try {
        const response = await fetch(`/api/runs/${runId}`, { method: "DELETE" });
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          throw new Error(detail.detail || "That project could not be deleted.");
        }
        await refresh();
      } catch (e) {
        setError(e.message);
      } finally {
        setBusy(false);
      }
    },
    [refresh]
  );

  const resume = useCallback(async (runId) => {
    await fetch(`/api/runs/${runId}/resume`, { method: "POST" }).catch(() => {});
    location.search = `?run=${runId}`;
  }, []);

  return { projects, refresh, remove, resume, busy, error };
}
