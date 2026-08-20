"""Entrypoint that runs the pipeline with Telegram as the approval channel
instead of the terminal - approve/edit/regenerate from your phone. Initial
inputs (niche/topic/voice sample) are still collected here on the machine
running the pipeline; only the approval gates and notifications go through
Telegram. See main.py for the pure-CLI equivalent.
"""

import os

from config import build_config
from interfaces.telegram_handler import TelegramApprovalHandler
from main import _collect_initial_inputs, _offer_resume
from manager import PipelineHalted, PipelineManager


def main() -> None:
    config = build_config()
    approval_handler = TelegramApprovalHandler(
        config["TELEGRAM_BOT_TOKEN"], config["TELEGRAM_CHAT_ID"]
    )

    state = _offer_resume() or _collect_initial_inputs()
    manager = PipelineManager(state, config, approval_handler)

    approval_handler.notify(f"Starting run {state.run_id} - niche: {state.niche!r}")
    try:
        final_state = manager.run()
    except PipelineHalted as e:
        approval_handler.notify(f"Pipeline halted: {e}")
        return

    approval_handler.notify(
        f"Done. video_path: {final_state.video_output['video_path']}\n"
        f"Full run state: {os.path.join('runs', final_state.run_id + '.json')}"
    )


if __name__ == "__main__":
    main()
