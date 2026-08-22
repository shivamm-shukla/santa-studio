"""Routes a completion across several free-tier providers.

The old fallback tried Gemini, then Groq, and gave up. That was fine while the
pipeline made a handful of calls per video. It stops being fine once research
fans out across several agents per run, because free tiers are capped per day
and Google cut Gemini's sharply in late 2025 - one exhausted provider then
means every subsequent call burns a failed request before falling through.

So this adds three things the plain chain did not have:

* **Budgets.** A provider known to be out of quota for the day is skipped
  rather than tried and failed, and requests to the same provider are spaced
  out to respect its rate limit. Counters live on disk because the four
  frontends are separate processes sharing one quota.

* **Ordering by what is actually available.** Providers with no key configured
  are dropped entirely, so a fresh checkout with one key behaves sensibly
  instead of failing three times per call.

* **An optional response cache.** Off by default: a review gate's "regenerate"
  sends exactly the same prompt, and a cache would hand back exactly the same
  answer, which is the opposite of what was asked for. Switched on with
  SANTA_STUDIO_LLM_CACHE=1 it makes re-running a crashed pipeline free, which
  is worth a great deal on a free tier during development.

The budget is a hint that avoids waste. The provider's own 429 is still what
decides.
"""

from __future__ import annotations

import hashlib
import json
import os
import time

from providers.base import LLMProvider
from providers.llm._openai_compatible import RateLimited
from providers.llm.budget import BudgetLedger

# Tried in this order. Gemini first for quality on the free tier, Groq for
# speed, Cerebras because its cap is measured in tokens rather than requests,
# OpenRouter last as the broadest safety net.
CHAIN = ("gemini", "groq", "cerebras", "openrouter")

KEY_ENV = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


def _build(name: str) -> LLMProvider:
    if name == "gemini":
        from providers.llm.gemini_provider import GeminiProvider

        return GeminiProvider()
    if name == "groq":
        from providers.llm.groq_provider import GroqProvider

        return GroqProvider()
    if name == "cerebras":
        from providers.llm.cerebras_provider import CerebrasProvider

        return CerebrasProvider()
    if name == "openrouter":
        from providers.llm.openrouter_provider import OpenRouterProvider

        return OpenRouterProvider()
    raise ValueError(f"Unknown LLM provider {name!r}")


def configured_providers() -> list[str]:
    """Chain members that have a key set, in order."""
    return [name for name in CHAIN if os.getenv(KEY_ENV[name], "")]


class ResponseCache:
    """Content-addressed cache of completions."""

    def __init__(self, directory=None):
        if directory is None:
            import paths

            directory = paths.cache_dir("llm")
        self.directory = str(directory)

    def _path(self, prompt: str, system: str | None) -> str:
        digest = hashlib.sha256(
            json.dumps([system or "", prompt], ensure_ascii=False).encode("utf-8")
        ).hexdigest()
        return os.path.join(self.directory, f"{digest}.json")

    def get(self, prompt: str, system: str | None) -> dict | None:
        try:
            with open(self._path(prompt, system)) as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, prompt: str, system: str | None, result: dict) -> None:
        # Creating the directory is inside the guard along with the write: a
        # cache that cannot be written is not a reason to fail a run, and an
        # unwritable path fails at the mkdir rather than at the open.
        try:
            os.makedirs(self.directory, exist_ok=True)
            with open(self._path(prompt, system), "w") as handle:
                json.dump(result, handle)
        except OSError:
            pass

    def forget(self, prompt: str, system: str | None) -> None:
        """Drops one entry, so a regenerate really does regenerate."""
        try:
            os.remove(self._path(prompt, system))
        except OSError:
            pass


class RouterLLMProvider(LLMProvider):
    """Tries each available provider in turn, respecting its budget."""

    def __init__(self, chain: list[str] | None = None, ledger=None, cache=None):
        self.chain = chain if chain is not None else list(CHAIN)
        self.ledger = ledger or BudgetLedger()
        self._cache = cache
        self._instances: dict[str, LLMProvider] = {}

    # ---- cache ------------------------------------------------------------

    @property
    def cache_enabled(self) -> bool:
        return os.getenv("SANTA_STUDIO_LLM_CACHE", "").lower() in ("1", "true", "yes")

    @property
    def cache(self) -> ResponseCache:
        if self._cache is None:
            self._cache = ResponseCache()
        return self._cache

    # ---- routing ----------------------------------------------------------

    def _instance(self, name: str) -> LLMProvider:
        if name not in self._instances:
            self._instances[name] = _build(name)
        return self._instances[name]

    def _candidates(self) -> list[str]:
        """Providers worth trying, best first.

        A provider with no key is dropped rather than attempted - on a fresh
        checkout with a single key, trying all four would mean three
        guaranteed failures on every call.
        """
        available = [name for name in self.chain if os.getenv(KEY_ENV.get(name, ""), "")]
        if not available:
            return []
        fresh = [n for n in available if not self.ledger.usage(n).exhausted]
        # If everything is nominally exhausted, try anyway: the ledger is a
        # local guess and the real quota may have rolled over.
        return fresh or available

    def complete(self, prompt: str, system: str | None = None) -> dict:
        if self.cache_enabled:
            cached = self.cache.get(prompt, system)
            if cached is not None:
                return cached

        candidates = self._candidates()
        if not candidates:
            raise RuntimeError(
                "No LLM provider is configured. Set at least one of "
                + ", ".join(KEY_ENV[name] for name in self.chain)
                + " in .env. All of them have a free tier."
            )

        failures = []
        for name in candidates:
            pause = self.ledger.wait_needed(name)
            if pause > 0:
                time.sleep(min(pause, 10.0))

            try:
                result = self._instance(name).complete(prompt, system=system)
            except RateLimited as e:
                # Believe the provider over the ledger, and stop asking today.
                self._mark_exhausted(name)
                failures.append(f"{name}: {e}")
                continue
            except Exception as e:
                failures.append(f"{name}: {e}")
                continue

            self.ledger.record(name)
            result = {**result, "provider": name}
            if self.cache_enabled:
                self.cache.put(prompt, system, result)
            return result

        raise RuntimeError(
            "Every configured LLM provider failed:\n  - " + "\n  - ".join(failures)
        )

    def _mark_exhausted(self, name: str) -> None:
        usage = self.ledger.usage(name)
        if usage.limit > 0:
            for _ in range(max(0, usage.limit - usage.used)):
                self.ledger.record(name)
        else:
            self.ledger.record(name)

    # ---- reporting --------------------------------------------------------

    def status(self) -> dict:
        """What the doctor check shows about routing."""
        return {
            "chain": list(self.chain),
            "configured": configured_providers(),
            "cache_enabled": self.cache_enabled,
            "budgets": self.ledger.report(),
        }
