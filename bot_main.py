"""Full Telegram bot - everything the website can do, from chat.

Unlike the earlier version of this file (which only used Telegram for
approvals on one run started from the terminal), this is a persistent,
command-driven loop: /newvideo starts a run entirely from chat (niche,
topic, voice profile, review mode all collected via replies/buttons),
/runs resumes a previous one, voice notes create/update voice profiles,
and approval gates + the final video all arrive as chat messages.

Drives PipelineManager.step() directly, in-process - not through the web
API - the same way the earlier version drove PipelineManager.run()
directly. No pipeline logic lives here, same as every other interface.
"""

import glob
import json
import os
import threading
import time
import uuid

from config import build_config
from interfaces.telegram_client import TelegramClient
from manager import PipelineHalted, PipelineManager
from providers.voice.profiles import create_profile, list_profiles
from state import PipelineState, load_state

POLL_TIMEOUT = 3  # short timeout so we stay responsive to run progress too

# Single-user bot: one conversation session, one active run at a time.
session = {"stage": "idle", "data": {}}
active_run = None  # {"manager": PipelineManager, "message_id": int, "result": dict, "dirty": bool}


def _drive_run(decision=None, edited_payload=None):
    """Runs in a background thread: advances the active run until it hits
    a gate, finishes, or halts. Same shape as web/server.py's _drive_run,
    except that a pending gate decision is resolved here too rather than
    on the caller's thread - "regenerate" re-runs a whole agent, which
    would otherwise stall the poll loop for as long as that takes.
    """
    mgr = active_run["manager"]
    try:
        while True:
            result = mgr.step(decision=decision, edited_payload=edited_payload)
            decision, edited_payload = None, None
            active_run["result"] = result
            active_run["dirty"] = True
            if result["type"] in ("awaiting_approval", "done"):
                return
    except PipelineHalted as e:
        active_run["result"] = {"type": "error", "error": str(e)}
        active_run["dirty"] = True


def _start_driving(decision=None, edited_payload=None):
    threading.Thread(
        target=_drive_run, args=(decision, edited_payload), daemon=True
    ).start()


def _format_gate(checkpoint: str, payload: dict) -> str:
    if checkpoint == "SCRIPTING" and payload.get("scenes"):
        lines = [f"Approval checkpoint: {checkpoint}\n"]
        for s in payload["scenes"]:
            lines.append(f"[{s.get('timestamp_estimate', '')}] {s.get('text', '')}")
        return "\n".join(lines)[:4000]
    if checkpoint == "RESEARCHING" and payload.get("sources"):
        lines = [f"Approval checkpoint: {checkpoint}\n", payload.get("research_summary", "")]
        for s in payload["sources"]:
            lines.append(f"- {s.get('title', '')}: " + "; ".join(s.get("key_facts", [])))
        return "\n".join(lines)[:4000]
    return f"Approval checkpoint: {checkpoint}\n\n{json.dumps(payload, indent=2, default=str)}"[:4000]


class SantaStudioBot:
    def __init__(self, config: dict):
        self.config = config
        self.chat_id = config["TELEGRAM_CHAT_ID"]
        self.client = TelegramClient(config["TELEGRAM_BOT_TOKEN"])

    def send(self, text: str, reply_markup: dict | None = None) -> dict:
        return self.client.send_message(self.chat_id, text, reply_markup)

    # ---- run lifecycle ----------------------------------------------------

    def _offer_voice_profiles(self) -> None:
        session["stage"] = "awaiting_voice_choice"
        profiles = list_profiles()
        buttons = [[{"text": p["name"], "callback_data": f"voice:{pid}"}] for pid, p in profiles.items()]
        buttons.append([{"text": "+ Add new voice", "callback_data": "voice:new"}])
        buttons.append([{"text": "Skip (stub voice)", "callback_data": "voice:none"}])
        self.send("Pick a voice profile:", {"inline_keyboard": buttons})

    def _offer_review_mode(self) -> None:
        session["stage"] = "awaiting_review_mode"
        buttons = [[
            {"text": "Autonomous", "callback_data": "review:autonomous"},
            {"text": "Checkpoints", "callback_data": "review:checkpoints"},
        ]]
        self.send("Review mode?", {"inline_keyboard": buttons})

    def _launch_run(self) -> None:
        global active_run
        d = session["data"]
        state = PipelineState(
            niche=d["niche"],
            user_topic=d.get("user_topic"),
            voice_profile_id=d.get("voice_profile_id"),
            target_length_minutes=d.get("target_length_minutes", 5),
            preferences={},
        )
        cfg = dict(self.config)
        cfg["REVIEW_MODE"] = d.get("review_mode", "autonomous")
        manager = PipelineManager(state, cfg, approval_handler=None)

        msg = self.send(f"Starting run for '{d['niche']}' (run {state.run_id[:8]})...")
        active_run = {"manager": manager, "message_id": msg["message_id"], "result": None, "dirty": False}
        session["stage"] = "idle"
        session["data"] = {}
        _start_driving()

    def _resume_run(self, run_id: str) -> None:
        global active_run
        path = os.path.join("runs", f"{run_id}.json")
        if not os.path.exists(path):
            self.send(f"No saved run found for {run_id[:8]}.")
            return
        state = load_state(path)
        if state.current_state == "DONE":
            self.send(f"Run {run_id[:8]} is already done.")
            self.client.send_video(self.chat_id, state.video_output["video_path"])
            return
        manager = PipelineManager(state, self.config, approval_handler=None)
        msg = self.send(f"Resuming run {run_id[:8]} (currently at {state.current_state})...")
        active_run = {"manager": manager, "message_id": msg["message_id"], "result": None, "dirty": False}
        _start_driving()

    def _push_run_update(self) -> None:
        """Called from the main loop when active_run["dirty"] - reflects the
        latest step() result to the chat."""
        global active_run
        result = active_run["result"]
        active_run["dirty"] = False

        if result["type"] == "advanced":
            self.client.edit_message(self.chat_id, active_run["message_id"], f"Working on: {result['state']}...")
        elif result["type"] == "awaiting_approval":
            text = _format_gate(result["checkpoint"], result["payload"])
            keyboard = {"inline_keyboard": [[
                {"text": "Approve", "callback_data": "approve"},
                {"text": "Regenerate", "callback_data": "regenerate"},
                {"text": "Edit", "callback_data": "edit"},
            ]]}
            self.client.edit_message(self.chat_id, active_run["message_id"], text, keyboard)
        elif result["type"] == "done":
            self.client.edit_message(self.chat_id, active_run["message_id"], "Pipeline complete - sending video...")
            self.client.send_video(self.chat_id, result["video_path"])
            active_run = None
        elif result["type"] == "error":
            self.client.edit_message(self.chat_id, active_run["message_id"], f"Halted: {result['error']}")
            active_run = None

    # ---- Telegram update handlers ------------------------------------------

    def handle_command(self, text: str) -> None:
        global active_run
        if text.startswith("/newvideo"):
            if active_run is not None:
                self.send("A run is already in progress - finish or wait for it first.")
                return
            session["stage"] = "awaiting_niche"
            session["data"] = {}
            self.send("What's the niche for this video?")
        elif text.startswith("/runs"):
            candidates = sorted(glob.glob("runs/*.json"), reverse=True)
            unfinished = []
            for path in candidates:
                try:
                    with open(path) as f:
                        data = json.load(f)
                except (json.JSONDecodeError, OSError):
                    continue
                if data.get("current_state") not in ("DONE", None):
                    unfinished.append(data)
            if not unfinished:
                self.send("No in-progress runs to resume.")
                return
            buttons = [
                [{"text": f"{d['niche']} ({d['current_state']})", "callback_data": f"resume:{d['run_id']}"}]
                for d in unfinished[:10]
            ]
            self.send("Resume which run?", {"inline_keyboard": buttons})
        elif text.startswith("/start"):
            self.send("Santa Studio bot. /newvideo to start a run, /runs to resume one.")

    def handle_text(self, text: str) -> None:
        global active_run
        stage = session["stage"]

        if stage == "awaiting_niche":
            session["data"]["niche"] = text
            session["stage"] = "awaiting_topic"
            self.send("Specific topic? (send - to let the pipeline suggest one)")
        elif stage == "awaiting_topic":
            session["data"]["user_topic"] = None if text.strip() == "-" else text
            session["stage"] = "awaiting_length"
            self.send("Target length in minutes? (e.g. 5)")
        elif stage == "awaiting_length":
            session["data"]["target_length_minutes"] = int(text.strip()) if text.strip().isdigit() else 5
            self._offer_voice_profiles()
        elif stage == "awaiting_profile_name":
            name = text.strip() or "Untitled Voice"
            source_path = session["data"].pop("pending_voice_path")
            profile = create_profile(name, source_path)
            os.remove(source_path)
            session["data"]["voice_profile_id"] = profile["profile_id"]
            self.send(f"Saved voice profile '{name}'.")
            self._offer_review_mode()
        elif stage == "awaiting_edit_text" and active_run is not None:
            session["stage"] = "idle"
            _start_driving(decision="edit", edited_payload={"edited_text": text})
        # else: stray text outside any flow, ignore

    def handle_voice_or_audio(self, file_id: str) -> None:
        if session["stage"] != "awaiting_voice_note":
            return
        dest = os.path.join("/tmp", f"{uuid.uuid4()}.ogg")
        self.client.download_file(file_id, dest)
        session["data"]["pending_voice_path"] = dest
        session["stage"] = "awaiting_profile_name"
        self.send("Got it. What should this voice profile be called?")

    def handle_callback(self, cq: dict) -> None:
        global active_run
        self.client.answer_callback_query(cq["id"])
        data = cq["data"]

        if data.startswith("voice:"):
            choice = data.split(":", 1)[1]
            if choice == "new":
                session["stage"] = "awaiting_voice_note"
                self.send("Send a ~6s voice note or audio file.")
            elif choice == "none":
                session["data"]["voice_profile_id"] = None
                self._offer_review_mode()
            else:
                session["data"]["voice_profile_id"] = choice
                self._offer_review_mode()
        elif data.startswith("review:"):
            session["data"]["review_mode"] = data.split(":", 1)[1]
            self._launch_run()
        elif data.startswith("resume:"):
            self._resume_run(data.split(":", 1)[1])
        elif data in ("approve", "regenerate") and active_run is not None:
            if data == "regenerate":
                # Re-running the agent can take a while - drop the buttons
                # and say so, otherwise the gate message just sits there.
                self.client.edit_message(
                    self.chat_id, active_run["message_id"], "Regenerating..."
                )
            _start_driving(decision=data)
        elif data == "edit" and active_run is not None:
            session["stage"] = "awaiting_edit_text"
            self.send("Reply with your replacement text.")

    def dispatch(self, update: dict) -> None:
        if "callback_query" in update:
            self.handle_callback(update["callback_query"])
            return

        message = update.get("message")
        if not message or str(message.get("chat", {}).get("id")) != str(self.chat_id):
            return

        if "text" in message and message["text"].startswith("/"):
            self.handle_command(message["text"])
        elif "text" in message:
            self.handle_text(message["text"])
        elif "voice" in message:
            self.handle_voice_or_audio(message["voice"]["file_id"])
        elif "audio" in message:
            self.handle_voice_or_audio(message["audio"]["file_id"])

    def run_forever(self) -> None:
        self.send("Santa Studio bot is online. /newvideo to start a run.")
        while True:
            updates = self.client.get_updates(timeout=POLL_TIMEOUT)
            for update in updates:
                try:
                    self.dispatch(update)
                except Exception as e:
                    self.send(f"Something went wrong handling that: {e}")

            if active_run is not None and active_run["dirty"]:
                self._push_run_update()

            if not updates:
                time.sleep(0.5)


def main() -> None:
    config = build_config()
    if not config["TELEGRAM_BOT_TOKEN"] or not config["TELEGRAM_CHAT_ID"]:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env.")
    SantaStudioBot(config).run_forever()


if __name__ == "__main__":
    main()
