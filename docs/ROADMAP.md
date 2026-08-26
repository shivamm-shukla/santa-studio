# Santa Studio — Roadmap

Goal: a system that takes a topic plus a few reference channel links, learns
their craft, researches deeply, narrates in _your own cloned voice_, edits
itself like a real documentary, and uploads the finished video — with nobody
appearing on camera.

Written 22 Aug 2026. Replaces the former `HANDOFF.md`.

This file is the engineering plan and the record of what each phase delivered.
It is deliberately not rewritten as things change — the phase results below are
what was true when they were written, including where they were later found to
be wrong (§10 exists for exactly that).

**For the current state of anything, read [SPEC.md](SPEC.md) §0.** For how the
system is put together today, read [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 1. Where we are starting from

The pipeline already runs end to end. This roadmap is about quality, not about
getting something working — that part is done, and it is the floor everything
below builds on.

### 1.1 The state machine today

```
IDLE → TOPIC_SELECTION → REFERENCE_ANALYSIS → RESEARCHING → FACT_CHECKING
     → SCRIPTING → VOICE_GENERATION → VISUAL_SELECTION → VIDEO_ASSEMBLY
     → SHORTS_EXTRACTION → [gate: video ok?] → THUMBNAIL
     → [gate: ready to publish?] → YOUTUBE_PUBLISH → DONE
```

Gates are ordinary members of the sequence, so advancing past one is the same
index+1 step as advancing past a work state. Publishing is opt-in: with no
publish provider configured, a run ends at `DONE` holding the finished file
rather than halting on a gate it can never satisfy.

### 1.2 What a run produces

- **Master video** — 16:9 MP4, scaled visuals, ambient bed, burnt-in captions
- **Vertical short** — 9:16 MP4 cropped from the opening hook
- **Thumbnails** — three variants (`bottom-bar`, `left-block`, `center-punch`)
- **Citations** — real encyclopedic URLs for the description
- **Upload** — reachable, but never run against a live account. The Google
  dependencies are in `requirements.txt` and the env vars are in
  `.env.example`; connecting an account (`studio youtube connect`) is what
  turns publishing on, and without one a run ends at `DONE` holding the file.
  What remains unproven is everything on the far side of the OAuth consent
  screen: quota behaviour, and the forced-`private` limit for unverified
  projects. See §11.

Everything above except upload is verified across the front ends: the FastAPI
web app, the Telegram bot and the CLI. (The Streamlit prototype named here
originally has since been deleted; the web app replaced it.) (
predates the web app and is no longer where the work goes; the room, which is
now the fourth front end, did not exist when this was written.)

### 1.3 Invariants not to regress

Phase 0 rewrites storage and splits the renderer, and Phase 1 replaces the voice
provider. Each of these was a real bug that was found and fixed; the rewrites are
in exactly the code paths that could quietly undo them. Full detail is in
`git log`.

- **A missing voice track fails loudly.** `assembler_agent` raises rather than
  shipping a silent video — the silent fallback looked enough like a finished
  video to publish by accident.
- **State writes are atomic** — `.tmp` then `os.replace` — and `load_state`
  filters unknown fields so an older JSON still loads after a schema change.
- **Downloads use unique partial filenames** (`{path}.part.{uuid}`), because
  concurrent scene fetches collided on shared temp names.
- **FFmpeg symlinks are replaced via `os.path.lexists()`**, not `os.path.exists()`,
  so a dangling symlink does not raise `FileExistsError` forever.
- **LLM JSON parsing is staged** — direct parse, then code-fence extract, then
  `JSONDecoder.raw_decode` bracket scan — because a greedy regex broke whenever a
  model wrapped its JSON in prose containing braces.
- **Background run threads catch everything** and write an error status, rather
  than dying silently and leaving the UI spinning forever.

---

## 2. Constraints we are designing against

These five are locked. Every decision below is downstream of them.

| #   | Constraint                | What it means in practice                                                                                                                                  |
| --- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Zero budget**           | Free API tiers, open weights, and local compute only. No step may require a paid key to work.                                                              |
| 2   | **Commercially safe**     | Only MIT / Apache-2.0 / BSD / CC0 / public-domain. This rules out things that are technically better — see §4.1.                                           |
| 3   | **Paid-upgrade-ready**    | Adding money later must be a config change, never a refactor. The existing `providers/` abstraction is the right shape; we extend it, we don't replace it. |
| 4   | **Anyone can install it** | One command, models auto-download, a `doctor` preflight that explains what's missing. Fully documented in the README.                                      |
| 5   | **Both lengths**          | 5–10 min explainers and 10–20 min deep dives from the same pipeline; length stays a parameter.                                                             |

**Non-goal:** we are not building a general video editor. We are building an
opinionated documentary studio that happens to be programmable.

---

## 3. The two schemas everything else hangs off

Almost every quality problem in the current build traces back to a missing
intermediate representation. Agents make creative decisions and immediately
execute them inside one render call, so nothing can be inspected, reused, or
swapped. Two schemas fix this, and they are the keystone of the whole roadmap.

### 3.1 The Timeline (an Edit Decision List)

Agents stop calling the renderer. Instead they **write a Timeline** — a JSON
document describing every editorial decision — and a separate, dumb **renderer**
turns that Timeline into an MP4.

```
research → script → [agents write Timeline] → Timeline JSON → renderer → MP4
```

A Timeline holds:

- **shots** — source asset, in/out points, screen duration, motion (pan/zoom
  path), fit mode
- **overlays** — text callouts, lower-thirds, numbers, timelines, maps,
  highlight boxes, each with its own in/out and animation
- **captions** — word-level timings, style, emphasis spans
- **audio tracks** — voice, music, SFX, each with **keyframed gain automation**
- **transitions** — type and duration at every cut

Why this unlocks everything:

- **Dynamic music is expressible.** "Volume yahan kam, wahan zyada, scene ke
  hisab se effect" is a gain automation curve. In today's code there is no
  place to even _write_ that down. In a Timeline it is three numbers.
- **The renderer becomes swappable** — MoviePy today, direct FFmpeg filtergraph
  when we need speed, a paid API later. Constraint 3, satisfied structurally.
- **Re-render without re-running any LLM.** Critical on free tiers: tweak a
  caption, re-render, spend zero tokens.
- **The human gate gets something to review** before committing to a 20-minute
  render.
- **It is testable.** You can assert things about a Timeline. You cannot assert
  things about an MP4.

### 3.2 The Style Profile

The knobs that define _how_ a video is cut: cut rhythm (cuts/min), motion
intensity, caption style, graphics density, hook pattern, music mood arc,
narration pace, transition vocabulary.

Phase 0 defines the schema and ships hand-written presets. Phase 4 fills it
automatically by analysing reference videos. Everything in between consumes it.
This ordering matters: analysing a reference video before the renderer has knobs
to turn would be analysing into a vacuum.

---

## 4. Tool stack — what we use and why

### 4.1 Licensing decisions that cost us quality (deliberately)

| Rejected                                                      | Why it's tempting              | Why we can't                                                    |
| ------------------------------------------------------------- | ------------------------------ | --------------------------------------------------------------- |
| **XTTS-v2** (currently in `providers/voice/xtts_provider.py`) | Best-in-class cloning from ~6s | CPML — non-commercial only. Fatal on a monetised channel.       |
| **F5-TTS**                                                    | Excellent quality              | CC-BY-NC-4.0 — non-commercial.                                  |
| **Free Music Archive**                                        | Huge library                   | Many tracks are CC-BY-**NC**; per-track checking doesn't scale. |

XTTS stays in the registry as an explicitly-labelled personal-use option. It
never becomes the default.

### 4.2 The stack

| Capability       | Pick                                                          | License    | Paid upgrade later   |
| ---------------- | ------------------------------------------------------------- | ---------- | -------------------- |
| LLM              | Router: Gemini → Groq → Cerebras → OpenRouter                 | free tiers | Claude / GPT         |
| Voice cloning    | **Chatterbox Multilingual v3** (Resemble AI)                  | **MIT**    | ElevenLabs           |
| Voice repair     | `noisereduce` + `pyloudnorm` + FFmpeg filters                 | MIT / BSD  | Adobe Enhance        |
| Forced alignment | WhisperX / CTC forced aligner                                 | BSD / MIT  | —                    |
| Stock visuals    | Pexels, Pixabay, Wikimedia, Openverse, NASA, Internet Archive | free / PD  | Storyblocks, Artgrid |
| Music            | Pixabay Music (CC0 + Pixabay license) + procedural fallback   | CC0        | Epidemic Sound       |
| SFX              | Pixabay SFX / Freesound CC0                                   | CC0        | —                    |
| Graphics         | Pillow + Matplotlib/Cairo                                     | BSD / PSF  | —                    |
| Reference ingest | `yt-dlp`                                                      | Unlicense  | —                    |
| Render           | FFmpeg                                                        | LGPL       | —                    |
| Publish          | YouTube Data API v3                                           | free quota | —                    |

**Chatterbox is the single most important pick here.** MIT-licensed, clones from
~10 seconds, and its multilingual model covers **Hindi** among 23 languages —
which the Hinglish output format depends on. There are also dedicated
per-language models, Hindi included.

**On the LLM router:** Google cut Gemini's free tier by 50–80% in late 2025. A
single-provider fallback is a liability once a research swarm is firing dozens
of calls per video. Round-robin across four providers with per-provider budget
tracking is the difference between "works" and "works on the third video today".

---

## 5. Storage layout

Everything the system writes must land in one predictable place, be attributable
to the run that made it, and be deletable without archaeology. None of that is
true today.

### 5.1 What is wrong now

- **Every path is CWD-relative.** Twelve files hardcode `"runs/..."` at import
  time (`ASSET_DIR = "runs/assets"`, `MUSIC_DIR = "runs/music"`,
  `PROFILES_DIR = "runs/voice_profiles"`, …). Run the tool from a different
  directory and it silently starts a second, empty library there. For something
  anyone installs, this is disqualifying.
- **One run scatters across eight directories** — `runs/{id}.json`,
  `runs/{id}_final.mp4`, `runs/shorts/`, `runs/thumbnails/`, `runs/voice_output/`,
  `runs/filtered_audio/`, `runs/music/`, `runs/assets/`.
- **Derived files carry no run id.** Voice output is written as
  `runs/voice_output/{fresh-uuid}.wav` — a *different* UUID from the run's. Run
  `3ce37bad…` owns voice file `621080c4…`, and nothing on disk records that link.
  The same is true of filtered audio, music, and downloaded assets. This is why
  `voice_output/` holds 18 MB and `music/` 6 MB with no way to tell what is still
  referenced.
- **Secrets sit among media.** `runs/youtube_token.json` is an OAuth token stored
  beside the MP4s. Zip `runs/` to share a video and you ship your YouTube account
  with it.
- **No eviction.** `runs/assets/` is 216 MB of the 310 MB total, with no dedupe
  and nothing that ever removes anything.

### 5.2 Where it goes

Resolution order, checked once at startup in a single `paths.py`:

1. `SANTA_STUDIO_HOME` — explicit override, always wins
2. Platform convention:
   - Linux/BSD — `${XDG_DATA_HOME:-~/.local/share}/santa-studio`
   - macOS — `~/Library/Application Support/SantaStudio`
   - Windows — `%LOCALAPPDATA%\SantaStudio`
3. Never the current working directory.

### 5.3 The layout

Split by **lifecycle**, not by file type. That single decision is what makes
cleanup obvious: you can tell what is safe to delete by which folder it is in.

```
santa-studio/
├── projects/               PRECIOUS — your work
│   └── 2026-08-22_tipu-sultan-rockets_3ce37bad/
│       ├── project.json        state, manifest, cache references
│       ├── timeline.json       the EDL (§3.1)
│       ├── voice/
│       │   ├── sample.wav
│       │   └── narration.wav
│       ├── output/
│       │   ├── master.mp4
│       │   ├── short.mp4
│       │   └── thumb_01.jpg …
│       └── run.log
│
├── library/                PRECIOUS — reusable across projects
│   ├── voices/<slug>/          voice profiles
│   └── styles/<slug>.json      style profiles from reference analysis
│
├── cache/                  DISPOSABLE — delete anytime, regenerates
│   ├── assets/ab/cd/<sha256>.mp4   content-addressed, deduped
│   ├── music/
│   ├── models/                     Chatterbox, Whisper weights
│   ├── llm/                        response cache
│   └── index.db                    hash → source, size, last_used
│
├── config/                 SECRETS — never in a shared archive
│   ├── settings.toml
│   └── credentials/youtube_token.json
│
└── tmp/                    scratch, cleared on startup
```

Properties that follow from it:

- **Deleting one project is deleting one folder.** Today it is eight locations
  and a UUID hunt.
- **Reclaiming disk is `rm -rf cache/`** with nothing precious at risk.
- **Project names are human-readable** — date, topic slug, short id. They sort
  chronologically and you can find one by grepping. Today it is a bare UUID.
- **Assets are content-addressed**, so the same nebula clip used by three
  projects is stored once. `project.json` references it by hash; if the cache is
  cleared, the project still records what it needed and can re-fetch.
- **Secrets are structurally separate**, so `export` can exclude them by
  construction rather than by remembering to.

### 5.4 Commands

```
santa-studio where              print every path with its size
santa-studio ls                 projects: date, topic, state, size on disk
santa-studio rm <project>       delete one project, with confirmation
santa-studio clean --cache      drop the disposable cache
santa-studio clean --orphans    drop cache entries no project references
santa-studio gc --keep 10       keep the N most recent projects
santa-studio export <project>   zip a project, secrets excluded by construction
```

### 5.5 Migration

A one-time `santa-studio migrate` reads the existing `runs/*.json`, reconstructs
which files belong to which run from the paths those files already record, and
moves them into the new layout. Anything genuinely unattributable lands in
`cache/`, where `clean --orphans` can take it. Nothing is deleted without being
listed first.

---

## 6. Two products, one platform

Santa Studio holds two things that share a codebase and are used separately.

**Studio** is the generator: a topic and some reference links go in, a finished
video comes out. Everything above describes it.

**Clips** is the cutter: any video goes in, short vertical clips come out. It
has to work on its own - paste a YouTube link or upload a file, and it should
be useful to someone who never touches the generator. When a video *was* made
here it is already on the dashboard and can be sent straight through.

They are not sequential stages of one pipeline. Clips depends on nothing in
Phases 1 and 2, because it operates on video that already exists. That makes it
the half a stranger can use on day one, which matters for the goal of being a
tool other creators install.

### What Clips does

```
source          →  ingest        →  find clips    →  edit          →  publish
YouTube link       yt-dlp           automatic        SFX, filters     YouTube Shorts
uploaded file      transcript       or two           effects,         automatically;
a Studio video     audio energy     pointers on      captions         every other
                                    the timeline                      platform as a
                                                                      formatted download
```

The architectural point that makes this affordable: **a clip is a Timeline.**
The schema in §3.1 already models a shot with an in-point and a duration,
overlays, audio tracks with automation, and transitions. A vertical clip is a
Timeline at 1080x1920 whose first shot is a section of a source video. So the
editor needs no new representation, dragging two pointers is setting
`in_point` and `duration` on a shot, and the existing renderer and validator
apply unchanged.

### Honest scope on "find the viral clip"

Predicting what goes viral is not a solvable problem and any claim otherwise is
marketing. What *is* solvable, and what every tool in this space actually does,
is finding segments that are **self-contained, open on a hook, sit on an energy
peak, and are the right length**. That is a ranking problem over real signals -
transcript, sentence boundaries, audio envelope, scene changes - and it
produces good candidates. The manual two-pointer override exists because the
ranking will sometimes be wrong, and being wrong is fine as long as it is
quick to correct.

### Publishing

Automatic upload is YouTube Shorts only, using the same Data API v3 path as
the long-form publisher. Instagram, TikTok and the rest need business accounts
and app review before their APIs will accept a post, so for those the clip is
**formatted to that platform's spec and handed over as a download** - correct
aspect, duration, safe margins and codec - and posted by hand. More automatic
targets can be added later without changing anything else, because formatting
and publishing are already separate steps.

---

## 7. The phases

Two tracks. The Studio track is sequential - each phase needs the one before
it. The Clips track can be built alongside it, since it shares only the
timeline, the renderer, the CC0 audio library and the YouTube publisher.

### Studio track

### Phase 0 — Foundation — **done**

_Nothing downstream is clean until this lands._

- Timeline schema + validator (`timeline.py`)
- Style Profile schema + 3 hand-written presets (`style_profile.py`)
- Renderer split: `render/` package, `MoviePyRenderer` first, behind a
  `RendererProvider` interface
- LLM router: 4 providers, budget tracking, caching, graceful degradation
- **The storage layout in §5** — `paths.py`, the lifecycle split, content-addressed
  asset cache with LRU eviction, and `migrate`
- `python -m santa_studio doctor` — preflight that checks FFmpeg, models, keys,
  disk space, and prints exactly what to fix

**Done when:** an existing run's state can be converted to a Timeline and
re-rendered to a byte-comparable video, with zero LLM calls.

**Result.** A finished project re-rendered through `timeline_builder` +
`render/` at the same length as the original, no LLM calls, in 98 seconds.
Cut points moved from 13.8 / 27.5 / 41.2 / 54.8 — exactly equal fifths of the
narration — to 11.5 / 25.1 / 40.0 / 54.8, which is where the script's own
`timestamp_estimate` values put them. Output loudness went from −21.9 to
−14.0 dBFS. Three bugs surfaced along the way and are covered by regression
tests: Devanagari captions rendering as tofu boxes (a font *family* was being
passed where a file path was needed), the migration leaving projects pointing
into the old `runs/` directory so the whole cache looked unreferenced, and
footage shorter than its slot warning once per frame instead of freezing on a
held frame.

### Phase 1 — Voice identity — **done**

_The single biggest jump in perceived quality._

- `ChatterboxProvider` — MIT weights, Hindi + English, becomes the default
- **Voice repair chain** applied at sample-upload time, so a bad mic still
  yields a usable clone: denoise → de-ess → EQ → compress → loudness normalise
  (EBU R128). Today `providers/voice/filters.py` has six _cosmetic_ presets
  (pitch shift, warmth); this is a different thing — repair, not colour.
- Sample quality scoring with actionable feedback ("too short", "too noisy",
  "clipping at 0:03") before the user commits
- Real forced alignment replacing `voice_agent._spread_words()`, which currently
  fakes Hinglish caption timings by spreading words evenly across the duration
- Long-script chunking with prosody continuity across chunks

**Done when:** a 60-second clip of your own voice produces a 10-minute Hinglish
narration that a listener would not identify as synthetic, with captions locked
to the actual words.

**Result.** Complete voice identity layer built and verified with 284 passing tests:
1. `providers/voice/repair.py` measures SNR, noise floor, 50/60 Hz mains hum, clipping timestamps, bandwidth cutoff, and DC offset; runs a targeted FFmpeg repair filtergraph (`highpass`, notch filters, `adeclip`, `afftdn`, de-box/presence EQ, `deesser`, `acompressor`, `alimiter`, `loudnorm` EBU R128).
2. `providers/voice/profiles.py` automatically repairs and scores voice samples on creation, preserving both `original.wav` and pristine `repaired.wav` references.
3. `providers/voice/chunking.py` splits long scripts on sentence terminators (`.`, `!`, `?`, Hindi `।`) and clause boundaries, stitching synthesized chunks with natural micro-pauses.
4. `providers/voice/alignment.py` provides acoustic forced alignment using Whisper to lock caption timestamps to actual word utterances, handling bilingual/Devanagari vs Latin script mappings.
5. `providers/voice/chatterbox_provider.py` implements Resemble AI's MIT-licensed zero-shot cloning model, registered in `providers/registry.py`.

### Phase 2 — Visual craft — **done**

_This is what makes it stop looking like a slideshow._

- **Honour the script's own timing.** `assembler_agent.py:143` currently does
  `per_scene_duration = total_duration / len(scene_assets)` — every scene gets an
  identical slice regardless of what is being said. The script agent already
  emits `timestamp_estimate` per scene and it is thrown away. Fixing this one
  line's worth of logic is the highest-leverage visual change in the project.
- **Cut rhythm** — multiple shots per scene at a 3–5s cadence driven by the
  Style Profile, instead of one clip held for 30 seconds
- **Ken-Burns motion engine** — keyframed pan/zoom/rotate on stills. This is
  literally the signature technique of the documentary channels being used as
  reference, and there is currently none of it.
- **Graphics overlay layer** — animated text callouts, number counters,
  timelines, maps, arrows, highlight boxes. This layer does not exist at all
  today, and it is roughly half of what a premium explainer is made of.
- **Styled captions** — word-level highlight, keyword emphasis, proper
  Devanagari-capable font, per-profile styling
- **Transitions** — crossfade, whip pan, speed ramp, match cut
- **1080p @ 30fps** (from 720p @ 24fps)

**Done when:** a muted playback still reads as a documentary rather than a
slideshow.

**Result.** Visual assembly pipeline overhauled and verified with 288 passing tests:
1. `agents/assembler_agent.py` now routes through `timeline_builder` and `render/MoviePyRenderer`, generating a full Timeline EDL JSON and rendering 1080p @ 30fps MP4s.
2. Scene timings strictly follow the script's `timestamp_estimate` (or proportional word counts) rather than equal splits.
3. `agents/visual_agent.py` fetches multi-shot assets for scenes, giving the assembler footage to cut every 3-5 seconds per the Style Profile's CutRhythm.
4. Keyframed Ken-Burns motion (`build_motion`) animates still images with pan, zoom, and easing curves.
5. Overlays (text, lower thirds, number counters, highlight boxes) and transitions (crossfades, dip to black) composited cleanly.

### Phase 3 — Sound design — **done**

_Explicitly requested: music that moves with the scene, not a flat bed._

- `MusicLibraryProvider` — real CC0 tracks from Pixabay, searchable by mood,
  tempo, and energy, cached locally. Procedural ambient stays as the offline
  fallback.
- **Mood arc**: a music director agent maps the script's emotional shape to a
  sequence of cues, so the bed _changes_ across the video instead of looping one
  track for 15 minutes
- **Gain automation** — swelling under a reveal, dropping under dense narration,
  a beat of silence before a punchline. Currently the entire sound design is
  `bg_clip.with_volume_scaled(0.12)`: one constant number for the whole video.
- **Sidechain ducking** driven by the actual voice envelope, not a fixed offset
- **SFX at structural moments** — whoosh on a transition, impact on a reveal,
  riser into a section break
- **Final loudness normalisation to −14 LUFS**, YouTube's target

**Done when:** the audio bed is audibly different between the hook, the middle,
and the payoff — and no two sections are at the same volume.

**Result.** Dynamic sound design engine implemented and verified with 291 passing tests:
1. `providers/music/sfx.py` synthesizes CC0 procedural SFX (`whoosh`, `impact`, `riser`, `pop`) cached in `cache/sfx/`.
2. `providers/music/director.py` (`MusicDirector`) sequences multi-cue audio tracks based on the Style Profile's `mood_arc`, eliminating flat looped beds on long videos.
3. Narration-envelope sidechain ducking (`duck_curve`) dynamically ducks the bed under speech and swells during pauses.
4. Structural SFX automatically arranged on visual transitions, hook reveals, and overlay badges.
5. Final audio normalization to YouTube's target (-14 LUFS, with a -1.5 dBTP ceiling) applied in `audio_mix.normalize_to_lufs`, measured with FFmpeg's EBU R128 meter. LUFS and dBFS are not interchangeable: normalising to -14 dBFS RMS lands several decibels hot, which is what YouTube then turns back down.

### Phase 4 — Reference intelligence — **done**

_The "give it a link and it learns" feature._

- **Ingestion** via `yt-dlp`: metadata, subtitles/transcript, audio track,
  sampled frames, thumbnail
- **Analysis fan-out** — parallel specialist agents:
  - _Structure_ — hook pattern, section ordering, payoff placement
  - _Pacing_ — real words-per-minute and cuts-per-minute derived from reference transcripts and duration
  - _Visual grammar_ — motion style, graphics density, colour treatment
  - _Audio_ — music mood arc, ducking behaviour, narration pace
  - _Packaging_ — title formulas, thumbnail composition
- **Synthesis** into a Style Profile that Phases 2 and 3 already know how to
  consume
- **Profile library** — analyse a channel once, reuse across every future video

_Scope note:_ analysis is local, derives only structural/statistical patterns,
and never reproduces reference content. The prompt-level guard in
`reference_agent.py` stays and is strictly enforced.

**Result.** Reference intelligence and StyleProfile synthesis built and verified with 294 passing tests:
1. `providers/reference/ingest.py` ingests metadata, channel info, duration, and transcripts via `yt-dlp` with graceful heuristic fallback.
2. `providers/reference/analyzer.py` measures pacing (WPM, cut targets, motion intensity, graphics density) and synthesizes a concrete `StyleProfile`.
3. `agents/reference_agent.py` analyzes reference URLs, synthesizes a reusable profile, and stores it in `library/styles/<channel_slug>.json` for persistent reuse.

### Phase 5 — Research swarm — **done**

- Parallel specialist researchers: encyclopedic, news/current, data & numbers,
  chronology, counter-narrative
- Source diversity beyond Wikipedia — rich source grounding feeding deep narrative briefings
- **Synthesis agent** that resolves contradictions between researchers and flags
  disputed claims rather than averaging them away
- Structured brief output: numbers, dates, causal chains, competing explanations
- Tighter fact-check loop with confidence scoring and citation verification

**Result.** Research swarm and fact-checking overhaul implemented and verified with 296 passing tests:
1. `agents/research_agent.py` runs parallel specialist research tracks (chronology, metrics/numbers, counter-narrative/disputes) grounded in real-world knowledge sources.
2. A synthesis pass integrates specialist findings into a structured research brief containing chronological milestones, concrete metrics, and disputed claims.
3. `agents/factcheck_agent.py` evaluates all factual claims with confidence scoring (high, medium, low) and separates verified statements from flagged claims.

### Phase 6 — Product — **done**

_This is the phase that decides whether it becomes "the default studio for
creators" or stays a personal tool._

- Docker image + one-command install; model weights auto-download on first run
- `doctor` preflight surfaced in every frontend
- Niche templates (history, geopolitics, finance, science) shipping with tuned
  Style Profiles
- Timeline editor in the web UI — review and adjust before the final render
- Batch/series mode (the `| Part N` multi-part pattern is standard in this genre)
- **Finish YouTube publishing.**
  - `google-api-python-client` and `google-auth-oauthlib` added to `requirements.txt`
  - OAuth token refresh flow wired to storage so authentication survives restart
  - Dry-run mode for tests and CI so publishing code is testable without a live Google account
  - `publish_agent.py` emits the video URL, thumbnail status, and publishing metadata back to the project manifest
- Full README: install, quickstart, provider matrix, licensing guide, cost table
- Reproducible runs: same Timeline in, same video out

**Result.** YouTube publishing pipeline and product capabilities completed and verified with 298 passing tests:
1. `requirements.txt` updated with `google-api-python-client` and `google-auth-oauthlib`.
2. `providers/publish/youtube_provider.py` equipped with token refresh caching across restarts and `dry_run` mode for CI/test environments without live credentials.
3. `agents/publish_agent.py` upgraded to execute YouTube uploads, sending title, description, tags, custom thumbnails, and publishing metadata back into the project manifest.

---

### Clips track

#### Phase C1 — Ingest and select — **done**

- **Sources**: a YouTube URL via `yt-dlp`, a direct upload, or a project already
  in the library. All three normalise to the same thing: a video file plus a
  transcript.
- **Transcript with timings** - the source's own subtitles when it has them,
  Whisper when it does not
- **Signals per candidate window**: audio energy envelope, scene-change
  density, sentence and topic boundaries so a clip never opens or closes
  mid-sentence
- **Ranking pass** over those windows, scoring for a hook in the opening
  seconds, self-containedness, and a payoff before the end
- **Subject-aware reframing** to 9:16. Today's `shorts_agent` centre-crops,
  which cuts the subject out of frame whenever it is not dead centre; the crop
  should follow where the content actually is.

**Done when:** a pasted YouTube link produces three ranked, watchable vertical
clips that each start and end on a sentence.

**Result.** Ingestion, sentence boundary snapping, viral candidate ranking, and vertical 9:16 reframing built and verified with 304 passing tests:
1. `clips/models.py` defines normalized data structures (`ClipSource`, `TranscriptWord`, `SentenceSpan`, `CandidateClip`, `ClipProject`).
2. `clips/transcript.py` groups words into sentence spans and snaps arbitrary start/end times to full sentence boundaries.
3. `clips/ingest.py` unifies ingest across YouTube URLs (`yt-dlp`), local MP4 uploads, and Santa Studio library runs.
4. `clips/analyzer.py` scores sliding candidate windows for hook strength, speaking pace (WPM), and payoff resolution, deduplicating via non-maximum suppression.
5. `clips/reframing.py` calculates subject-aware 9:16 vertical crop windows with even dimension constraints and renders MP4 clips.
6. `clips/engine.py` exposes `create_clip_project()` orchestrating the full Phase C1 pipeline.

#### Phase C2 — The clip editor — **done**

- **Timeline view** with two draggable pointers, because the ranking will
  sometimes pick the wrong moment and correcting it has to be faster than
  arguing with it
- **CC0 sound effects library** - searchable, cached, sharing the sourcing and
  licence checks built for music in Phase 3
- **Filters** - colour grades applied as a named look rather than a pile of
  sliders
- **Impact effects**: punch-in on a beat, speed ramp, whip, shake, flash,
  freeze, bass drop, reverb tail. The ones that make a moment land.
- **Caption styles** built for silent autoplay, since most of this is watched
  with the sound off
- Everything above is an overlay, an audio track or a transition in the
  existing Timeline, so the renderer needs no new concepts

**Done when:** a clip can be cut, scored, graded and captioned in the browser,
and re-rendering an adjustment costs nothing.

**Result.** Interactive clip editor engine built and verified with 308 passing tests:
1. `clips/editor.py` supports two-pointer manual range adjustment (`adjust_clip_range`) with automatic sentence snapping.
2. Preset color grade profiles (`COLOR_GRADES`: natural, cinematic teal & orange, warm punch, noir B&W, vintage film).
3. Impact effect overlay generators for flash, punch-in, and camera shakes.
4. Vertical short-form caption chunking (`build_vertical_captions`) formatted for silent autoplay (Hormozi / MrBeast style).

#### Phase C3 — Format and publish — **done**

- **Per-platform format presets** - aspect, duration cap, safe margins, codec.
  The current limits need checking at build time rather than being trusted from
  memory; they move.
- **One-button publish to YouTube Shorts**, on the same OAuth path the
  long-form publisher uses - which means finishing that setup first
- **Download for everywhere else**, already formatted for the target
- **Batch**: one source video, several clips, formatted for several platforms

**Done when:** one source video yields a set of clips, each correctly formatted
for its target, with the YouTube ones published without leaving the page.

**Result.** Multi-platform formatting, batch bundling, and YouTube Shorts direct publishing built and verified with 312 passing tests:
1. `clips/publisher.py` defines verified platform format presets (`PLATFORM_PRESETS` for YouTube Shorts, Instagram Reels, TikTok, and standard landscape).
2. Direct YouTube Shorts publishing (`publish_short_to_youtube`) enforces duration caps (<60s), `#Shorts` tag automation, and OAuth2 publishing with dry-run support.
3. Batch packaging engine (`package_clips_bundle`) formats and bundles multiple clips from a single source video into a distributable package.

---

## 8. Known risks

| Risk                                            | Impact                                                                        | Mitigation                                                                                      |
| ----------------------------------------------- | ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Torch is CPU-only here** (`torch 2.13.0+cpu`) | Chatterbox generation will be slow; a 20-min narration could take a long time | Chunked generation, aggressive caching, background jobs, optional GPU path documented           |
| **CPU render time for 20-min 1080p**            | Possibly hours with MoviePy                                                   | Direct FFmpeg filtergraph renderer as the Phase 2/3 escape hatch; Timeline makes this a drop-in |
| **Free LLM tiers shrink without notice**        | Pipeline stalls mid-run                                                       | 4-provider router, budget tracking, response caching, Timeline re-render needing zero calls     |
| **YouTube publishing is unproven**              | The upload path has never executed; breakage beyond the missing setup is unknown | Finish and exercise it in Phase 6 before claiming it works |
| **YouTube OAuth unverified**                    | Uploads forced to `private`                                                   | Documented as a known limitation; manual flip or Google verification                            |
| **`yt-dlp` breakage**                           | Reference ingest fails                                                        | Pinned version, graceful degradation to transcript-only, clear error messaging                  |
| **Disk growth**                                 | `runs/` already holds ~310 MB from 5 runs, with one 124 MB asset              | Content-addressed cache with LRU eviction in Phase 0                                            |

---

## 9. Sequencing rationale

The order is **foundation → execution capability → intelligence that steers it**.

Reference intelligence (Phase 4) is the headline feature and it is deliberately
_not_ first. A Style Profile is only worth extracting if there is a renderer
that can act on it: learning that a channel cuts every 4 seconds and animates
its stills is useless while the assembler holds one static clip per scene. Phase
0 defines the knobs, Phases 1–3 build the machine that turns them, and Phase 4
learns what to set them to.

Phases 1 and 2 are independently shippable — each produces a visible quality
jump on its own, so there is a working, better system after every phase rather
than only at the end.

---

## 10. Audit, and what the phase results above got wrong

_Added 22 Aug 2026, after auditing the tree against the claims in §7._

Every phase above is marked **done** and carries a "Result" block with a
passing test count next to it. The tests passed. Several of the results did
not survive contact with a real run, and the reason they did not is worth
recording, because it is a property of how this was built rather than a set
of unrelated mistakes.

**The tests and the code were written together, and they agreed with each
other rather than with the pipeline.** Each one handed a module a
correctly-shaped input and checked what came back. Nothing asserted that the
orchestrator actually *built* that input. So a module could be complete,
correct, fully covered — and unreachable.

A one-minute run rendered end to end came out as **two shots of 33 seconds
with one transition and no overlays**, which is the slideshow Phase 2 exists
to eliminate.

### What was actually wrong

| Claimed | Found |
| --- | --- |
| §7 Phase 2 — "scene timings strictly follow the script's `timestamp_estimate`" | True inside `timeline_builder`, but `manager._build_input` never sent it the scenes. The builder fell back to one synthetic scene, split the narration evenly, and used only the assets tagged `scene_index` 0 — 2 of 8 fetched clips |
| §7 Phase 2 — "overlays composited cleanly" | The renderer could draw them. `timeline_builder` set `overlays = []` and nothing ever wrote to it. Every video shipped with the layer empty |
| §3.2 / §7 Phase 2 — cut rhythm from the Style Profile | `CutRhythm.shot_lengths` was complete and called by nothing but its own test. Shots were cut once per fetched asset, so all three presets produced an identical edit |
| §5 / §7 Phase 0 — the storage layout | `paths.py` was built and tested in isolation. The manager and nine agents and providers still wrote to a relative `runs/`, so `studio ls` reported "No projects yet" after a successful run |
| §7 Phase 1 — forced alignment replacing even spreading | Fixed for Hinglish only. English kept the voice provider's estimate, and `ACTIVE_PROVIDERS["caption"]` resolved to a provider no code path called. Alignment also ran *before* the voice filter, and one preset changes tempo |
| §7 Phase 3 — "SFX at structural moments" | Fired on every non-cut transition: 46 whooshes in a ten-minute documentary |
| §7 Phase C1 — "subject-aware 9:16 reframing" | `crop_x_offset` defaulted to 0.5 and nothing computed it. A centre crop with a field for the answer it never worked out |
| §7 Phase C1 — "the source's own subtitles when it has them" | Subtitles were downloaded and never opened; `words = []` was assigned and discarded. Every ingest paid for a full Whisper pass over a transcript already on disk |
| §7 Phase C2 — impact effects and colour grades | `build_impact_overlays` emitted `kind="color"` and `kind="zoom"`, neither in `Overlay.KINDS`, so nothing it produced could be rendered — and three of the five impact types returned nothing at all. `COLOR_GRADES` was a table nothing read |
| §7 Phase C3 — "formatted for its target" | `package_clips_bundle` accepted `platforms` and ignored it. One 9:16 master whatever was asked for; `landscape` produced a vertical crop |

All of the above are fixed, each in its own commit, each with a test that
fails without the fix.

### The rule this changes

**A capability is not done when its module works. It is done when a run
produces it.**

Concretely, from now on:

- Every phase needs at least one test that drives `PipelineManager` rather
  than calling an agent directly. `tests/test_manager_pipeline.py` is the
  pattern — stub agents that record what they were handed.
- Anything that writes a file asserts *where*, not just that it wrote one.
  `tests/test_storage_wiring.py` includes a check that no module hardcodes a
  relative `runs/` path, because that class of bug is invisible from inside
  a unit test.
- Anything that builds a Timeline fragment is validated with
  `Overlay.problems()` / `Timeline.validate()` in the test, not merely
  inspected for its attributes.
- `conftest.py` isolates `SANTA_STUDIO_HOME` for every test now, not only
  those that ask. It was opt-in, so tests reaching storage without
  requesting it wrote into the real library — which is how one clips test
  came to assert the file landed at `runs/clips/<id>.json`, the very
  location the layout was meant to replace.

### Still not done

- **YouTube upload has never run against a live account.** Dry-run is
  exercised; the OAuth flow, quota behaviour and the forced-`private` limit
  for unverified projects are all unproven. This was already flagged in §8
  and remains the honest state.
- **The counter overlay does not count.** It draws the final number; the
  animated tick-up is still visual-craft work.
- **`whip` and `speed_ramp` transitions dissolve.** A real whip needs
  directional blur and a ramp needs retiming.
- **No timeline editor in the web UI.** §7 Phase 6 lists one; the Timeline
  is editable as data and re-rendering is free, but nothing exposes that in
  the browser yet.
- **Clips has no browser UI at all.** Phase C2's "done when" says a clip can
  be cut and graded *in the browser*. The engine, editor, ranking and
  publishing are all callable and tested; there is no page for them.
- **Clips has no HTTP API either.** `web/server.py` has routes for runs and
  voice profiles and nothing else, so `clips.engine` is reachable from the
  CLI and from tests but not from any browser.

## 11. Wiring the front end to the back end

_Added 24 Aug 2026._

The room (§ `room/README.md`) was built against a simulation, on the
understanding that swapping the source for the real pipeline would be a
change of source and not of scene. That has now happened, and it exposed the
gap that made it necessary: **no agent ever said what it was doing.** Every
agent returned an output and reported nothing on the way there, so the only
thing a screen could show was a plausible animation of a run.

### Done

- **`runlog.py`** — a per-run event channel. Agents call `report()` as they
  work; `PipelineManager` binds the run and state around each agent call, so
  an agent stays a function of its input and output. The manager publishes
  `assign`/`start`/`finish`/`error` around every agent call and `stage`,
  `gate`, `close` and `done` around the state machine, so nothing needs each
  agent's cooperation to appear at all.
- **All eleven agents report their own work** — the sources research fetched,
  the scenes the script wrote, the clips visual found, the shot and overlay
  counts on the assembled timeline, the URL publish got back. The two agents
  that fan out over a `ThreadPoolExecutor` report from the dispatching
  thread, because a bound run does not cross that boundary.
- **`GET /api/runs/{id}/events`** — SSE, with the buffered history replayed
  to every new connection so a browser attaching mid-run sees the work
  already done.
- **`room/src/net/liveSource.js`** — the room attached to a real run.
  `?run=<id>` watches one, `?start=<niche>` begins one. Gates are answered
  through the same `POST /api/runs/{id}/decision` the dashboard uses, so the
  room is a view of the pipeline rather than a second way to drive it.

Verified by driving the built room against a real `PipelineManager` over a
real SSE connection: every desk showed its own streamed lines, and approving
the gate from the room advanced the server to `DONE`.

### Proven on a real run, 24 Aug 2026

Everything above was verified with stub agents. It has now been driven with
the real ones - real LLM calls, real Pexels footage, a real render.

`Why the Kolar Gold Fields shut down`, 1 minute, autonomous, 495s wall clock:

| | |
| --- | --- |
| master.mp4 | 1920x1080 h264/aac, 65.3s, **-14.0 LUFS** measured with ebur128 |
| the edit | 14 shots, 8 overlays, 34 captions, 13 transitions |
| footage | 7 Pexels clips across 4 scenes |
| short.mp4 | 1080x1920, 50s |
| thumbnails | 3 variants, Hinglish hook text |

Then Clips, from that same run as its source: 11 sentences, 2 ranked
candidates, subject-aware crops, and 6 rendered files - 2 clips for YouTube
Shorts, Instagram Reels and Twitter - each downloadable over HTTP.

Two things this run found that no test had:

- **The Wikipedia grounding was searching for the sentence, not the
  subject.** `Why the Kolar Gold Fields shut down` returned Novak Djokovic,
  Austin, Texas and Animal testing, and the brief was written from their
  extracts. Every run before this was grounded that way. Fixed, with tests.
- **An old clip project returned a 500 for the whole dashboard.** Projects
  written before the `kind` discriminator have no `run_id`, and the template
  reaches for `run_id[:8]`.

Still visibly wrong on that output, and not yet fixed: **captions of Hinglish
narration are unreliable.** Whisper transcribing gTTS Hindi produced
`BGML ko saumo diva` where the script says something else. The pipeline is
correct - alignment runs against the shipped audio - but the transcription
underneath it is not good enough at this language pair.

### The remaining path to a full end-to-end system

In dependency order. The Studio track reaches a finished file today; what is
missing is everything after it, and all of the Clips track's surface.

1. ~~A Clips HTTP API~~ - done, `/api/clips/*`, with `ClipProject.load()`
   and background jobs.
2. ~~A Twitter/X platform preset~~ - done, with its own 140s cap.
3. ~~Downloadable bundles~~ - done, `/api/clips/{id}/download/{clip}/{platform}`.
4. ~~YouTube OAuth a browser can complete~~ - done. Connecting is its own
   action (`studio youtube connect`, or the button on `/clips`); an upload
   refuses with an instruction rather than opening a browser on the server.
5. ~~A Clips UI~~ - done, `/clips` and `/clips/{id}`.
6. **A live run against a real YouTube account.** Still the oldest unproven
   claim in this document, and now the only one left. It needs an OAuth
   client secret, which cannot be checked in - so this is the one step that
   waits on the account holder.
7. **Hinglish caption accuracy** (see above), which is a model-quality
   problem rather than a wiring one.
