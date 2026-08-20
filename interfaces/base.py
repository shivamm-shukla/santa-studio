"""Abstract interface for human-facing I/O: approvals, edits, notifications.

The Manager never calls input()/print() directly - it talks only to this
interface. CLI is the only concrete implementation today; Telegram and a
Streamlit dashboard are future adapters that implement the same contract
without touching the Manager, agents, or providers.
"""

from abc import ABC, abstractmethod


class ApprovalHandler(ABC):
    @abstractmethod
    def request_approval(self, checkpoint: str, payload: dict) -> str:
        """Show payload to the human. Returns 'approve' | 'edit' | 'regenerate'."""
        ...

    @abstractmethod
    def request_edit(self, checkpoint: str, payload: dict) -> dict:
        """Collect replacement content when the human chose 'edit'. Returns
        an updated payload dict to substitute for the agent's output."""
        ...

    @abstractmethod
    def notify(self, message: str) -> None:
        """Fire-and-forget status update (state transitions, errors)."""
        ...
