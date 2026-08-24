# Santa Studio — Product Spec

_What we are building, in the words it was asked for, and how much of it
stands up today. `ROADMAP.md` is the engineering plan and stays the source of
truth for schemas and phase history; this file is the product brief and the
status board. When something here gets built, it gets ticked here._

_Last audited: 24 Aug 2026._

---

## 1. The thing in one paragraph

A faceless research-video studio that takes a topic — given, or found — plus
optional reference channels, and produces a finished, published YouTube video
in the owner's own cloned voice. The research is deep and the sources are
verifiable, because these videos take positions on things people argue about.
The visuals are licensed for commercial use or generated. The quality bar is
Nitish Rajput / Ankit Awasthi / Dhruv Rathi: a viewer should finish a
half-hour video feeling they invested it, not spent it, and should come back
for the next one. Nothing is copied from anyone — references teach structure
and pacing, never content.

---

## 2. The run, end to end

The pipeline already has these as real states (`manager.py: STATE_SEQUENCE`).
This is what each one owes the product.

| # | Stage | What it must do |
|---|-------|-----------------|
| 1 | **TOPIC_SELECTION** | Take the owner's topic and any notes attached to it. If there is no topic, go find what people are actually searching for right now and propose one. |
| 2 | **REFERENCE_ANALYSIS** | Take one or more reference channels/videos. Study how they are *built* — hook shape, pacing, section order, tone, how they hand off between beats. Extract patterns. Never content. |
| 3 | **RESEARCHING** | A lot of research, from more than one kind of source. Numbers, chronology, causal chains, and the disagreements — not a summary. |
| 4 | **FACT_CHECKING** | Score every claim. Isolate the unverified ones. Attach each surviving claim to the source that carries it. |
| 5 | **SCRIPTING** | Write to the reference standard, in the owner's voice and register. Structure comes from stage 2, substance from stages 3–4. |
| 6 | **VOICE_GENERATION** | Narrate in the owner's cloned voice. Captions timed off the audio that ships. |
| 7 | **VISUAL_SELECTION** | Find footage, maps, and stills that are licensed for commercial use. Where nothing suitable exists, generate it — and it has to look real. |
| 8 | **VIDEO_ASSEMBLY** | Cut it. Overlays, transitions, music, mix. |
| 9 | **SHORTS_EXTRACTION** | Pull the clips for Shorts / Reels / Twitter. |
| 10 | **THUMBNAIL** | Variants with hook text. |
| 11 | **YOUTUBE_PUBLISH** | Upload, with a description that carries the sources as verifiable links. |

---

## 3. The quality bar

- **Reference-level, not reference-derived.** The output should sit next to
  the reference channels without embarrassment and without resemblance.
- **Half an hour invested, not wasted.** Retention comes from substance and
  pacing, not from tricks.
- **Habit-forming.** A consistent voice, a consistent standard, a reason to
  come back.
- **Nothing copied.** Enforced at the prompt level in `reference_agent`, not
  merely documented.

---

## 4. Sources, and why they matter more here

Research videos on contested subjects live or die on sourcing. So:

- Every claim that survives fact-checking carries the source that supports it.
- Sources are **documented as a deliverable**, not just used internally.
- The published description carries them as **verifiable links** a viewer can
  click and check.
- Where a claim could not be verified, it does not go in the script.

---

## 5. Visuals: licensed first, generated second

Order of preference:

1. **Stock, commercially licensed** — Pexels, then Pixabay, then Wikimedia.
2. **Generate it** — only where the search genuinely fails. Maps, diagrams,
   period scenes, anything specific enough that stock will never have it.

Generated material has to look real, not "AI-looking".

### What is actually free (checked 24 Aug 2026)

**Images — this is a solved problem, and free.**

| Option | Free allowance | Notes |
|--------|----------------|-------|
| **Google Gemini API** — Nano Banana (Gemini 2.5 Flash Image) | **500 images/day, 1024×1024, no card** | **We already have `GEMINI_API_KEY` configured.** Nothing new to sign up for. This is the recommendation. |
| Cloudflare Workers AI | 10,000 neurons/day, no card | SDXL / FLUX Schnell. Good second fallback when the daily Gemini quota runs out. |
| Self-hosted FLUX.1-schnell | Free forever (Apache 2.0) | Needs 20–30 GB of disk. **Not viable right now — the disk is at 95%.** |

Nano Banana **Pro** (Gemini 3 Pro Image) has no free API tier at all — 0 RPM,
0 RPD. Don't design around it.

**Video — be honest: there is no free API.**

You had heard right that Google Flow gives something away, but it is a
consumer product, not an API: 50 credits/day in the Flow UI and 10 Veo 3.1
generations/month per Google account. A human clicks those; a pipeline cannot.
The Veo API through Gemini/Vertex has **no free tier** — it is $0.03–$0.50 per
second of output, and clips cap at 8 seconds.

**So the plan is not AI video.** It is: generate stills for free, and move
them in the renderer — slow push-ins, parallax, map draw-on, chart builds,
match-cut stills. Which is what the reference channels are doing anyway. Watch
Dhruv Rathi or Nitish Rajput frame by frame: it is overwhelmingly stills,
maps, charts, archival and motion graphics, not generated video. Buying Veo
would not move us toward that standard; a better motion system would.

If a specific shot ever genuinely needs generated video, that is a per-shot
paid decision, made deliberately — not a pipeline default.

---

## 6. Stopping and resuming

Any stage can die: the network drops, an API quota is exhausted, a provider
returns nonsense.

- The run **stops where it is**. It does not thrash and it does not fake a
  result.
- The state on disk is **complete up to that point**.
- Next time, the owner picks: **continue from there**, or **start fresh**.
- Long stages should not throw away the work they had already finished inside
  themselves.

---

## 7. Status board

Legend: `[x]` done and proven · `[~]` built but unproven or partial · `[ ]` not built.

### 7.1 The spine

- [x] Eleven-state pipeline with gates (`manager.py`)
- [x] State persisted as JSON after every state (`state.py`)
- [x] Two review modes — autonomous, and checkpoints after research/script
- [x] Live activity bus: agents report as they work, SSE to the room
- [x] Telegram bot control (`bot_main.py`), Streamlit dashboard, web room
- [x] Proven end to end on a real run — Kolar Gold Fields, 495s wall clock

### 7.2 Topic

- [x] Owner's topic is taken as given, with notes
- [ ] **Trending-topic discovery.** Today `topic_agent` asks an LLM to invent
      three topics for a niche. That is a guess dressed as research — it has
      no idea what anyone is searching for. Needs real trend data.

### 7.3 References

- [x] Multiple reference URLs accepted
- [x] Structure-and-style-only extraction, enforced in the prompt
- [x] Style Profile drives downstream stages
- [ ] **Reference transcripts are never actually read.** `ingest.py` asks
      yt-dlp for subtitles, finds them, and then breaks out of the loop
      without ever reading them — `transcript_text` is always `""`. So the
      analyser has only ever seen the title, description and tags. The single
      highest-value fix on this list: it is the difference between analysing a
      video and analysing its metadata.

### 7.4 Research and verification

- [x] Research swarm — parallel specialist roles
- [x] Wikipedia grounding, searched on the *subject* rather than the sentence
- [x] Fact-check agent with confidence scores and per-claim citations
- [ ] **Sources are Wikipedia and nothing else.** Not enough for contested
      material. Needs news archives, primary documents, official statistics.
- [ ] **Source cross-checking** — a claim that appears in one source and
      contradicts another should surface as disputed, not get averaged away.
- [ ] **A sources document as a deliverable** — written out per run.
- [ ] **Sources in the published description.** `draft_metadata()` writes 3–5
      LLM sentences and no links at all. The verifiability promise is
      currently not kept.

### 7.5 Script

- [x] Scene-structured script from research + style profile
- [x] Hinglish support — Devanagari spoken, Latin captions

### 7.6 Voice

- [x] gTTS, XTTS, Chatterbox providers; profiles; filter presets
- [x] Captions aligned against the audio that ships, not the raw take
- [x] Synthesis chunk spans used as the caption clock — measured, not
      transcribed, which is what Hinglish needed
- [~] **Chatterbox end-to-end** — the bridge runs; the 3 GB model is
      downloading. Unproven until a real clone comes out of it.

### 7.7 Visuals

- [x] Pexels → Pixabay → Wikimedia fallback chain
- [x] Subject-aware crops for vertical
- [ ] **AI image generation when stock fails.** Nothing exists yet. Gemini /
      Nano Banana, 500/day, on the key we already have.
- [ ] **Maps and data animations.** Named as a requirement; there is no map
      renderer and no chart builder.
- [ ] **A real motion system for stills.** Since generated video is off the
      table, this is what carries the visual standard: push-ins, parallax,
      draw-on, builds.
- [ ] Counter overlay animates its tick-up (today it draws the final number)
- [ ] `whip` and `speed_ramp` are real (today both dissolve)

### 7.8 Assembly and output

- [x] Timeline/EDL, overlays, transitions, music direction, SFX
- [x] Loudness-normalised master (-14 LUFS measured)
- [x] Shorts / Reels / Twitter extraction with per-platform caps
- [x] Thumbnails with hook text
- [x] Clips track: engine, ranking, HTTP API, browser UI, downloads

### 7.9 Publishing

- [x] YouTube OAuth flow a browser can complete
- [x] Dry-run upload path exercised
- [ ] **A live upload to a real account.** The oldest unproven claim in the
      project. Blocked on an OAuth client secret, which cannot be checked in —
      **this one needs the owner, not the code.**

### 7.10 Resumability

- [x] State saved after every completed stage
- [x] A failed stage saves state and halts with a resumable run id
- [x] Resume from the CLI, the bot, and the dashboard
- [ ] **Partial progress inside a long stage is lost.** A research swarm that
      finishes five specialists and dies on the sixth re-runs all six. Same
      for a visual stage that has downloaded eighteen of twenty clips.
- [ ] **Quota exhaustion is not distinguished from failure.** An API limit
      should park the run and say so, not burn the one retry and halt as if
      the provider were broken.

---

## 8. What is needed from the owner

1. **A Google OAuth client secret** (Desktop app, YouTube Data API v3
   enabled) — the only thing standing between us and a proven publish.
2. **Confirmation on the reference channels** to profile against.
3. Nothing else. The Gemini key already on this machine covers image
   generation; Pexels and Pixabay keys are already configured.

---

## 9. Order of work

Ranked by what buys the most quality per unit of effort.

1. **Fix the reference transcript bug** — one function, and it turns reference
   analysis from metadata-guessing into the real thing.
2. **Sources into the description**, plus a per-run sources document — this is
   a promise currently being broken.
3. **Widen research past Wikipedia** — the substance ceiling.
4. **AI image generation on the Gemini key** — closes the visual gap for free.
5. **A motion system for stills** — this is what actually reaches the
   reference standard, now that generated video is ruled out.
6. **Trending-topic discovery** — real data instead of an LLM's guess.
7. **Live YouTube publish** — as soon as the secret exists.
8. **Intra-stage checkpointing and quota-aware halting.**
9. Counter animation, real whip/ramp, timeline editor in the browser.
