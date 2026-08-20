import os

import anthropic

from providers.base import LLMProvider

# Sonnet 5, not Opus: this is a $0-budget project where Claude is the one
# paid dependency - Sonnet is materially cheaper while still strong enough
# for research/script/fact-check reasoning. Bump to claude-opus-5 later if
# output quality demands it once real revenue funds it.
MODEL = "claude-sonnet-5"


class ClaudeProvider(LLMProvider):
    """Anthropic Claude - the one paid provider in this stack."""

    def __init__(self):
        self._client = None

    def _get_client(self) -> anthropic.Anthropic:
        if self._client is None:
            if not os.getenv("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Add it to .env to enable "
                    "real Claude calls (see .env.example)."
                )
            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, prompt: str, system: str | None = None) -> dict:
        client = self._get_client()
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system or anthropic.NOT_GIVEN,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as e:
            raise RuntimeError(f"Claude authentication failed: {e}") from e
        except anthropic.RateLimitError as e:
            raise RuntimeError(f"Claude rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise RuntimeError(f"Claude API error ({e.status_code}): {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise RuntimeError(f"Claude connection error: {e}") from e

        text = "".join(block.text for block in response.content if block.type == "text")
        return {"text": text, "raw": response.to_dict()}
