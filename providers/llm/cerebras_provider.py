"""Cerebras - free tier, very fast inference on open models.

Its free tier is measured in tokens per day rather than requests, which makes
it the useful one to fall back to when a request-capped provider has run out
for the day.
"""

from providers.llm._openai_compatible import OpenAICompatibleProvider


class CerebrasProvider(OpenAICompatibleProvider):
    base_url = "https://api.cerebras.ai/v1"
    model = "llama-3.3-70b"
    api_key_env = "CEREBRAS_API_KEY"
    signup_url = "cloud.cerebras.ai"
