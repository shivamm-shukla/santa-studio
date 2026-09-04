import os

import groq

from providers.base import LLMProvider

MODEL = "openai/gpt-oss-120b"  # free tier, strongest general model currently on Groq

# Shared with the other providers - see providers/llm/_openai_compatible.py for
# why asking for this at all was the fix.
from providers.llm._openai_compatible import MAX_OUTPUT_TOKENS  # noqa: E402


class GroqProvider(LLMProvider):
    """Groq - free tier, very fast inference on open models. Get a key at
    console.groq.com."""

    def __init__(self):
        self._client = None

    def _get_client(self) -> groq.Groq:
        if self._client is None:
            api_key = os.getenv("GROQ_API_KEY", "")
            if not api_key:
                raise RuntimeError(
                    "GROQ_API_KEY is not set. Get a free key at "
                    "console.groq.com and add it to .env."
                )
            self._client = groq.Groq(api_key=api_key)
        return self._client

    def complete(self, prompt: str, system: str | None = None) -> dict:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        try:
            response = client.chat.completions.create(
                model=MODEL, messages=messages, max_tokens=MAX_OUTPUT_TOKENS
            )
        except groq.GroqError as e:
            raise RuntimeError(f"Groq API error: {e}") from e

        return {"text": response.choices[0].message.content or "", "raw": {}}
