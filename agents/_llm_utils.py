"""Shared helper for agents that call the LLM provider and expect JSON back."""

import json
import re


def call_llm_json(provider, prompt: str, system: str) -> dict:
    """Calls provider.complete(), extracts and parses a JSON object from the
    response text (tolerating markdown code fences), and returns it.
    Raises ValueError on any failure - callers should catch this and return
    the standard {"success": False, "error": ...} agent contract.
    """
    result = provider.complete(prompt, system=system)
    text = result["text"].strip()

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text[:200]}")

    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response was not valid JSON: {e}. Text: {text[:200]}") from e
