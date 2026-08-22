# Santa Studio — handoff

State of the project as of 22 Aug 2026, for picking the work up elsewhere.

Latest commits landed on `main` (`f4c0d06`), verified end-to-end. `git log --oneline` lists recent commits.

---

## What the pipeline does now

```
IDLE → TOPIC_SELECTION → REFERENCE_ANALYSIS → RESEARCHING → FACT_CHECKING
     → SCRIPTING → VOICE_GENERATION → VISUAL_SELECTION → VIDEO_ASSEMBLY
     → SHORTS_EXTRACTION → [GATE: video ok?] → THUMBNAIL → [GATE: ready to publish?]
     → YOUTUBE_PUBLISH → DONE
```

The pipeline produces:
1. **Master Video (16:9 MP4):** Scaled visuals, mixed ambient background audio, timed subtitles (`runs/{run_id}_final.mp4`).
2. **Vertical YouTube Short (9:16 MP4):** 30–50s opening hook vertical crop (`runs/shorts/{run_id}_short.mp4`).
3. **Multi-Variant Thumbnails (JPG):** 3 distinct layout and text options (`runs/thumbnails/{run_id}_thumb_*.jpg`).
4. **Grounded Source Citations:** Real encyclopedic sources and verified URLs for video descriptions.
5. **Publishing (Opt-in):** Direct upload via YouTube Data API v3 (`ACTIVE_PROVIDERS["publish"] = "youtube"`).

Verified end-to-end across all four frontends (Web, Telegram bot, CLI, Streamlit).

---

## What works

### 1. Grounded Research & Authentic Citations
`agents/research_agent.py` queries the live Wikipedia API to extract lead summaries, key facts, and verified URLs (`https://en.wikipedia.org/wiki/...`). LLMs synthesize research grounded in real-world facts, eliminating fabricated citations in video descriptions.

### 2. Wikimedia Commons Visual Provider & 3-Tier Fallback
`providers/visual/wikimedia_provider.py` adds public-domain historical paintings, photographs, and scientific diagrams.
`visual_agent.py` and `thumbnail.py` now execute a 3-tier fallback search:
$$\text{Pexels} \longrightarrow \text{Pixabay} \longrightarrow \text{Wikimedia Commons}$$
In `assembler_agent.py`, images are dynamically scaled and center-cropped to 1280×720 without stretching or aspect ratio distortion.

### 3. Background Music Mixing & Voice Ducking
`providers/music/ambient_music_provider.py` procedural audio generator synthesizes mood-tailored atmospheric background beds (`curious`, `cinematic`, `calm`, `energetic`, `mysterious`) without copyright risk. In `assembler_agent.py`, music is looped and ducked by $-18\,\text{dB}$ under voiceover speech.

### 4. Vertical Shorts Extraction (`agents/shorts_agent.py`)
Automatically isolates the high-retention opening hook, center-crops the 16:9 composite to vertical 9:16 ($720\times1280$), and encodes a standalone YouTube Short in `runs/shorts/`.

### 5. YouTube Data API v3 Publishing (`providers/publish/youtube_provider.py`)
Implements `PublishProvider` with OAuth2 Installed-App flow and token caching (`runs/youtube_token.json`). Automatically sets title, description, tags, custom thumbnail, and uploads as `private`.

### 6. Hinglish Dual-Scripting
`config.OUTPUT_LANGUAGE` (`"hinglish"`) outputs:
- `text`: Latin script for on-screen captions, titles, and thumbnails.
- `spoken`: Phonetic Devanagari script for natural Hindi voice pronunciation.

### 7. Multi-Variant Thumbnails (`agents/thumbnail.py`)
Generates three layout styles (`bottom-bar`, `left-block`, `center-punch`) with Pillow and visual asset queries.

---

## Codebase Audit & Fixed Bugs

1. **Greedy LLM JSON Parsing (`agents/_llm_utils.py`):** Replaced greedy regex with a 4-stage parser (direct `json.loads` $\rightarrow$ code fence extract $\rightarrow$ `JSONDecoder.raw_decode` bracket scan $\rightarrow$ fallback) preventing crashes when models add conversational text with curly braces.
2. **Unhandled Agent Exceptions (`assembler_agent.py`, `visual_agent.py`):** Wrapped `run()` and concurrent asset fetches in `try...except` returning `{success: False, error: ...}` to trigger manager retries cleanly instead of crashing worker threads.
3. **Checkpoint Edit Synchronization (`manager.py`):** Applied user edits at `SCRIPTING` and `RESEARCHING` gates directly to `script_text`, scenes, and `research_summary` so edits properly propagate downstream.
4. **Web UI Stage Track on Gate Pauses (`web/templates/run.html`):** Mapped gate states (`AWAITING_APPROVAL` $\rightarrow$ `SHORTS_EXTRACTION`, `AWAITING_PUBLISH` $\rightarrow$ `THUMBNAIL`) so progress dots maintain active state rather than resetting to grey.
5. **Dangling FFmpeg Symlinks (`providers/_ffmpeg_setup.py`):** Used `os.path.lexists()` to replace stale symlinks safely without `FileExistsError`, and explicitly bound `pydub.AudioSegment.converter`.
6. **Concurrent Download File Collisions (`providers/visual/_download.py`):** Used unique partial filenames (`f"{path}.part.{uuid}"`) and standard User-Agents to prevent multi-threaded write collisions and 403 blocks.
7. **Silent Thread Crashes (`web/server.py`, `bot_main.py`):** Wrapped `_drive_run` in general exception handlers to update `STATUS[run_id] = {"type": "error"}` instead of stalling the UI.
8. **State Schema Resilience & Atomic Writes (`state.py`):** Filtered unknown fields in `load_state` and used `.tmp` atomic renaming in `save_state`.
9. **Empty Caption Chunks (`agents/assembler_agent.py`):** Added guards against empty/whitespace chunks in `_build_captions`.
10. **Telegram Bot Voice Exception Handling (`bot_main.py`):** Guarded `pending_voice_path` dictionary pop and wrapped update dispatch loops in error traps.

---

## What does not work / Next steps

1. **Commercial Voice Cloning (Chatterbox TTS):**
   - XTTS-v2 weights are CPML (non-commercial only).
   - Chatterbox (Resemble AI) has permissive MIT weights. `pip install chatterbox-tts` requires pinning compatible Torch wheels on a stable connection (~3GB free disk).
   - Currently uses `gtts` as the default zero-dependency fallback.

2. **YouTube Verification for Public Uploads:**
   - Videos uploaded through unverified OAuth2 Google Cloud projects are set to `private` by YouTube API policy. User must manually flip to public or complete Google Cloud app verification.

---

## Running It

```bash
cd santa-studio && source venv/bin/activate
uvicorn web.server:app        # FastAPI web app -> http://localhost:8000
python bot_main.py            # Telegram Bot (@santa_studio_bot)
python main.py                # Interactive CLI
streamlit run studio_app.py   # Streamlit prototyping UI
```

All credentials and API keys are managed in `.env`.
