"""Low-level Telegram Bot API client - raw HTTP via requests (long-polling
getUpdates), shared by TelegramApprovalHandler (interfaces/telegram_handler.py)
and the full command-driven bot (bot_main.py). No python-telegram-bot
framework dependency - see telegram_handler.py's module docstring for why.
"""

import requests

API_BASE = "https://api.telegram.org/bot{token}"
FILE_BASE = "https://api.telegram.org/file/bot{token}"
POLL_TIMEOUT = 30  # seconds - Telegram long-polling


class TelegramClient:
    def __init__(self, bot_token: str):
        if not bot_token:
            raise RuntimeError("A Telegram bot token is required.")
        self.bot_token = bot_token
        self._base = API_BASE.format(token=bot_token)
        self._file_base = FILE_BASE.format(token=bot_token)
        self.update_offset = 0

    def call(self, method: str, **params) -> dict:
        response = requests.post(f"{self._base}/{method}", json=params, timeout=POLL_TIMEOUT + 10)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on {method}: {data}")
        return data["result"]

    def get_updates(self, timeout: int = POLL_TIMEOUT) -> list[dict]:
        """One long-polling call. Advances the internal offset past every
        update returned, so nothing is processed twice. `timeout` controls
        how long this blocks waiting for a new update - callers that also
        need to notice other state changes (e.g. background pipeline
        progress) should pass a short value instead of the default 30s."""
        updates = self.call("getUpdates", offset=self.update_offset, timeout=timeout)
        if updates:
            self.update_offset = updates[-1]["update_id"] + 1
        return updates

    def poll_until(self, predicate):
        """Long-polls until `predicate(update)` returns a truthy value,
        which is returned."""
        while True:
            for update in self.get_updates():
                result = predicate(update)
                if result is not None:
                    return result

    def send_message(self, chat_id, text: str, reply_markup: dict | None = None) -> dict:
        params = {"chat_id": chat_id, "text": text}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self.call("sendMessage", **params)

    def edit_message(self, chat_id, message_id, text: str, reply_markup: dict | None = None) -> dict:
        params = {"chat_id": chat_id, "message_id": message_id, "text": text}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self.call("editMessageText", **params)

    def answer_callback_query(self, callback_query_id: str) -> None:
        self.call("answerCallbackQuery", callback_query_id=callback_query_id)

    def send_video(self, chat_id, video_path: str, caption: str = "") -> dict:
        with open(video_path, "rb") as f:
            response = requests.post(
                f"{self._base}/sendVideo",
                data={"chat_id": chat_id, "caption": caption},
                files={"video": f},
                timeout=120,
            )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on sendVideo: {data}")
        return data["result"]

    def send_audio(self, chat_id, audio_path: str, caption: str = "") -> dict:
        with open(audio_path, "rb") as f:
            response = requests.post(
                f"{self._base}/sendAudio",
                data={"chat_id": chat_id, "caption": caption},
                files={"audio": f},
                timeout=60,
            )
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error on sendAudio: {data}")
        return data["result"]

    def download_file(self, file_id: str, dest_path: str) -> str:
        file_info = self.call("getFile", file_id=file_id)
        url = f"{self._file_base}/{file_info['file_path']}"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(response.content)
        return dest_path
