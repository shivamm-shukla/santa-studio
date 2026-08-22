"""Per-provider daily budgets and rate limits.

Free tiers are capped two ways: a ceiling on requests per day, and a floor on
how close together two requests may be. Hitting either returns an error that
looks like a broken provider, so without tracking, a run that exhausts Gemini
at 2pm keeps hammering it for the rest of the day and burns a retry on every
single call.

Counters are kept on disk rather than in memory because the four frontends run
as separate processes, and a bot, a web app and a CLI run on the same machine
share one quota whether or not they know it.

The numbers below are conservative starting points, not published guarantees.
Free tiers move - Gemini's was cut sharply in late 2025 - so every one of them
is overridable by environment variable, and the router treats the budget as a
hint that keeps it from wasting calls rather than as the authority. The
provider's own 429 is still what actually decides.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import date

# requests/day, minimum seconds between requests
DEFAULTS = {
    "gemini": (200, 1.0),
    "groq": (900, 2.0),
    "cerebras": (500, 1.0),
    "openrouter": (180, 3.0),
    "claude": (0, 0.0),      # paid; 0 means no daily cap
}


def _limits(name: str) -> tuple[int, float]:
    per_day, min_interval = DEFAULTS.get(name, (0, 0.0))
    per_day = int(os.getenv(f"{name.upper()}_DAILY_LIMIT", per_day))
    min_interval = float(os.getenv(f"{name.upper()}_MIN_INTERVAL", min_interval))
    return per_day, min_interval


@dataclass
class Usage:
    name: str
    used: int
    limit: int
    last_call: float

    @property
    def exhausted(self) -> bool:
        return self.limit > 0 and self.used >= self.limit

    @property
    def remaining(self) -> int | None:
        return None if self.limit <= 0 else max(0, self.limit - self.used)


class BudgetLedger:
    """Tracks what has been spent today, shared across processes."""

    def __init__(self, path=None):
        if path is None:
            import paths

            path = paths.cache_dir("llm") / "budget.json"
        self.path = str(path)

    def _read(self) -> dict:
        try:
            with open(self.path) as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {"day": date.today().isoformat(), "providers": {}}

        # Counters are daily, so a stale file is an empty one.
        if data.get("day") != date.today().isoformat():
            return {"day": date.today().isoformat(), "providers": {}}
        return data

    def _write(self, data: dict) -> None:
        import uuid

        parent = os.path.dirname(self.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        temp = f"{self.path}.tmp.{uuid.uuid4().hex[:8]}"
        try:
            with open(temp, "w") as handle:
                json.dump(data, handle, indent=2)
            os.replace(temp, self.path)
        finally:
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                except OSError:
                    pass

    def usage(self, name: str) -> Usage:
        entry = self._read()["providers"].get(name, {})
        limit, _ = _limits(name)
        return Usage(
            name=name,
            used=int(entry.get("used", 0)),
            limit=limit,
            last_call=float(entry.get("last_call", 0.0)),
        )

    def record(self, name: str) -> None:
        data = self._read()
        entry = data["providers"].setdefault(name, {"used": 0, "last_call": 0.0})
        entry["used"] = int(entry.get("used", 0)) + 1
        entry["last_call"] = time.time()
        self._write(data)

    def wait_needed(self, name: str) -> float:
        """Seconds to pause before calling `name` again, or 0."""
        _, min_interval = _limits(name)
        if min_interval <= 0:
            return 0.0
        elapsed = time.time() - self.usage(name).last_call
        return max(0.0, min_interval - elapsed)

    def report(self) -> dict:
        """Everything the doctor check shows."""
        return {
            name: {
                "used": self.usage(name).used,
                "limit": limit or None,
                "remaining": self.usage(name).remaining,
                "exhausted": self.usage(name).exhausted,
            }
            for name in DEFAULTS
            for limit, _ in [_limits(name)]
        }

    def reset(self) -> None:
        self._write({"day": date.today().isoformat(), "providers": {}})
