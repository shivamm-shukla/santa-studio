# Santa Studio (notes to self)

My AI studio — I give it a niche/topic, it researches, scripts, clones my
voice, picks visuals, and cuts the final video. I only step in where it
actually matters (default: just before it goes live).

## How I've got it wired up

- `manager.py` — the state machine. Runs one agent per stage, retries an
  agent once if it fails, saves the whole run to `runs/<run_id>.json`
  after every step so I can kill and resume it anytime.
- `agents/` — one file per stage (topic → reference → research →
  factcheck → script → voice → visual → assembler). `shorts_agent` /
  `publish_agent` are still empty stubs, Phase 2.
- `providers/` — LLM / voice / visuals / captions are all behind an
  interface, picked in `config.ACTIVE_PROVIDERS`. So if I ever want to
  swap XTTS for ElevenLabs or Pexels for something else, it's a one-line
  config change, not touching the agents.
- `providers/voice/profiles.py` — my saved voices live in
  `runs/voice_profiles/`. Upload once, pick a filter once, reuse
  everywhere — don't need to re-upload every run.
- `interfaces/` — how approvals reach me: terminal, Telegram, or a UI.
  Same `ApprovalHandler` shape underneath so I can add more later
  without touching the pipeline itself.
- Three front doors right now: `main.py` (terminal), `bot_main.py`
  (Telegram), `studio_app.py` (Streamlit — quick and ugly, mostly for
  testing), and `web/` (the actual site).

## Getting it running again

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in keys as I get them
```

Didn't have to install ffmpeg myself — `providers/_ffmpeg_setup.py`
grabs it via pip automatically the first time something needs it.

- Terminal: `python main.py`
- Telegram: `python bot_main.py` — needs `TELEGRAM_BOT_TOKEN` +
  `TELEGRAM_CHAT_ID` in `.env` (from @BotFather)
- The actual website: `uvicorn web.server:app --reload`, open
  `localhost:8000`
- Streamlit (backup/testing only): `streamlit run studio_app.py`

`REVIEW_MODE` in `.env`: `autonomous` = only stops me once, right before
publish. `checkpoints` = also stops after research and after script, if
I want more control.

## Keys — what's blocked without them

- `ANTHROPIC_API_KEY` → without this, nothing past the first couple
  stages works (topic/research/script all need Claude)
- `PEXELS_API_KEY` / `PIXABAY_API_KEY` → real visuals. No key = it still
  runs, just with placeholder footage.
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` → only matters for the bot
- Everything else (Whisper captions, video assembly, voice filters) is
  free/local, no key needed — good stuff to test before I add real keys.

## Still need to do

- [ ] Add the real API keys once I'm ready to spend money
- [ ] `pip install TTS` for real voice cloning — heavy install (torch +
  big model download), and remember: XTTS's license doesn't allow
  commercial use for free, need to sort that out before monetizing
- [ ] `reference_agent` / `research_agent` don't actually browse/search
  yet, just reasoning from the model's own knowledge — wire up real
  web search
- [ ] Telegram bot parity with the website (profiles, gates, everything)
  — in progress
- [ ] `shorts_agent`, `publish_agent` — nothing built yet
