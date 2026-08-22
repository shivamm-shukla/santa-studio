<div align="center">
  <img src="assets/logo/santa-studio-logo.svg" alt="Santa Studio" width="88" />

  # Santa Studio

  **An autonomous, multi-agent AI studio that turns a topic into a finished, captioned YouTube video** — research, script, cloned voice, visuals, and assembly, orchestrated end-to-end, with a human approving only where it actually matters.

  ![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
  ![FastAPI](https://img.shields.io/badge/FastAPI-web%20app-009688?logo=fastapi&logoColor=white)
  ![Claude](https://img.shields.io/badge/LLM-Claude-c2570c)
  ![Status](https://img.shields.io/badge/status-in%20development-e08a3c)
</div>

---

## What this is

Santa Studio is a personal project exploring **agentic pipeline design**: a
state machine orchestrates a chain of independent agents (research →
fact-check → script → voice → visuals → assembly), each one a pure
function with a strict input/output contract, with every external AI
capability (LLM, TTS, stock media, captions) swappable behind an
abstract provider interface — so replacing Claude with another model, or
Pexels with another stock library, is a one-line config change, not a
rewrite.

The same backend is exposed through **four different front ends** — CLI,
Telegram bot, a Streamlit prototype, and a fully custom FastAPI web app —
without duplicating a single line of pipeline logic between them.

## Screenshots

| Dashboard | Voice Studio |
|---|---|
| ![Dashboard](docs/screenshots/dashboard.png) | ![Voice Studio](docs/screenshots/voice-studio.png) |

**Run in progress** — animated stage tracker, live approval gate with real content (not a JSON dump):

![Run page](docs/screenshots/run-page.png)

## Highlights

- **Provider abstraction from day one.** Every AI capability (`LLMProvider`, `VoiceProvider`, `VisualProvider`, `CaptionProvider`) is an ABC resolved through a config-driven registry — agents never import a concrete implementation.
- **A pluggable human-in-the-loop layer.** The same `ApprovalHandler` interface backs a terminal prompt, Telegram inline buttons, and a web UI — approvals, edits, and regenerations work identically across all three.
- **A dual execution model.** `PipelineManager.run()` is a blocking loop for the CLI; `PipelineManager.step()` advances one unit of work at a time for callers that can't block on `input()` — the web app (which can't block a request) and the Telegram bot (which has to stay responsive to incoming updates while a run advances on a background thread).
- **Full pipeline from a chat window.** The Telegram bot is not just an approval channel — `/newvideo` collects niche, topic, length, voice profile, and review mode via replies and inline buttons, a voice note becomes a new cloned voice profile, `/runs` resumes an interrupted run, and the finished video arrives as a chat upload.
- **Persistent, reusable voice profiles.** Clone and filter a voice once — six mood-based filter presets (pitch-shift, EQ blend, tempo) — cache the result, reuse it across every future run instead of re-uploading per run.
- **Resumable by design.** Full pipeline state persists to JSON after every transition; a killed run picks back up exactly where it left off.
- **The edit is data, not a side effect.** Agents emit a timeline — every shot, motion path, caption and volume change written down — and a separate renderer turns it into a video. Re-rendering an adjusted edit costs no API calls, and the renderer can be swapped without touching an agent.
- **Free tiers, routed.** Four LLM providers behind one interface, with per-day quota tracked on disk so an exhausted provider is skipped rather than retried into failure.
- **Zero-friction local media pipeline.** No system `ffmpeg` install (or root access) required — resolved automatically via a pip-installed static binary.

## Architecture

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│  Interfaces │────▶│     Manager      │────▶│       Agents         │
│ CLI/Telegram│     │  state machine,  │     │ topic → reference →  │
│  /Web/(app) │◀────│  validate/retry, │◀────│ research → factcheck │
└─────────────┘     │  JSON persistence│     │ → script → voice →   │
                     └──────────────────┘     │  visual → assembler  │
                                               └──────────┬───────────┘
                                                          ▼
                                               ┌─────────────────────┐
                                               │      Providers       │
                                               │ LLM · Voice · Visual │
                                               │      · Caption       │
                                               └─────────────────────┘
```

- **`manager.py`** — the state machine. One agent per pipeline stage,
  output validation, retry-once-then-halt, JSON persistence after every
  transition.
- **`agents/`** — one function per stage, each following
  `run(input_data, config) -> {success, output, error}`.
- **`providers/`** — abstract interfaces + concrete implementations
  (Claude, XTTS-v2, Pexels/Pixabay, Whisper), resolved via
  `providers/registry.py`.
- **`interfaces/`** — `ApprovalHandler` implementations for CLI,
  Telegram, and the web app.
- **`web/`** — the FastAPI app: dashboard, live run view, and voice
  profile studio.
- **`timeline.py`** — the edit decision list. Agents describe the edit
  (shots, motion paths, captions, audio with keyframed levels, transitions)
  rather than calling the renderer, so an edit can be inspected, adjusted and
  re-rendered without spending a single API call.
- **`style_profile.py`** — the knobs that decide *how* a video is cut: cut
  rhythm, motion intensity, graphics density, music levels, narration pace.
- **`render/`** — turns a timeline into a file. MoviePy today, behind an
  interface so it can be replaced without touching an agent.
- **`paths.py`** / **`asset_cache.py`** — where everything is stored, and a
  content-addressed cache so the same clip is never downloaded twice.

## Tech stack

| Layer | Choice |
|---|---|
| Reasoning | Router across Gemini, Groq, Cerebras and OpenRouter free tiers (Claude optional) |
| Voice | gTTS by default; Coqui XTTS-v2 for cloning (non-commercial) |
| Voice filters | pydub (pitch shift, EQ, tempo) |
| Captions | OpenAI Whisper (local) |
| Stock visuals | Pexels, Pixabay, Wikimedia Commons |
| Edit representation | A timeline (edit decision list) the agents write and a renderer reads |
| Video assembly | MoviePy / FFmpeg |
| Audio mixing | pydub, with keyframed gain automation |
| Web backend | FastAPI |
| Bot interface | Telegram Bot API (raw, long-polling) |
| Frontend | Hand-written HTML/CSS/JS, no build step |

## Getting it running

You need Python 3.11 or newer. Nothing else has to be installed system-wide —
FFmpeg comes in through pip.

```bash
git clone https://github.com/shivamm-shukla/santa-studio
cd santa-studio
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then open `.env` and add at least one LLM key. All four options are free and
none of them asks for a card:

| Key | Where to get it | Free tier |
|---|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) | requests/day |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) | requests/day, very fast |
| `CEREBRAS_API_KEY` | [cloud.cerebras.ai](https://cloud.cerebras.ai) | tokens/day |
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) | several free models |

More keys is better — the router moves to the next provider when one runs out
for the day instead of stalling the run.

For visuals, `PEXELS_API_KEY` ([pexels.com/api](https://www.pexels.com/api/))
and `PIXABAY_API_KEY` ([pixabay.com/api/docs](https://pixabay.com/api/docs))
are both free. Without either, only Wikimedia Commons is available and the
footage will be thinner.

### Check the machine is ready

```bash
python studio.py doctor
```

This is the fastest way to find out what will and will not work. It checks
Python, FFmpeg, fonts, libraries, API keys, remaining daily quota, and free
disk — and every failing check prints the fix next to it.

If you are on Linux and plan to make Hindi or Hinglish videos, install a
Devanagari font or captions will render as empty boxes:

```bash
sudo apt install fonts-noto-devanagari     # Debian/Ubuntu
sudo pacman -S noto-fonts                  # Arch
```

### Start it

- **Web app:** `uvicorn web.server:app --reload` → `localhost:8000`
- **CLI:** `python main.py`
- **Telegram bot:** `python bot_main.py` (needs `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`)
- **Streamlit prototype:** `streamlit run studio_app.py`

Every provider fails cleanly — a clear error, not a crash — when its key is
missing, so voice filters, captions and video assembly are all testable before
any paid key is added.

## Where your files go

Nothing is written into the project folder. Everything lands in one place
outside it, so you can move or delete the checkout without losing your work:

| | Linux | macOS | Windows |
|---|---|---|---|
| | `~/.local/share/santa-studio` | `~/Library/Application Support/SantaStudio` | `%LOCALAPPDATA%\SantaStudio` |

Set `SANTA_STUDIO_HOME` in `.env` to put it somewhere else — an external drive,
for instance, since video adds up quickly.

It is laid out by how disposable things are, so you can tell at a glance what is
safe to remove:

```
projects/   one folder per video: state, timeline, voice, output   keep
library/    voice profiles and style profiles, reused everywhere   keep
cache/      downloaded footage, music, models                      safe to delete
config/     API credentials                                        secret
tmp/        scratch, cleared on startup                            safe to delete
```

Projects are named `2026-08-22_how-gravitational-waves-were-detected_f02d143b`,
so a plain directory listing is in date order and you can find one by reading it.

### Looking after it

```bash
python studio.py where              # every path, with its size
python studio.py ls                 # your projects: date, topic, state, size
python studio.py rm <project>       # delete one project
python studio.py clean --cache      # reclaim space; nothing precious is touched
python studio.py clean --orphans    # only footage no project still needs
python studio.py gc --keep 10       # keep the 10 most recent projects
python studio.py export <project>   # zip one up, credentials excluded
```

`<project>` can be an id fragment, a directory name, or part of the topic.

Upgrading from a version that kept everything in `./runs`? Run
`python studio.py migrate`. It copies rather than moves, so the old directory
is left intact until you have checked the result.

## Running the tests

```bash
pip install pytest
python -m pytest
```

### Choosing a voice

`ACTIVE_PROVIDERS["voice"]` picks between two very different things:

| | `gtts` (default) | `xtts` |
|---|---|---|
| Clones your voice | no — one fixed voice | yes, from a ~6s sample |
| Setup | none | `pip install 'coqui-tts[codec]'` + ~1.9GB model |
| Licence | free to use | **CPML — non-commercial only** |

`gtts` is the default because it is the only one that runs from a plain
`pip install -r requirements.txt`, so a fresh checkout reaches a finished
video without extra setup. It ignores uploaded voice samples entirely.

`xtts` does real cloning, but XTTS-v2's weights are licensed under the
Coqui Public Model License, which forbids commercial use — a monetized
channel counts. Set `COQUI_TOS_AGREED=1` to record agreement to that
licence before using it. **A permissively-licensed cloning provider is
being added for the monetized case** — Chatterbox, MIT weights; see
[ROADMAP.md](ROADMAP.md).

Interfaces fall back to `gtts` automatically when a run has no voice
sample or profile to clone from, rather than halting at
`VOICE_GENERATION`.

## Roadmap

Shipped:

- [x] Telegram bot parity with the web app (voice profiles, gates, full runs from chat)
- [x] Thumbnail agent — variant thumbnails to choose from at an approval gate
- [x] Shorts extraction — 9:16 vertical cut from the opening hook
- [x] Grounded research — real Wikipedia sources and verified citation URLs
- [x] Wikimedia Commons visual provider (Pexels → Pixabay → Wikimedia fallback)
- [x] Ambient background music mixed and ducked under the voice track

Next — see **[ROADMAP.md](ROADMAP.md)** for the full plan, including the Timeline
(edit decision list) and Style Profile schemas everything else depends on:

- [ ] **Phase 0** — Timeline + Style Profile schemas, renderer split, LLM router,
      and a proper storage layout (fixed per-platform data dir, one folder per
      project, disposable cache)
- [ ] **Phase 1** — commercially-licensed voice cloning (Chatterbox, MIT weights)
      plus a voice repair chain and real forced alignment
- [ ] **Phase 2** — visual craft: script-driven scene timing, cut rhythm,
      Ken-Burns motion, a graphics overlay layer, styled captions, 1080p30
- [ ] **Phase 3** — sound design: CC0 music library, mood arc, gain automation
- [ ] **Phase 4** — reference intelligence: analyse a channel via `yt-dlp` and
      learn its Style Profile
- [ ] **Phase 5** — parallel research swarm with a synthesis pass
- [ ] **Phase 6** — finish YouTube publishing (the provider is written but its
      dependencies, env vars, OAuth setup and first real upload are all still
      pending), plus Docker, one-command install, and niche templates

---

<div align="center"><sub>Built solo, end to end — architecture, backend, and frontend.</sub></div>
