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

## Tech stack

| Layer | Choice |
|---|---|
| Reasoning | Gemini -> Groq free fallback chain (Claude optional) |
| Voice | gTTS by default (free, zero-setup); Coqui XTTS-v2 for real cloning |
| Voice filters | pydub (pitch shift, EQ, tempo) |
| Captions | OpenAI Whisper (local) |
| Stock visuals | Pexels API, Pixabay API (fallback) |
| Video assembly | MoviePy / FFmpeg |
| Web backend | FastAPI |
| Bot interface | Telegram Bot API (raw, long-polling) |
| Frontend | Hand-written HTML/CSS/JS, no build step |

## Running it

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add API keys as available
```

- **Web app:** `uvicorn web.server:app --reload` → `localhost:8000`
- **CLI:** `python main.py`
- **Telegram bot:** `python bot_main.py` (needs `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`)
- **Streamlit prototype:** `streamlit run studio_app.py`

Every provider fails cleanly (a clear error, not a crash) when its key
is missing, so the whole system — voice filters, captions, video
assembly — is testable before any paid API key is added.

## Roadmap

- [x] Telegram bot parity with the web app (voice profiles, gates, full runs from chat)
- [ ] Real web search/fetch for the research and reference agents
- [ ] Shorts extraction + auto-publish agents
- [ ] XTTS-v2 commercial licensing decision before monetized use (Coqui CPML)

---

<div align="center"><sub>Built solo, end to end — architecture, backend, and frontend.</sub></div>
