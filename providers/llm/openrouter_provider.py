"""OpenRouter - one key, many free models behind an OpenAI-compatible API.

Kept last in the chain because it is the broadest safety net rather than the
fastest option: when the others are exhausted, there is usually still a free
model here that will answer.
"""

import os

from providers.llm._openai_compatible import OpenAICompatibleProvider

# Overridable because which models carry a `:free` tag changes often, and
# pinning one in code means a broken provider the day it moves.
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


class OpenRouterProvider(OpenAICompatibleProvider):
    base_url = "https://openrouter.ai/api/v1"
    api_key_env = "OPENROUTER_API_KEY"
    signup_url = "openrouter.ai/keys"

    @property
    def model(self) -> str:
        return os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL)
