# Santa Studio — Product Spec

_What we are building, in the words it was asked for, and how much of it
stands up today. `ROADMAP.md` is the engineering plan and stays the source of
truth for schemas and phase history; this file is the product brief and the
status board. When something here gets built, it gets ticked here._

_Last audited: 25 Aug 2026 — see §0 for where the last run left things._

---

## 0. Where things stand — 25 Aug 2026

Picking this up cold? Read this first.

**A full run finished.** Topic to master, 19 minutes wall clock, 110 seconds of
video, `DONE`. Project
`2026-08-25_why-the-kolar-gold-fields-mines-were-shut-down_b1387ed5`.

**What that run proved.** The chart builder found the comparison the story
actually turns on, unprompted: $500 an ounce to dig the gold out against $350
an ounce to sell it, picked out of eleven researched figures in four
incompatible units. Stock footage is now checked against the hint. Documents
and charts are refused rather than invented. Transitions, counters and motion
all landed.

**What it exposed, all three now fixed.** The chart rendered half off the
bottom of the frame. Three of seventeen shots were flat colour cards. A `gc`
run deleted an in-flight project out from under the pipeline.

### Open, in the order they matter

1. **The Cloudflare image quota was spent on 25 Aug and resets daily.** This is
   the first thing to check on a fresh day, because it silently changes what
   the visuals look like: generation falls back to the keyless service, whose
   output often fails the quality gate, which is what left three shots with
   nothing of their own. The run log says "Image generator is out of quota;
   falling back" when it happens. **A run done on a fresh quota has not been
   watched back yet** — that is the next thing to do.
2. **Disk is the standing constraint.** 2.6 GB free after a clean-up on 25 Aug.
   `~/.cache/whisper/medium.pt` is 1.5 GB of that and can go if captions can
   live with `base` (noticeably worse on Hindi — the owner's call, not made).
   `venvs/chatterbox` is 1.7 GB and must stay; the cloned voice runs on it.
3. **Maps.** Refused for the same reason as charts and with nothing to take
   their place yet. §7.7.
4. **A live YouTube publish.** Still the oldest unproven claim, still blocked
   on the OAuth secret. §8.

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

## 2b. Two products, one run

Shorts is its own product. It lives inside the same run rather than beside it,
because the long video is what it is cut from.

The shape of it, in the room:

1. The long video finishes. On the LED screen by the ludo table, two things
   appear: **Publish to YouTube**, and **Download**.
2. Publishing is a choice, not a step. The owner may publish, download, or
   both — and may do neither and still go on.
3. From there, a second choice: **cut shorts from this video**. That drops the
   run into the Shorts pipeline, which finds the moments worth cutting and
   renders them.
4. Each short then gets the same treatment as the long video, per platform:
   **publish where we support publishing, download where we do not.** If a
   platform cannot be posted to from here, the short is still rendered to that
   platform's exact format so the owner can post it by hand.

The download path is not a fallback we apologise for — it is how every
platform we do not hold credentials for gets served, and it should feel as
finished as publishing does.

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

**Corrected 24 Aug 2026, after testing against the real key.** The published
"500 free images/day" figure did not survive contact with our own project:
every Gemini image model returns

    429 RESOURCE_EXHAUSTED ... limit: 0, model: gemini-2.5-flash-preview-image

`limit: 0` is not a spent allowance — it is no free allowance at all. Gemini
image generation needs billing enabled. It is wired up and stays switched off
behind `GEMINI_IMAGE_ENABLED`.

| Option | Cost | Status |
|--------|------|--------|
| **Pollinations** | Free, **no key, no account** | **Fallback**, for when Cloudflare fails or its day's neurons are spent. See below for what it does and does not do. |
| **Cloudflare Workers AI** | Free, free signup, no card | **In use and proven.** FLUX.1-schnell (Apache 2.0), 10,000 neurons/day. Leads the chain; the keyless service is now the fallback under it. Fixed 1024×1024 — it refuses `width`, `height` and `seed` outright. |
| Google Gemini image | Needs billing on the Google Cloud project | Implemented, off by default. Set `GEMINI_IMAGE_ENABLED=true` once billing is on. |
| Self-hosted FLUX.1-schnell | Free forever (Apache 2.0) | Needs 20–30 GB of disk. **Not viable — the disk is at 95%.** |

**Corrected 25 Aug 2026, after probing Pollinations directly.** Two things
that were being assumed are not true:

- **The `model` parameter is accepted and ignored.** Requests for `flux`,
  `sana` and no model at all came back byte-identical, and every response is
  tagged `Make: sana` in its EXIF. `/models` lists one model for an anonymous
  caller. Samples in `samples/` once named `_flux` were never flux.
- **The requested size is a suggestion.** Asking for 1280×720 returns
  1024×576, which then gets scaled into a 1080p timeline.

Returns also carry the full prompt and the model name in EXIF — a label saying
how the picture was made, inside a file that ships in a published video. That
is stripped now.

So the free tier's quality is a fixed ceiling, and the work went into getting
the most out of it: a written camera brief, several seeds with the best one
kept, and a finishing pass. Cloudflare's FLUX.1-schnell is the next real step
up and costs a free signup.

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
- [x] **Reference transcripts are read.** json3/srv1/vtt, manual subtitles
      preferred over auto-generated, failed tracks fall through to the next.
      Before this, `transcript_text` was always `""` and the word count fell
      back to the *description* — which is what every style profile's
      words-per-minute, and so its entire pacing model, was derived from.

### 7.4 Research and verification

- [x] Research swarm — parallel specialist roles
- [x] Wikipedia grounding, searched on the *subject* rather than the sentence
- [x] Fact-check agent with confidence scores and per-claim citations
- [x] **Research is grounded on three indexes, not one.** Wikipedia for the
      shape of the subject, OpenAlex for the academic record with DOIs, GDELT
      for contemporary coverage — none of which needs a key. An index that is
      down narrows the brief rather than ending the run.
- [x] **The published sources are the ones we fetched.** `sources` used to be
      whatever the model wrote, with the grounded list as a fallback — so a
      description could carry an invented URL as a citation. The model now
      contributes facts, matched by URL onto sources that were really fetched;
      a URL nobody fetched is dropped.
- [ ] **Source cross-checking** — a claim that appears in one source and
      contradicts another should surface as disputed, not get averaged away.
- [x] **A sources document as a deliverable** — `sources.md` written beside
      the master file at fact-check time, carrying every source, the claims
      drawn from it, and separately the claims that were flagged and kept out
      of the script.
- [x] **Sources in the published description.** A numbered, clickable list
      appended under the drafted copy, inside YouTube's 5000-character limit
      and never truncated mid-link. It ships even when the LLM draft fails —
      it is the half of the description that needs no model.

### 7.5 Script

- [x] Scene-structured script from research + style profile
- [x] Hinglish support — Devanagari spoken, Latin captions

### 7.6 Voice

- [x] gTTS, XTTS, Chatterbox providers; profiles; filter presets
- [x] Captions aligned against the audio that ships, not the raw take
- [x] Synthesis chunk spans used as the caption clock — measured, not
      transcribed, which is what Hinglish needed
- [x] **Chatterbox end-to-end** — proven. 34s for a short take with the
      weights cached, a real cloned voice, captions timed against it. The
      library narrates itself on stdout, which is the JSON reply channel, so
      the work now runs with stdout redirected to stderr.

### 7.7 Visuals

- [x] Pexels → Pixabay → Wikimedia fallback chain
- [x] **Stock results are checked against what was asked for.** The libraries
      answer every query — Pexels reports eight thousand results for "chart
      gold production 1910s Kolar peak 1919" and returns a cryptocurrency
      trading desk — and the first result was taken unconditionally, so a
      finished video about a Karnataka gold mine carried a Binance chart and a
      Turkish military zone sign. `providers/visual/matching.py` compares the
      hint against the words the library itself attaches (Pexels' page slug,
      Pixabay's tags, a Commons filename); nothing relevant means no result,
      which sends the shot to generation. Deliberately strict: a loose but
      real match like "flooded quarry" for a flooded mine is refused too, on
      the grounds that a generated still of the right subject beats real
      footage of a different one — and that a nearly full disk should not
      carry downloads that will not be used.
- [x] Subject-aware crops for vertical
- [x] **Image generation when stock fails.** Last link in the chain, after
      Pexels/Pixabay/Wikimedia. Three backends: Cloudflare FLUX.1-schnell
      (implemented, unproven, needs a free account), Gemini (needs billing)
      and Pollinations (free, in use). Every failure path returns an empty
      asset_path rather than raising, because it is the end of the chain.
- [x] **A written camera brief per shot** (`providers/visual/art_direction.py`)
      — look, lens, light, framing, foreground and a flaw, varied per scene so
      a video's generated stills do not share one look. Measured: edge detail
      6 → 15 on the same subject. No golden hour, no film stock named, nothing
      that shrinks the subject — each of those rules is there because breaking
      it produced a bad frame we can point at.
- [x] **A quality gate and a pick** (`providers/visual/quality.py`) — detail,
      exposure and tonal range measured, several seeds tried, the best kept, a
      strong first result ending the search. Baked-in bars and print borders
      cropped.
- [x] **A finishing pass** (`providers/visual/filmic.py`) — scaled to
      1920×1080, halation, film toe, shadow-weighted grain, a pixel of
      fringing, corner falloff, EXIF stripped.
- [x] **A relevance check** (`providers/visual/relevance.py`) — the quality
      gate can tell a photograph from a smear and nothing more; it scored a
      lit tunnel and a colonial bungalow as strong frames when the brief asked
      for a mine headframe. A vision model now scores each candidate against
      the hint, which orders the candidates and refuses a plainly different
      subject. Image *understanding* is on the Gemini free tier even though
      image *generation* is not — the one useful asymmetry in that account.
      It scores rather than vetoes on purpose: asked outright, the model says
      no to every frame this generator produces, and a gate that strict leaves
      the scene blank. No key means no check and the ranking is what it was.
- [x] **Subject fidelity, once there is a model that can do it.** Same brief,
      same subject, measured 25 Aug 2026: FLUX.1-schnell scores 27.3 detail at
      1.0 relevance in 19s; the keyless service scores 13.9 at 0.2 relevance
      in 100s, and on the second shot every candidate it produced was refused
      as off-subject. The relevance check ranks what the generator gives it —
      it could not make the old one draw a winding wheel, and does not have to
      ask twice of this one.
- [x] **Documents and charts are refused, not invented.** Asked for "official
      closure notice BGML 2001 Kolar gold fields" the generator produced a
      sign reading OFFICIALT NOTICE / CLOSED / LLGML 2001 above a line of
      garbled English; asked for a 1919 production chart it produced a table
      of invented figures. The garbled lettering is the smaller half: the
      larger half is a fabricated official record about a real company, cut
      into a documentary whose whole claim is that its sources can be checked.
      No prompt fixes that, because the subject *is* the document. Those
      subjects are refused, and the shot is asked for again as the place
      rather than the paperwork.
- [x] **Data animations.** `charts.py` builds a bar chart from the run's own
      `numbers_and_data`, with the bars growing into place. It refuses far more
      often than it draws, on purpose: a chart is only made when two or more
      figures share a unit *and* sit within sight of each other, because 45
      tonnes of gold against 200,000 tonnes of ore share a word and nothing
      else, and a chart of unrelated quantities means nothing while looking
      authoritative — the invented table again in a tidier font.
- [x] **Maps come from Commons, not from a renderer.** Wikimedia carries real,
      correctly-labelled, freely-licensed maps — "India Karnataka relief map"
      — so the answer was routing rather than drawing. A hint naming a *kind*
      of thing (map, chart, diagram) now requires that word in the result's
      own description instead of merely outscoring it, which is what stops a
      photograph of a temple in Karnataka answering "map of Karnataka" — and
      which sends map hints to Commons by itself, since no Pexels slug says
      "map". Known cost: a Commons map whose filename does not say "map" is
      missed, and its categories come back empty, so there is nothing else to
      read.
- [x] **Motion that reads as a camera rather than an effect.** Travel is a
      rate per second capped by the style, so a two-second cut no longer moves
      as far as a seven-second one. A third of moves are drifts inside a crop,
      so the whole frame is not shown at one end of every shot. Consecutive
      shots avoid continuing the previous direction, across scene boundaries
      as well as within them. Fixed with it: a diagonal move applied the full
      pan to both axes and so travelled 1.41 times the ceiling `max_zoom` and
      `max_pan` claim to set.
- [ ] **Parallax, draw-on and builds.** Still not built. A push-in on a flat
      still is a move; separating a still into planes and moving them at
      different rates is the thing the reference channels actually do.
- [x] **Counter overlays count.** A quantity counts up to its figure and
      decelerates onto it; a year does not, because counting to 1902 from zero
      spins through four millennia to land on a date. A figure that arrives
      already finished is a caption of what was just said, which is not what
      the graphics layer is for.
- [x] **`whip` and `speed_ramp` are real.** A whip smears along its direction
      of travel and settles into place; a speed ramp opens fast and
      decelerates into real time. Both were crossfades wearing another name,
      so a profile weighting whips at a quarter of its cuts produced a video
      of dissolves.

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
- [x] Per-platform renders for YouTube Shorts, Instagram Reels and Twitter,
      each downloadable over HTTP (`clips/publisher.py`)
- [ ] **The publish/download moment in the room.** The LED screen by the ludo
      table should be where a finished video is published or downloaded, and
      where the run offers to cut shorts. Today that flow exists on `/clips`
      and the dashboard, not in the room.
- [ ] **Shorts publishing.** Clips renders every platform's format but can
      only *publish* to YouTube. Instagram and Twitter are download-only, and
      that is the right call for now — see §8.

### 7.10 Resumability

- [x] State saved after every completed stage
- [x] A failed stage saves state and halts with a resumable run id
- [x] Resume from the CLI, the bot, and the dashboard
- [ ] **Partial progress inside a long stage is lost.** A research swarm that
      finishes five specialists and dies on the sixth re-runs all six. Same
      for a visual stage that has downloaded eighteen of twenty clips.
- [x] **A busy minute is told apart from a spent day.** A free tier refuses in
      two ways and both were read as "out for the day", so one brush against a
      tokens-per-minute ceiling took a provider out until tomorrow — and a run
      halted reporting every provider failed while two of them would have
      answered thirteen seconds later. `providers/llm/backoff.py` reads the
      delay the provider states and waits for it when it is short, and only
      marks a provider spent when the refusal names a daily quota.
- [x] **A parked run.** A stage that stopped because a daily allowance ran out
      parks instead of halting: it does not spend its retry on a request that
      cannot succeed, it records when the allowance rolls over
      (`state.parked_until`), and it says it is out of allowance rather than
      broken. A per-minute ceiling deliberately does not park — the router
      already waits that out — and an ordinary failure still halts loudly.

---

## 8. What is needed from the owner

1. **A Google OAuth client secret** (Desktop app, YouTube Data API v3
   enabled) — the only thing standing between us and a proven publish.
2. **Confirmation on the reference channels** to profile against.
3. ~~A Cloudflare Workers AI account~~ — **done, 25 Aug 2026.** In `.env` and
   leading the visual chain.
4. Nothing else *required*. Pexels and Pixabay keys are already configured.

Deliberately **not** asking for:

- **Instagram direct publishing.** It needs an Instagram Business or Creator
  account linked to a Facebook Page, a Meta developer app, and review for the
  publishing permissions. That is a lot of account surface for one upload
  button. Reels get rendered to spec and downloaded instead.
- **Twitter/X direct publishing.** The free API tier does not usefully cover
  video posting. Same treatment: render to spec, download, post by hand.

Both become worth revisiting only if the manual step starts to hurt.

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
