import { useCallback, useState } from "react";
import { useStudio } from "../store.js";
import { connectRun, startRun } from "../net/liveSource.js";

/* The brief, and what happens when it is handed over.

   The room could always *watch* a run and never start one: ?start=<niche> in
   the URL was the only way in, which meant commissioning happened on another
   page and you came back here to watch. This closes that loop - the run is
   started from the board and the room attaches to it without a reload. */

const BLANK = {
  niche: "",
  topic: "",
  referenceUrls: [""],
  voiceProfileId: null,
  voiceName: "",
  minutes: 5,
  reviewMode: "autonomous",
};

export default function useCommission() {
  const [brief, setBrief] = useState(BLANK);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [live, setLive] = useState(false);

  const start = useCallback(async () => {
    if (!brief.niche.trim()) return;
    setStarting(true);
    setError("");

    try {
      const runId = await startRun({
        niche: brief.niche.trim(),
        topic: brief.topic.trim(),
        referenceUrls: brief.referenceUrls,
        voiceProfileId: brief.voiceProfileId,
        minutes: brief.minutes,
        reviewMode: brief.reviewMode,
      });

      const store = useStudio.getState();
      store.setRun(runId);
      store.setConnection("connecting");
      connectRun(useStudio, runId, {
        onStatus: (status) => useStudio.getState().setConnection(status),
      });

      // Keep it in the URL, so a reload rejoins this run rather than starting
      // a second one - the same rule ?start= follows.
      const url = new URL(location.href);
      url.searchParams.delete("at");
      url.searchParams.set("run", runId);
      history.replaceState({}, "", url);

      setLive(true);
      // Back to the floor: the work is about to land on the desks, and that is
      // the thing worth looking at.
      store.backToRoom();
    } catch (e) {
      setError(e.message || "The studio could not take it.");
    } finally {
      setStarting(false);
    }
  }, [brief]);

  return { brief, setBrief, start, starting, error, live };
}
