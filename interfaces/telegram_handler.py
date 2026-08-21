"""Telegram bot ApprovalHandler - approvals via inline buttons, notifications
as push messages, mobile-first control for the "AI does everything, only
asks permission where it matters" workflow.

Implements the same ApprovalHandler ABC as CLIApprovalHandler
(interfaces/base.py) - manager.py needs zero changes to use this instead.
Built on the shared TelegramClient (interfaces/telegram_client.py) rather
than the python-telegram-bot framework, since PipelineManager.run() is a
plain blocking loop and this avoids mixing in an async event loop for no
benefit.

Needs a real bot token (from @BotFather) and the chat_id to message - both
read from config, added last per the project's "keys come last" workflow.
"""

import json

from interfaces.base import ApprovalHandler
from interfaces.telegram_client import TelegramClient


class TelegramApprovalHandler(ApprovalHandler):
    def __init__(self, bot_token: str, chat_id: str):
        if not chat_id:
            raise RuntimeError(
                "TelegramApprovalHandler needs TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID - add them to .env."
            )
        self.client = TelegramClient(bot_token)
        self.chat_id = chat_id

    def request_approval(self, checkpoint: str, payload: dict) -> str:
        summary = json.dumps(payload, indent=2, default=str)[:3500]
        keyboard = {
            "inline_keyboard": [[
                {"text": "Approve", "callback_data": "approve"},
                {"text": "Edit", "callback_data": "edit"},
                {"text": "Regenerate", "callback_data": "regenerate"},
            ]]
        }
        self.client.send_message(self.chat_id, f"Approval checkpoint: {checkpoint}\n\n{summary}", keyboard)

        def find_choice(update):
            cq = update.get("callback_query")
            if cq and str(cq.get("message", {}).get("chat", {}).get("id")) == str(self.chat_id):
                self.client.answer_callback_query(cq["id"])
                return cq["data"]
            return None

        return self.client.poll_until(find_choice)

    def request_edit(self, checkpoint: str, payload: dict) -> dict:
        self.client.send_message(self.chat_id, f"Editing '{checkpoint}'. Reply with replacement text.")

        def find_text(update):
            msg = update.get("message")
            if msg and str(msg.get("chat", {}).get("id")) == str(self.chat_id) and "text" in msg:
                return msg["text"]
            return None

        edited_text = self.client.poll_until(find_text)
        updated = dict(payload)
        updated["edited_text"] = edited_text
        return updated

    def notify(self, message: str) -> None:
        self.client.send_message(self.chat_id, message)
