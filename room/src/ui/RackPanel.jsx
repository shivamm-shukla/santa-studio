import { useRef } from "react";
import { MOODS } from "../studio/useVoices.js";
import { useStudio } from "../store.js";
import { fitToScreen } from "../studio/useScreenRect.js";

/* Working the rack: pick a voice, hear it, give it a mood, hear that.

   Both takes are on screen together when there is a mood, because the only
   way to judge one is against the other - a filtered clip on its own tells you
   nothing about what the filter did. */

/* Adding a sample that already exists as a file.

   The booth is the better path and is offered first everywhere. This is for
   the case the sample checker actually names: a take it has just refused, and
   a cleaner recording sitting on disk. */
function AddFile({ upload, busy }) {
  const input = useRef(null);

  return (
    <div className="rack-row">
      <input
        ref={input}
        type="file"
        accept="audio/*,.wav,.mp3,.m4a,.webm,.ogg,.flac"
        style={{ display: "none" }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload?.(file);
          e.target.value = "";
        }}
      />
      <button className="chip" onClick={() => input.current?.click()} disabled={busy || !upload}>
        {busy ? "Working…" : "Add a file instead"}
      </button>
    </div>
  );
}

export default function RackPanel({ voices, order, selected, select, applyMood, clearMood, remove, upload, busy, error }) {
  const profile = selected ? voices[selected] : null;

  /* Laid into the rack's own screen, the same way the board and the
     television are. See studio/useScreenRect.js. */
  const rect = useStudio((s) => s.screenRects.rack);
  const style = fitToScreen(rect, { w: 768, h: 1125 });
  if (!style) return null;

  return (
    <div
      className="rack-panel"
      style={style}
    >
      <div className="rack-eyebrow">the rack</div>

      {!order.length ? (
        <>
          <p className="rack-say">
            Nothing on the rack yet. Step up to the microphone and record one —
            every video after that is read in it.
          </p>
          <AddFile upload={upload} busy={busy} />
          {error && <p className="rack-say bad">{error}</p>}
        </>
      ) : (
        <>
          <div className="rack-tabs">
            {order.map((id) => (
              <button
                key={id}
                className={"rack-tab" + (id === selected ? " on" : "")}
                onClick={() => select(id)}
              >
                {voices[id]?.name || "Untitled"}
              </button>
            ))}
          </div>

          {profile && (
            <>
              <div className="rack-takes">
                <div>
                  <span>as recorded</span>
                  <audio controls src={`/api/voice/profiles/${selected}/audio/original`} />
                </div>
                {profile.filtered_path && (
                  <div>
                    <span className="hot">{profile.filter_preset}</span>
                    <audio controls src={`/api/voice/profiles/${selected}/audio/filtered`} />
                  </div>
                )}
              </div>

              <div className="rack-moods">
                {MOODS.map(([preset, note]) => (
                  <button
                    key={preset}
                    className={"rack-mood" + (profile.filter_preset === preset ? " on" : "")}
                    onClick={() => applyMood(selected, preset)}
                    disabled={busy}
                    title={note}
                  >
                    <b>{preset}</b>
                    <span>{note}</span>
                  </button>
                ))}
              </div>

              {error && <p className="rack-say bad">{error}</p>}

              <div className="rack-row">
                {profile.filter_preset && (
                  <button className="chip" onClick={() => clearMood(selected)} disabled={busy}>
                    Back to as recorded
                  </button>
                )}
                <button
                  className="chip danger"
                  onClick={() => {
                    if (confirm(`Take "${profile.name}" off the rack?`)) remove(selected);
                  }}
                  disabled={busy}
                >
                  Remove
                </button>
              </div>

              <AddFile upload={upload} busy={busy} />
            </>
          )}
        </>
      )}
    </div>
  );
}
