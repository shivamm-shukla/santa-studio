import os

from google import genai
from google.genai import errors, types

from providers.base import LLMProvider

MODEL = "gemini-2.0-flash"  # free-tier friendly


class GeminiProvider(LLMProvider):
    """Google Gemini - free tier, no credit card required. Get a key at
    aistudio.google.com."""

    def __init__(self):
        self._client = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            api_key = os.getenv("GEMINI_API_KEY", "")
            if not api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set. Get a free key at "
                    "aistudio.google.com and add it to .env."
                )
            self._client = genai.Client(api_key=api_key)
        return self._client

    def complete(self, prompt: str, system: str | None = None) -> dict:
        client = self._get_client()
        config = types.GenerateContentConfig(system_instruction=system) if system else None
        try:
            response = client.models.generate_content(model=MODEL, contents=prompt, config=config)
        except errors.APIError as e:
            raise RuntimeError(f"Gemini API error: {e}") from e

        return {"text": response.text or "", "raw": {}}
