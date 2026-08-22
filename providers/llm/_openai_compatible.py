"""Shared client for providers that speak the OpenAI chat-completions shape.

Cerebras and OpenRouter both expose that API, and so do most of the smaller
free tiers worth adding later. Talking to them over plain HTTP rather than
through their SDKs keeps the dependency list short - `requests` is already
here - and means a new provider is a base URL, a model name, and an
environment variable.
"""

from __future__ import annotations

import os

import requests

from providers.base import LLMProvider

TIMEOUT_SECONDS = 120


class OpenAICompatibleProvider(LLMProvider):
    """Base for any chat-completions endpoint.

    Subclasses set `base_url`, `model`, `api_key_env`, and `signup_url`.
    """

    base_url = ""
    model = ""
    api_key_env = ""
    signup_url = ""
    extra_headers: dict[str, str] = {}

    def _api_key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise RuntimeError(
                f"{self.api_key_env} is not set. Get a free key at {self.signup_url} "
                "and add it to .env."
            )
        return key

    def complete(self, prompt: str, system: str | None = None) -> dict:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
            **self.extra_headers,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json={"model": self.model, "messages": messages},
                timeout=TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise RuntimeError(f"{self.__class__.__name__} could not be reached: {e}") from e

        if response.status_code == 429:
            # Distinguished from other failures so the router can move on
            # quickly rather than treating a quota as a broken provider.
            raise RateLimited(f"{self.__class__.__name__} is rate limited or out of quota")
        if response.status_code >= 400:
            raise RuntimeError(
                f"{self.__class__.__name__} returned {response.status_code}: "
                f"{response.text[:300]}"
            )

        try:
            payload = response.json()
            text = payload["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError) as e:
            raise RuntimeError(
                f"{self.__class__.__name__} returned an unexpected response shape: "
                f"{response.text[:300]}"
            ) from e

        usage = payload.get("usage") or {}
        return {"text": text, "raw": {"usage": usage, "model": payload.get("model")}}


class RateLimited(RuntimeError):
    """Out of quota or asked to slow down, rather than actually broken."""
