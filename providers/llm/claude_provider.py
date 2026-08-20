from providers.base import LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude - the one paid provider in this stack. Cheap relative
    to quality, and used for every reasoning-heavy agent (research, script,
    fact-check)."""

    def complete(self, prompt: str, system: str | None = None) -> dict:
        # TODO: wire real Claude API call here (anthropic SDK, messages.create)
        return {
            "text": f"[stub claude response for prompt: {prompt[:60]}...]",
            "raw": {},
        }
