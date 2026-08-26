import { useCallback, useEffect, useState } from "react";

/* Every voice this studio has, and the four things you can do to one.

   All of it goes through the same endpoints the voice studio page uses, so a
   mood applied at the rack and a mood applied on that page are the same
   operation on the same profile - there is one truth on disk and two ways to
   reach it. */

export default function useVoices() {
  const [voices, setVoices] = useState({});
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const response = await fetch("/api/voice/profiles");
      if (!response.ok) throw new Error("Could not read the rack.");
      const all = await response.json();
      setVoices(all);
      // Keep whatever was selected if it still exists, otherwise take the
      // first - a rack with something on it should never look empty.
      setSelected((current) => (current && all[current] ? current : Object.keys(all)[0] ?? null));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const act = useCallback(
    async (request) => {
      setBusy(true);
      setError("");
      try {
        const response = await request();
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          throw new Error(detail.detail || "That did not work.");
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

  const applyMood = useCallback(
    (id, preset) =>
      act(() =>
        fetch(`/api/voice/profiles/${id}/filter`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ preset }),
        })
      ),
    [act]
  );

  const clearMood = useCallback(
    (id) => act(() => fetch(`/api/voice/profiles/${id}/filter`, { method: "DELETE" })),
    [act]
  );

  const remove = useCallback(
    (id) => act(() => fetch(`/api/voice/profiles/${id}`, { method: "DELETE" })),
    [act]
  );

  return {
    voices,
    order: Object.keys(voices),
    selected,
    select: setSelected,
    applyMood,
    clearMood,
    remove,
    refresh,
    busy,
    error,
  };
}

/* The moods, and what each one actually does - so they are not six buttons
   with weather names on them. Kept in step with providers/voice/filters.py. */
export const MOODS = [
  ["natural", "Levelled, nothing else"],
  ["warm", "Fuller low-mids"],
  ["deep", "Down two semitones"],
  ["bright", "Up two semitones"],
  ["energetic", "Compressed and lifted"],
  ["calm", "Softened and slowed"],
];
