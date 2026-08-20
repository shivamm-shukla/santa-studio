# Santa Studio

An autonomous multi-agent AI studio that takes a YouTube video from topic
idea to a finished, captioned MP4 - research, script, cloned/filtered voice,
visuals, and assembly - with a human approving only where it actually
matters (by default, once, right before the final video is accepted).

## Architecture

- **`manager.py`** - the orchestrator. A state machine that calls one agent
  per pipeline state, validates output, retries once on failure then halts,
  and persists the full run to `runs/<run_id>.json` after every transition.
- **`agents/`** - one function per pipeline stage (`topic`, `reference`,
  `research`, `factcheck`, `script`, `voice`, `visual`, `assembler`, plus
  `shorts`/`publish` stubs for Phase 2). Every agent follows the same
  contract: `run(input_data, config) -> {success, output, error}`.
- **`providers/`** - every external AI capability (LLM, voice, visuals,
  captions) sits behind an abstract interface in `providers/base.py`,
  resolved via `providers/registry.py` from `config.ACTIVE_PROVIDERS`.
  Swapping XTTS for ElevenLabs, or Pexels for Storyblocks, is a one-line
  config change - agents never import a concrete provider directly.
- **`interfaces/`** - human-facing I/O (approvals, edits, notifications)
  is behind the same kind of abstraction (`ApprovalHandler`). Three
  implementations exist: CLI, Telegram (inline-button approvals from your
  phone), and Streamlit (`step()`-driven, since Streamlit can't block on
  input the way the other two do).
- **`state.py`** - the `PipelineState` schema and JSON persistence, so a
  run can be killed and resumed.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in API keys as you get them
```

No system `ffmpeg`/`ffprobe` install (and therefore no sudo) is required -
`providers/_ffmpeg_setup.py` resolves both automatically via the
`static-ffmpeg` package the first time any provider needs them.

## Running it

- **CLI:** `python main.py` - walks through niche/topic/voice-sample
  prompts, then runs the pipeline with approve/edit/regenerate prompts in
  the terminal.
- **Telegram:** `python bot_main.py` - same pipeline, but approvals and
  notifications go to a Telegram chat instead of the terminal. Needs
  `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` (from @BotFather).
- **Streamlit studio:** `streamlit run studio_app.py` - a browser dashboard
  to start/resume runs and a "Voice Studio" tab to upload a sample and
  preview filter presets (natural/warm/deep/bright/energetic/calm) before
  using it in a run.

`REVIEW_MODE` in `.env` controls how often the pipeline pauses:
`autonomous` (default) pauses once, right before the final video is
accepted; `checkpoints` adds two more pauses, after research and after
scripting.

## What needs a real API key vs. what doesn't

| Needs a key | Runs fully local/free |
|---|---|
| `ANTHROPIC_API_KEY` - topic/reference/research/factcheck/script agents | Whisper captions |
| `PEXELS_API_KEY` / `PIXABAY_API_KEY` - stock visual search | MoviePy/FFmpeg video assembly |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` - only for `bot_main.py` | Voice filter presets (pydub) |

Every provider fails cleanly (a clear error message, pipeline halts or
degrades gracefully) when its key is missing, rather than crashing -
you can build/test everything else before adding keys.

## Known limitations / next steps

- **XTTS-v2 voice cloning** needs the `TTS` package (`pip install TTS`) -
  a heavy dependency (torch + a multi-GB model download on first use) not
  installed by default. Its license (Coqui CPML) restricts *commercial*
  use - see the docstring in `providers/voice/xtts_provider.py` before
  using it on a monetized channel.
- **`reference_agent`/`research_agent`** currently reason from the model's
  own knowledge rather than actually browsing reference URLs or searching
  the web - wiring in Claude's `web_fetch`/`web_search` tools is a
  follow-up.
- **`shorts_agent`/`publish_agent`** are Phase 2 stubs with no real logic
  yet.
