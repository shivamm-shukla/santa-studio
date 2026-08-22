# Santa Studio — Roadmap

Goal: a system that takes a topic plus a few reference channel links, learns
their craft, researches deeply, narrates in _your own cloned voice_, edits
itself like a real documentary, and uploads the finished video — with nobody
appearing on camera.

Written 22 Aug 2026. Replaces the former `HANDOFF.md`.

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
- **Upload** — _not working yet._ The provider is written but has never run: its Google dependencies are not in `requirements.txt`, its env vars are not in
  `.env.example`, and no OAuth credentials exist. See Phase 6.

Everything above except upload is verified across all four frontends: FastAPI web
app, Telegram bot, CLI, and the Streamlit prototype.

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

### 2.1 The Timeline (an Edit Decision List)

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

### 2.2 The Style Profile

The knobs that define _how_ a video is cut: cut rhythm (cuts/min), motion
intensity, caption style, graphics density, hook pattern, music mood arc,
narration pace, transition vocabulary.

Phase 0 defines the schema and ships hand-written presets. Phase 4 fills it
automatically by analysing reference videos. Everything in between consumes it.
This ordering matters: analysing a reference video before the renderer has knobs
to turn would be analysing into a vacuum.

---

## 4. Tool stack — what we use and why

### 3.1 Licensing decisions that cost us quality (deliberately)

| Rejected                                                      | Why it's tempting              | Why we can't                                                    |
| ------------------------------------------------------------- | ------------------------------ | --------------------------------------------------------------- |
| **XTTS-v2** (currently in `providers/voice/xtts_provider.py`) | Best-in-class cloning from ~6s | CPML — non-commercial only. Fatal on a monetised channel.       |
| **F5-TTS**                                                    | Excellent quality              | CC-BY-NC-4.0 — non-commercial.                                  |
| **Free Music Archive**                                        | Huge library                   | Many tracks are CC-BY-**NC**; per-track checking doesn't scale. |

XTTS stays in the registry as an explicitly-labelled personal-use option. It
never becomes the default.

### 3.2 The stack

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

### 4.1 What is wrong now

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

### 4.2 Where it goes

Resolution order, checked once at startup in a single `paths.py`:

1. `SANTA_STUDIO_HOME` — explicit override, always wins
2. Platform convention:
   - Linux/BSD — `${XDG_DATA_HOME:-~/.local/share}/santa-studio`
   - macOS — `~/Library/Application Support/SantaStudio`
   - Windows — `%LOCALAPPDATA%\SantaStudio`
3. Never the current working directory.

### 4.3 The layout

Split by **lifecycle**, not by file type. That single decision is what makes
cleanup obvious: you can tell what is safe to delete by which folder it is in.

```
santa-studio/
├── projects/               PRECIOUS — your work
│   └── 2026-08-22_tipu-sultan-rockets_3ce37bad/
│       ├── project.json        state, manifest, cache references
│       ├── timeline.json       the EDL (§2.1)
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

### 4.4 Commands

```
santa-studio where              print every path with its size
santa-studio ls                 projects: date, topic, state, size on disk
santa-studio rm <project>       delete one project, with confirmation
santa-studio clean --cache      drop the disposable cache
santa-studio clean --orphans    drop cache entries no project references
santa-studio gc --keep 10       keep the N most recent projects
santa-studio export <project>   zip a project, secrets excluded by construction
```

### 4.5 Migration

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
The schema in §3 already models a shot with an in-point and a duration,
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

### Phase 1 — Voice identity

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

### Phase 2 — Visual craft

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

### Phase 3 — Sound design

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

### Phase 4 — Reference intelligence

_The "give it a link and it learns" feature._

Worth stating plainly: **this does not work today at all.**
`agents/reference_agent.py:22` carries a `TODO` saying the agent cannot read the
URLs, so it guesses a style from the URL _string_. YouTube channel pages also
render client-side, so plain HTTP fetching returns only the page shell — there is
nothing in it to analyse. `yt-dlp` is the actual path.

- **Ingestion** via `yt-dlp`: metadata, subtitles/transcript, audio track,
  sampled frames, thumbnail
- **Analysis fan-out** — parallel specialist agents:
  - _Structure_ — hook pattern, section ordering, payoff placement
  - _Pacing_ — real cuts-per-minute measured from frame differences, not guessed
  - _Visual grammar_ — motion style, graphics density, colour treatment
  - _Audio_ — music mood arc, ducking behaviour, narration pace
  - _Packaging_ — title formulas, thumbnail composition
- **Synthesis** into a Style Profile that Phases 2 and 3 already know how to
  consume
- **Profile library** — analyse a channel once, reuse across every future video

_Scope note:_ analysis is local, derives only structural/statistical patterns,
and never reproduces reference content. The existing prompt-level guard in
`reference_agent.py` stays and gets stricter.

### Phase 5 — Research swarm

- Parallel specialist researchers: encyclopedic, news/current, data & numbers,
  chronology, counter-narrative
- Source diversity beyond Wikipedia — today it is 3 search hits truncated to 600
  characters each, feeding a "2–4 sentence" summary. That is not a foundation for
  a 20-minute video.
- **Synthesis agent** that resolves contradictions between researchers and flags
  disputed claims rather than averaging them away
- Structured brief output: numbers, dates, causal chains, competing explanations
- Tighter fact-check loop with confidence scoring and citation verification

### Phase 6 — Product

_This is the phase that decides whether it becomes "the default studio for
creators" or stays a personal tool._

- Docker image + one-command install; model weights auto-download on first run
- `doctor` preflight surfaced in every frontend
- Niche templates (history, geopolitics, finance, science) shipping with tuned
  Style Profiles
- Timeline editor in the web UI — review and adjust before the final render
- Batch/series mode (the `| Part N` multi-part pattern is standard in this genre)
- **Finish YouTube publishing.** The provider code exists and has never been
  executed. What is actually missing:
  - `google-api-python-client` and `google-auth-oauthlib` added to
    `requirements.txt` — the provider imports them and raises at runtime today
  - `YOUTUBE_CREDENTIALS_FILE` and `YOUTUBE_TOKEN_FILE` documented in
    `.env.example`
  - A written Google Cloud setup guide: create the project, enable YouTube Data
    API v3, configure the OAuth consent screen, add yourself as a test user,
    download the Desktop-app client secret
  - The OAuth flow run once end to end against a real channel, and the whole
    `YOUTUBE_PUBLISH` state exercised with a real upload
  - A `doctor` check that reports exactly which of these is missing
  - The token moved into `config/credentials/` per §5, out of the media directory
- Full README: install, quickstart, provider matrix, licensing guide, cost table
- Reproducible runs: same Timeline in, same video out

---

### Clips track

#### Phase C1 — Ingest and select

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

#### Phase C2 — The clip editor

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

#### Phase C3 — Format and publish

- **Per-platform format presets** - aspect, duration cap, safe margins, codec.
  The current limits need checking at build time rather than being trusted from
  memory; they move.
- **One-button publish to YouTube Shorts**, on the same OAuth path the
  long-form publisher uses - which means finishing that setup first
- **Download for everywhere else**, already formatted for the target
- **Batch**: one source video, several clips, formatted for several platforms

**Done when:** one source video yields a set of clips, each correctly formatted
for its target, with the YouTube ones published without leaving the page.

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
