# Santa Studio — Architecture

_How the system is put together, and why. For what it does and how to run it,
see [the README](../README.md). For the product brief and the honest status of
every claim, see [SPEC.md](SPEC.md). For the engineering plan and phase
history, see [ROADMAP.md](ROADMAP.md)._

---

## 1. The shape of it

```
┌──────────────┐      ┌──────────────────┐      ┌──────────────────────┐
│  Interfaces  │─────▶│     Manager      │─────▶│        Agents        │
│ CLI · bot ·  │      │  state machine,  │      │ topic → reference →  │
│ web · room   │◀─────│  validate/retry, │◀─────│ research → factcheck │
└──────────────┘      │  JSON after each │      │ → script → voice →   │
                      │  transition      │      │ visual → assembly →  │
                      └──────────────────┘      │ shorts → thumbnail → │
                                                │ publish              │
                                                └───────────┬──────────┘
                                                            ▼
                          ┌─────────────────────────────────────────────┐
                          │                 Providers                   │
                          │ LLM · Voice · Visual · Caption · Music ·     │
                          │ Publish — chosen by config, never imported   │
                          │ by an agent                                  │
                          └─────────────────────────────────────────────┘
                                                            ▼
                          ┌─────────────────────────────────────────────┐
                          │        Timeline (EDL) → Renderer            │
                          │  every shot, move, overlay and gain written  │
                          │  down first; the renderer only reads it      │
                          └─────────────────────────────────────────────┘
```

Four ideas hold the whole thing up. Everything else is detail.

**One agent per stage, and an agent is a pure function.** Every agent is
`run(input_data, config) -> {"success": bool, "output": dict, "error": str}`.
It does not know what ran before it, what runs after it, or which interface a
human is watching from. `manager.py` owns the order, the validation and the
retries.

**No agent ever imports a provider.** Capabilities are abstract classes in
`providers/base.py`, resolved through `providers/registry.py` from
`config.ACTIVE_PROVIDERS`. Swapping Pexels for another stock library, or one
LLM for another, is a config change.

**The edit is data before it is a video.** Agents describe the cut — shots,
motion paths, overlays, captions, audio with keyframed gain — as a `Timeline`.
A renderer turns that into a file. Re-rendering an adjusted edit costs no API
calls, and the renderer can be replaced without touching an agent.

**A run is resumable because state is written after every transition.** The
pipeline stops where it is, on disk, with everything up to that point intact.

---

## 2. The pipeline

`manager.py: STATE_SEQUENCE` is the whole run. Each state maps to one agent
and to one validation of that agent's output.

| # | State | Agent | Owes |
|---|---|---|---|
| 1 | `TOPIC_SELECTION` | `topic_agent` | A topic — the owner's, or one found from real Wikipedia readership |
| 2 | `REFERENCE_ANALYSIS` | `reference_agent` | A Style Profile learned from reference videos' structure, never their content |
| 3 | `RESEARCHING` | `research_agent` | A brief grounded on three indexes, with chronology, figures and disputes |
| 4 | `FACT_CHECKING` | `factcheck_agent` | Claims scored, sourced, and where sources disagree, marked disputed |
| 5 | `SCRIPTING` | `script_agent` | Scenes, with spoken and on-screen text split where the languages differ |
| 6 | `VOICE_GENERATION` | `voice_agent` | Narration and caption timings measured off the audio that ships |
| 7 | `VISUAL_SELECTION` | `visual_agent` | Footage per scene: stock first, generated only where stock genuinely fails |
| 8 | `VIDEO_ASSEMBLY` | `assembler_agent` | A Timeline, then a rendered master |
| 9 | `SHORTS_EXTRACTION` | `shorts_agent` | Vertical cuts, per platform |
| 10 | `THUMBNAIL` | `thumbnail` | Variants with hook text |
| 11 | `YOUTUBE_PUBLISH` | `publish_agent` | Upload, with sources as clickable links |

### Failure, retry, and parking

An agent that fails validation is run once more. If it fails again the run
halts, having saved its state, and reports which stage and why.

A stage stopped because a **daily allowance ran out** is different and is
treated differently: it parks. It does not spend its retry on a request that
cannot succeed, it records when the allowance rolls over
(`state.parked_until`), and it says it is out of allowance rather than broken.
A per-minute rate limit deliberately does *not* park — the LLM router already
waits that out and moves to the next provider.

### Work that survives a retry

`checkpoints.py` lets a long stage write down the parts of itself that
succeeded, under the run's own project. The research swarm uses it: three
parallel LLM calls are three of a free tier's twenty requests for the day, and
re-deriving answers already on disk is how a run ends up parked for want of
allowance it had already used. Two runs never share a checkpoint, and an empty
answer is never saved — that would pin a failure in place.

### Two execution models

`PipelineManager.run()` is a blocking loop, for the CLI. `PipelineManager.step()`
advances one unit of work and returns, for callers that cannot block: the web
app inside a request, and the Telegram bot which has to stay responsive while a
run advances on a background thread. Both go through the same states, the same
validation and the same gates.

---

## 3. Providers

Every external capability is an ABC in `providers/base.py` with concrete
implementations beside it, resolved by `providers/registry.py`.

| Capability | Implementations | Notes |
|---|---|---|
| `LLMProvider` | Gemini, Groq, Cerebras, OpenRouter, Claude | Behind a router — see below |
| `VoiceProvider` | gTTS, Chatterbox, XTTS-v2 | Licence differences matter; see the README |
| `VisualProvider` | Pexels, Pixabay, Wikimedia, generated | Tried in that order |
| `CaptionProvider` | Whisper (local) | Model size chosen against free disk |
| `MusicProvider` | Ambient | |
| `PublishProvider` | YouTube | Dry-run path proven; a live upload is not |

### The LLM router

`providers/llm/router.py` puts four free tiers behind one interface. It keeps a
per-day budget on disk (`budget.py`) because the front ends are separate
processes sharing one quota, skips a provider that is known to be spent rather
than failing a request against it, and drops providers with no key configured.

`providers/llm/backoff.py` reads what a provider actually said when it refused.
A free tier says no in two very different ways, and reading both as the same
thing is how one busy minute used to cost a provider a whole day:

- **"Not this second"** — a tokens-per-minute ceiling, with a stated delay. The
  router waits, if the wait is short enough to be worth it, and retries.
- **"Not today"** — a spent daily quota. The provider is marked exhausted and
  the run parks.

An unexplained 429 is treated as the recoverable kind: one wasted request is
cheaper than losing a provider until tomorrow.

### Reading JSON out of an LLM

`agents/_llm_utils.call_llm_json` is what every agent parses through, and it
handles the shapes models actually produce rather than the one the prompt asked
for: the object, a bare array (callers name the key to wrap it under), an
answer in a code fence, an answer with conversational padding around it, and —
the one that caused real damage — an answer the model ran out of tokens partway
through. A truncated array parses nowhere, and a naive scan for the first `{`
finds the array's *first element* and returns it as the whole answer. Complete
objects are salvaged out of it instead, so eight of nine scenes survive rather
than one.

---

## 4. Research and sourcing

Research is the substance of the product, so it is grounded on things that can
be checked, not on what a model recalls.

`providers/research/grounding.py` searches three indexes, none of which needs a
key: **Wikipedia** for the shape of a subject, **OpenAlex** for the academic
record with DOIs, **GDELT** for contemporary coverage. An index that is down
returns an empty list, so a failed lookup narrows the brief rather than ending
the run.

`providers/research/trending.py` answers the other question — what to make at
all — from Wikipedia readership: which articles about a niche are being read,
and which are being read *more than usual*. An article has to clear a floor of
real readers before its trend counts, because one reader becoming two is up a
hundred per cent and is not a story.

**The sources that ship are the ones that were fetched.** The synthesis model
contributes facts, matched by URL onto sources that really exist; a URL nobody
fetched is dropped. A hallucinated citation in a description that invites a
viewer to check the work is worse than no citation.

`crosscheck.py` finds where sources disagree. Claims carry the source that made
them into fact-checking, and figures reported twice with different numbers are
marked disputed deterministically — using the chart builder's own parser, so
"≈ 45 metric tonnes" and "60 tonnes" are compared as amounts. A disputed claim
is neither verified nor flagged: it is a third thing, and the script can say
"sources differ" instead of picking one.

---

## 5. Visuals

The order of preference is **real footage first, generated last**, because a
photograph of the thing beats a picture of something like it.

### Stock, and why it needs checking

The stock libraries answer every query. Asked for "chart gold production 1910s
Kolar peak 1919", Pexels reports eight thousand results and returns a
cryptocurrency trading desk. `providers/visual/matching.py` compares the hint
against the words the library itself attaches — Pexels' page slug, Pixabay's
tags, a Commons filename — and nothing relevant means no result, which sends
the shot down the chain to generation.

Proper nouns are not required to match: a hint carries a company acronym, a year
and a place name no stock library has heard of. But a word naming a *kind* of
thing — map, chart, diagram — has to appear, because a photograph of Karnataka
is not a map of it. That rule also routes map hints to Commons by itself, since
no Pexels slug says "map".

### Generation

`providers/visual/generated_provider.py`, last in the chain. Backends in order:
Cloudflare Workers AI (FLUX.1-schnell), Gemini (needs billing, off by default),
Pollinations (keyless, the fallback).

- **`art_direction.py`** writes a camera brief rather than passing the subject
  through. A film stock, a lens, a light, a place in the frame, a flaw. Left to
  itself the model makes the same photograph every time — subject centred, sun
  low behind it — and twenty of those is what makes a video announce itself.
- **`quality.py`** decides whether a return is a photograph or a soft smear,
  and ranks candidates, because the same brief on two seeds returns both.
- **`relevance.py`** asks a vision model whether the frame is of the right
  thing. It scores rather than vetoes; a gate strict enough to insist would
  reject everything and leave the scene blank.
- **`filmic.py`** finishes what survives: scaled to the frame, halation,
  chromatic fringing, EXIF stripped. It deliberately does **not** grade — see
  §6.

**Documents are refused, not generated.** Asked for an official closure notice
the model produces a sign reading `OFFICIALT NOTICE / CLOSED / LLGML 2001` over
a line of garbled English; asked for a production chart it produces a table of
invented figures. The garbled lettering is the smaller half of the problem. The
larger half is a fabricated official record about a real company, presented to
a viewer as evidence, in a video whose whole claim is that its sources can be
checked. No prompt fixes that, because the subject *is* the document. The shot
is asked for again as the place rather than the paperwork.

`charts.py` fills the hole that leaves, building a chart from the run's own
researched figures — but only when two or more of them share a unit and sit
within sight of each other. A chart of unrelated quantities looks authoritative
and means nothing, which is the invented table again in a tidier font.

---

## 6. The edit, and how it is rendered

`timeline.py` is the edit decision list: shots with their sources, in-points,
fit and motion; overlays; transitions; captions; audio tracks with keyframed
gain. It validates itself — a timeline that does not tile the video exactly is
a bug caught before a frame is rendered.

`style_profile.py` holds the knobs that decide *how* a video is cut: cut rhythm,
motion intensity, graphics density, transition weights, music levels, narration
pace. Every field is a number or a small enum, deliberately, because these are
meant to be measured off real reference videos rather than written by hand.

`timeline_builder.py` turns a run's state into a Timeline. A scene that found
no footage of its own borrows from the rest of the run rather than holding a
flat colour card — returning to a shot the video has already used is ordinary
B-roll; a coloured rectangle is a missing picture.

### Motion

`render/motion.py` builds the moves. Travel is a **rate per second** capped by
the style, so a two-second cut does not travel as far as a seven-second one. A
third of moves are drifts inside a crop that never show the whole frame.
Consecutive shots avoid continuing the previous direction, across scene
boundaries as well as within them.

`render/parallax.py` moves a still as a scene rather than as a card, using a
depth map from `providers/visual/depth.py` (Depth Anything V2 Small, ~1.4s on
CPU, cached beside the picture). The warp is **continuous**, not plane-based:
planes were built first and are wrong for this material, because a mine
headframe is a lattice spanning most of the depth range, so every threshold ran
through the middle of it and the halves slid apart. Displacement is a
multiplier on the move, so a shot holding still is not warped, and it is kept
small because an estimated depth map is not smooth along a straight edge and a
warp bends straight steel to match it.

### One look over everything

`render/grade.py` grades every frame to a single look at encode time. A run
cuts stock footage against generated stills against Commons photographs, each
with its own colour, contrast and grain, and the picture changing character at
every cut is most of what makes an edit feel assembled rather than filmed.

It is an ffmpeg filtergraph for two reasons: it has to reach stock footage,
which nothing in the asset pipeline touches, and the same work in Python
measured 75ms a frame — four and a half minutes added to a two-minute video.

Order in that graph is not cosmetic. The lift on the blacks comes **last**,
because `eq` round-trips through limited-range YUV where black is 16 rather
than 0, so a lift applied before it comes back as zero, and the vignette then
multiplies what is left towards nothing.

---

## 7. Storage

`paths.py` owns every location. Nothing is written into the checkout.

```
projects/   one folder per video: state, timeline, voice, output   keep
library/    voice profiles and style profiles                      keep
cache/      footage, music, models, depth maps                     disposable
config/     credentials                                            secret
tmp/        scratch, cleared on startup                            disposable
```

`asset_cache.py` is content-addressed, so the same clip is never downloaded
twice and a re-run of the visual stage costs nothing for what it already has.

`studio.py` is the housekeeping CLI. Its garbage collector will not touch a run
that is still in flight — `paths.in_flight()` answers that across processes,
because `paths.active_run()` is thread-local and a `gc` in its own process
cannot see another process's open run. It learned this the hard way, by
deleting a live project's voice track between the voice stage and assembly.

---

## 8. Interfaces

Four front ends, one backend, no duplicated pipeline logic.

- **CLI** (`main.py`) — blocking `run()`, prompts at gates.
- **Telegram bot** (`bot_main.py`) — full runs from chat: `/newvideo` collects
  everything by reply and inline button, a voice note becomes a cloned profile,
  the finished video arrives as an upload.
- **Web app** (`web/server.py`) — FastAPI. Dashboard, live run view, voice
  studio, clips.
- **The room** (`room/`) — a 3D studio where each agent is a desk. Work arrives
  over SSE from `runlog.py`, and the one screen that talks to a human carries
  every gate — and, when a run finishes, the video itself.

There are two ways a front end answers a gate, and which one it uses follows
from whether it can block.

`interfaces/base.py` defines `ApprovalHandler` — `request_approval`,
`request_edit`, `notify` — implemented by the CLI and the Telegram bot, both of
which drive `PipelineManager.run()` and can sit inside a blocking call waiting
for an answer.

The web app and the room cannot: a request has to return, and a browser has to
stay responsive. They drive `PipelineManager.step()` instead, which surfaces
the gate as a payload and takes the decision back through
`POST /api/runs/{id}/decision`. Either way `manager.py` knows nothing about
which one is listening.

There is also a Streamlit prototype (`studio_app.py`) from before the web app
existed. It still runs; it is not where the work goes.

`runlog.py` is the activity bus. Every agent call goes through
`_run_agent_with_retry`, which is the single place that announces work, so the
room sees all of it and none of it has to be plumbed per agent.

---

## 9. Testing

`pytest`, no network in the suite. The rule the tests follow is that a test
should fail for the reason it is named after — several here exist because an
earlier version of the same test passed while the bug was still present, and
the docstring says so where that happened.

Two examples worth knowing about, because they shape how the rest are written:

- The chart-placement test first measured average brightness per half-frame and
  passed with the chart rendering half off screen, because the shot underneath
  is not black and the mistake averaged away. It measures where the bars land
  now.
- The stillness tests measure movement after averaging away high frequencies,
  because the finished video carries grain that changes every frame on purpose,
  and a plain per-pixel difference counts that as motion.
