from providers.base import LLMProvider
from providers.llm.gemini_provider import GeminiProvider
from providers.llm.groq_provider import GroqProvider


class FallbackLLMProvider(LLMProvider):
    """Tries each configured free-tier LLM in order, falling through to the
    next on any failure (quota exhausted, rate limited, missing key, etc).
    Only raises if every provider in the chain fails.
    """

    def __init__(self):
        self._providers = [GeminiProvider(), GroqProvider()]

    def complete(self, prompt: str, system: str | None = None) -> dict:
        errors = []
        for provider in self._providers:
            try:
                return provider.complete(prompt, system=system)
            except Exception as e:
                errors.append(f"{provider.__class__.__name__}: {e}")

        raise RuntimeError(
            "All LLM providers failed:\n" + "\n".join(errors)
        )
