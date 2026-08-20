"""CLI entrypoint. Builds config, collects the initial niche/topic/voice
inputs, and runs the pipeline through to DONE (or a halt on repeated
agent failure).
"""

import glob
import json
import os

from config import build_config
from interfaces.cli_handler import CLIApprovalHandler
from manager import PipelineHalted, PipelineManager
from state import PipelineState, load_state


def _offer_resume() -> PipelineState | None:
    candidates = sorted(glob.glob("runs/*.json"))
    unfinished = []
    for path in candidates:
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if data.get("current_state") not in ("DONE", None):
            unfinished.append(path)

    if not unfinished:
        return None

    print("Found in-progress run(s):")
    for i, path in enumerate(unfinished):
        print(f"  [{i}] {path}")
    choice = input("Resume one? Enter number, or press Enter to start fresh: ").strip()
    if choice.isdigit() and int(choice) < len(unfinished):
        return load_state(unfinished[int(choice)])
    return None


def _collect_initial_inputs() -> PipelineState:
    print("=== Santa Studio ===")
    niche = input("Niche (e.g. 'personal finance', 'space exploration'): ").strip()
    user_topic = input("Specific topic? (leave blank to let the pipeline suggest one): ").strip() or None
    voice_sample_path = input("Path to your voice sample (leave blank to use a stub): ").strip()
    length_input = input("Target video length in minutes (leave blank for 5): ").strip()
    target_length_minutes = int(length_input) if length_input.isdigit() else 5

    return PipelineState(
        niche=niche,
        preferences={},
        user_topic=user_topic,
        voice_sample_path=voice_sample_path or "stub_voice_sample.wav",
        target_length_minutes=target_length_minutes,
    )


def main() -> None:
    config = build_config()
    approval_handler = CLIApprovalHandler()

    state = _offer_resume() or _collect_initial_inputs()
    manager = PipelineManager(state, config, approval_handler)

    try:
        final_state = manager.run()
    except PipelineHalted as e:
        print(f"\nPipeline halted: {e}")
        return

    print("\n=== DONE ===")
    print(f"video_path: {final_state.video_output['video_path']}")
    print(f"Full run state: {os.path.join('runs', final_state.run_id + '.json')}")


if __name__ == "__main__":
    main()
