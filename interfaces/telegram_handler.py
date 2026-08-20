"""Telegram bot ApprovalHandler - approvals via inline buttons, notifications
as push messages, mobile-first control for the "AI does everything, only
asks permission where it matters" workflow.

Implements the same ApprovalHandler ABC as CLIApprovalHandler
(interfaces/base.py) - manager.py needs zero changes to use this instead.
Uses raw Bot API calls via `requests` (long-polling getUpdates) rather than
the python-telegram-bot framework, since PipelineManager.run() is a plain
blocking loop and this avoids mixing in an async event loop for no benefit.

Needs a real bot token (from @BotFather) and the chat_id to message - both
read from config, added last per the project's "keys come last" workflow.
"""

import json
import time

import requests

from interfaces.base import ApprovalHandler

API_BASE = "https://api.telegram.org/bot{token}"
POLL_TIMEOUT = 30  # seconds - Telegram long-polling


class TelegramApprovalHandler(ApprovalHandler):
    def __init__(self, bot_token: str, chat_id: str):
        if not bot_token or not chat_id:
            raise RuntimeError(
                "TelegramApprovalHandler needs TELEGRAM_BOT_TOKEN and "
                "TELEGRAM_CHAT_ID - add them to .env."
            )
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._base = API_BASE.format(token=bot_token)
        self._update_offset = 0

    def _call(self, method: str, **params) -> dict:
        response = requests.post(f"{self._base}/{method}", json=params, timeout=POLL_TIMEOUT + 10)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {data}")
        return data["result"]

    def _poll_until(self, predicate):
        """Long-polls getUpdates until `predicate(update)` returns a truthy
        value, which is returned. Advances the offset past every update seen
        so nothing is processed twice.
        """
        while True:
            updates = self._call(
                "getUpdates", offset=self._update_offset, timeout=POLL_TIMEOUT
            )
            for update in updates:
                self._update_offset = update["update_id"] + 1
                result = predicate(update)
                if result is not None:
                    return result

    def request_approval(self, checkpoint: str, payload: dict) -> str:
        summary = json.dumps(payload, indent=2, default=str)[:3500]
        keyboard = {
            "inline_keyboard": [[
                {"text": "Approve", "callback_data": "approve"},
                {"text": "Edit", "callback_data": "edit"},
                {"text": "Regenerate", "callback_data": "regenerate"},
            ]]
        }
        self._call(
            "sendMessage",
            chat_id=self.chat_id,
            text=f"Approval checkpoint: {checkpoint}\n\n{summary}",
            reply_markup=keyboard,
        )

        def find_choice(update):
            cq = update.get("callback_query")
            if cq and str(cq.get("message", {}).get("chat", {}).get("id")) == str(self.chat_id):
                self._call("answerCallbackQuery", callback_query_id=cq["id"])
                return cq["data"]
            return None

        return self._poll_until(find_choice)

    def request_edit(self, checkpoint: str, payload: dict) -> dict:
        self._call(
            "sendMessage",
            chat_id=self.chat_id,
            text=f"Editing '{checkpoint}'. Reply with replacement text.",
        )

        def find_text(update):
            msg = update.get("message")
            if msg and str(msg.get("chat", {}).get("id")) == str(self.chat_id) and "text" in msg:
                return msg["text"]
            return None

        edited_text = self._poll_until(find_text)
        updated = dict(payload)
        updated["edited_text"] = edited_text
        return updated

    def notify(self, message: str) -> None:
        self._call("sendMessage", chat_id=self.chat_id, text=message)
