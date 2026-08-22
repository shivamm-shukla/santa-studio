# Santa Studio — handoff

State of the project as of 22 Aug 2026, for picking the work up elsewhere.

Seven commits landed this session (`8a144a5..f3ccee6`), all on `main`,
none pushed. `git log --oneline a9711a7..HEAD` lists them.

---

## What the pipeline does now

```
IDLE → TOPIC_SELECTION → REFERENCE_ANALYSIS → RESEARCHING → FACT_CHECKING
     → SCRIPTING → VOICE_GENERATION → VISUAL_SELECTION → VIDEO_ASSEMBLY
     → [GATE: video ok?] → THUMBNAIL → [GATE: ready to publish?]
     → YOUTUBE_PUBLISH → DONE
```

The last three stages are opt-in: `ACTIVE_PROVIDERS["publish"]` defaults to
`None`, and `manager._next_state()` skips both publish states, so a run
ends at DONE holding the finished file. Thumbnails are generated either
way.

A full run produces a real captioned mp4. Verified end to end twice.

---

## What works

**Hinglish output** (`0f677d4`). `config.OUTPUT_LANGUAGE` (default
`"hinglish"`) drives every viewer-facing agent from one place.

The awkward part is that Hinglish splits between what is read and what is
heard. Latin script is what Hindi speakers type, but TTS pronounces
romanised Hindi as English and it is unintelligible. Devanagari on screen
would drag a font dependency through captions, thumbnails and titles.

So `script_agent` emits **both** per scene:
- `text` — Latin script, for captions/thumbnails/titles
- `spoken` — Devanagari, for the voice only
- `visual_hint` — stays English, it is a stock-footage search query

Captions therefore cannot come from Whisper (transcribing Hindi audio
returns Devanagari). `voice_agent` re-spreads the audio duration over the
Latin words, and the assembler uses those stamps for any non-English run.

`language` is part of the `VoiceProvider` / `CaptionProvider` contracts,
not a provider-local default.

Research deliberately stays English — the sources are English, and
translating facts on the way in risks distorting them.

**Thumbnails** (`340470e`). `agents/thumbnail.py` produces three variants:
different LLM-written overlay text, crop anchor and layout (bottom bar,
left block, centre punch). Sources its base image through the existing
`VisualProvider.search(query, asset_type="image")` — no provider change
was needed. Nothing in it can fail the stage: LLM falls back to
topic-derived text, missing image falls back to a dark canvas.

**Speed.** Measured on a real 763-word script:

| Stage | Before | After |
|---|---|---|
| VOICE_GENERATION | 5+ min | 14s |
| VIDEO_ASSEMBLY | 133s | 29s |
| VISUAL_SELECTION | 61s | 15s (uncontended) |

- gTTS ran one HTTP round-trip at a time. Now split on sentence boundaries
  (never mid-sentence, or concatenation leaves an audible seam) and
  requested concurrently.
- Scene footage downloads overlap instead of queueing.
- x264 was on its default preset, single core → `veryfast` + real thread
  count. Bigger file, much shorter wait; YouTube re-encodes anyway.
- Whisper is skipped entirely for non-English runs.

---

## Real bugs found and fixed

**Silent videos passed as success** (`f3ccee6`). A run produced a
24-second video with no audio and no captions and reported success:

```python
total_duration = audio_clip.duration if audio_clip else len(scene_assets) * 4
```

Six scenes × 4s = exactly the 24 seconds that came out. Captions sat
inside `if audio_clip:` so they vanished too. Assembly now raises when the
voice track is missing, and `VOICE_GENERATION`'s validator checks the file
exists rather than trusting a non-empty path string.

**The download cache never worked** (`897c284`). Asset filenames embedded
`hash(url)`, and Python randomises string hashing per process — the same
clip got a different filename on every run. Verified: one URL gave `66589`
then `59089`. Now md5. Downloads land on `.part` first so an interrupted
one cannot leave a truncated file the cache then trusts forever.

**Oversized stock downloads** (`897c284`). Pexels returns several
renditions; the picker only looked at width, so a 60fps master could beat
a 30fps file. Output is 1280×720 @ 24fps — anything wider or smoother was
downloaded then discarded. Now ranked by closeness to what is actually
used.

**A status poll could resurrect a killed run** (`9143404`). `RUNS`/`STATUS`
are in-process, so a server restart orphaned in-flight runs and the page
polled a 404 forever. Rehydrating inside `GET /status` fixed that and
introduced worse: a run could no longer be stopped — any open tab's next
poll silently restarted the pipeline, downloads and all. `GET` now reports
`stalled` without driving; the run page offers a Resume button. `POST
/decision` still resumes, since that is an explicit action.

**Gate decisions blocked the Telegram poll loop** (`076e4e0`, earlier).
`regenerate` re-ran a whole agent on the getUpdates thread.

**XTTS could not load at all** (`8a144a5`). transformers 5.x dropped
`pytorch_utils.isin_mps_friendly` which coqui-tts 0.27 imports; torch 2.9+
needs torchcodec. Both pinned. The model was also being reloaded per agent
call (registry builds a fresh provider each time) — now cached on the
module. Coqui's interactive licence prompt would have hung the bot and web
server forever; `COQUI_TOS_AGREED` records it instead.

**No voice sample halted the run.** Selecting no profile left cloning with
nothing to clone. All four interfaces now fall back to the non-cloning
provider, and the bot's button says "generic voice, no cloning" so the
swap is visible.

---

## What does not work / not done

**Voice cloning is not installed.** This is the big one.

XTTS-v2 is the project's original choice but its weights are **CPML —
non-commercial**. A monetized channel is commercial use, so it is ruled
out. Verified alternatives:

| Model | Code | Weights | Commercial |
|---|---|---|---|
| XTTS-v2 | MPL | CPML | ❌ |
| F5-TTS | MIT | CC-BY-NC | ❌ |
| **Chatterbox** (Resemble AI) | MIT | **MIT** | ✅ |

Chatterbox is the right choice — MIT weights, zero-shot cloning from a
short reference. `pip install chatterbox-tts` **failed** after ~4 hours:
it pins `torch==2.6.0` (a 766MB wheel, a downgrade from the installed
2.13) and the download timed out:

```
ReadTimeoutError: HTTPSConnectionPool(host='files.pythonhosted.org'): Read timed out.
```

Nothing was broken by the failure — torch is still 2.13, whisper and
moviepy still import. **Retry on a faster connection**, and note it needs
~3GB free (disk was down to 3.3GB).

Current voice is gTTS: free, no key, but one fixed voice that ignores the
uploaded sample entirely.

**Research is not grounded.** `agents/research_agent.py` has a
`TODO: wire the web_search server tool`, and its prompt literally asks the
model for "a plausible url". The URLs happen to resolve, but nothing
verifies the page supports the claim. **Do not publish these as sources**
— fabricated citations are worse than none. This blocks the "Google Doc of
sources in the description" idea, which otherwise has all the data it
needs (`research.sources` already carries title/url/key_facts).

**YouTube publish is a skeleton.** `agents/youtube_publish.py` has working
`draft_metadata()` (title/description/tags via the existing LLM provider,
drafted *before* the gate so it can be edited there). `run()` calls
`get_provider("publish", config)` — that provider does not exist yet.
Needs OAuth2 installed-app flow with a cached refresh token.

Two things to know before building it:
- Videos uploaded via `videos.insert` from API projects unverified since
  28 Jul 2020 are **locked to private** until the project passes a
  compliance audit, which takes weeks. Plan for private upload + manual
  flip to public.
- Quota is 100 uploads/day.

**Interfaces do not render the publish gate.** The state machine supports
`AWAITING_PUBLISH`, but CLI, Telegram and web only handle
`AWAITING_APPROVAL`. Harmless while publishing is off.

---

## The actual quality problem

This is what to fix first, and it is not a bug.

Script, voice, captions, timing and assembly all work. **The footage does
not match the content.** For "Tipu Sultan's rockets", the queries the LLM
wrote were good — "18th century Indian soldiers army historical", "antique
iron rocket weapon museum" — but Pexels has no 18th-century Indian battle
footage. It returns whatever loosely matches. The result had Napoleonic-era
European reenactors firing muskets.

The filenames actively mislead here: `download_asset` names files from
*our query*, not the video's content, so
`18th-century-indian-soldiers-army-histor-75936.mp4` may contain nothing
of the sort.

Keyword stock search is the ceiling on quality right now. Options:

1. **AI image generation** for scenes stock cannot cover — best fidelity,
   needs an image provider behind the existing `VisualProvider` interface.
2. **Wikimedia / archive.org** — real historical paintings and photos,
   free, good for history topics specifically.
3. **Pick topics stock footage covers** — tech, science, business, health
   all have deep libraries. Cheapest way to see the rest of the pipeline's
   real quality.

Anything else — better voice, faster runs, auto-publish — is polish on top
of footage that does not match the words.

---

## Running it

```bash
cd santa-studio && source venv/bin/activate
uvicorn web.server:app        # do NOT use --reload; it kills in-flight runs
```

Also: `python main.py` (CLI), `python bot_main.py` (Telegram,
@santa_studio_bot), `streamlit run studio_app.py`.

`.env` has working keys for Gemini, Groq, Pexels, and Telegram.
`PIXABAY_API_KEY` and `ANTHROPIC_API_KEY` are empty and unused (LLM is the
free Gemini → Groq fallback chain).

Do not delete anything under `runs/` while a run is in flight — that is
what caused the 24-second silent video.
