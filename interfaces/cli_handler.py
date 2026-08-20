import json

from interfaces.base import ApprovalHandler


class CLIApprovalHandler(ApprovalHandler):
    """Pretty-prints stub output to the terminal and prompts approve/edit/
    regenerate via input(). This is the only concrete ApprovalHandler in
    Phase 0 - TelegramApprovalHandler and a Streamlit equivalent implement
    the same ABC later without any change to manager.py.
    """

    def request_approval(self, checkpoint: str, payload: dict) -> str:
        print(f"\n=== Approval checkpoint: {checkpoint} ===")
        print(json.dumps(payload, indent=2, default=str))
        while True:
            choice = input("[a]pprove / [e]dit / [r]egenerate: ").strip().lower()
            if choice in ("a", "approve"):
                return "approve"
            if choice in ("e", "edit"):
                return "edit"
            if choice in ("r", "regenerate"):
                return "regenerate"
            print("Please enter a, e, or r.")

    def request_edit(self, checkpoint: str, payload: dict) -> dict:
        print(f"Editing '{checkpoint}'. Current payload shown above.")
        print("Enter replacement text (stored as payload['edited_text']):")
        edited_text = input("> ")
        updated = dict(payload)
        updated["edited_text"] = edited_text
        return updated

    def notify(self, message: str) -> None:
        print(f"[notify] {message}")
