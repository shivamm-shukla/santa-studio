"""Reading, from a provider's own refusal, whether to wait or to give up on it.

A free tier says no in two very different ways and the router used to treat
them identically. Groq refusing a request because the last minute used 5,642
of its 8,000 tokens per minute is a "not this second" - it clears on its own,
and the reply says when: *try again in 12.93s*. Google refusing because the
project has spent all 20 of its daily requests for a model is a "not today".

Everything was read as the second. One brush against a per-minute token
ceiling took a provider out for the rest of the day, and the run halted with
every provider "failed" while two of them would have answered thirteen seconds
later. That is what parses here:

* **How long to wait**, from whichever form the provider used to say it -
  Google's `retryDelay`, an OpenAI-style `Retry-After`, or the sentence in the
  message. Returns None when the reply gives no number, because a wait we
  invented is worse than moving on to the next provider.
* **Whether the limit is a daily one**, which is the only case where the right
  answer is to stop asking until tomorrow.
"""

from __future__ import annotations

import re

# Enough patterns to cover the three refusals actually seen, in the order they
# are most reliable: a structured field, then a header, then prose.
_DELAY_PATTERNS = (
    r"['\"]?retry_?delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s?",
    r"['\"]?retry[- ]after['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)",
    r"(?:retry|try again)\s+in\s+(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)?",
    r"please\s+wait\s+(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds)",
)

# What a per-day exhaustion looks like in each provider's wording. A minute or
# a second in the name means it clears by itself.
_DAILY_MARKERS = (
    "perday",
    "per day",
    "per-day",
    "requests per day",
    "daily limit",
    "daily quota",
    "free_tier_requests",
    "quota exceeded for metric",
    "out of quota",
    "exceeded your current quota",
    "insufficient_quota",
)

_TRANSIENT_MARKERS = (
    "per minute",
    "per-minute",
    "tokens per minute",
    "tpm",
    "requests per minute",
    "rpm",
    "per second",
)


def retry_after(error: object) -> float | None:
    """Seconds the provider asked us to wait, or None if it did not say."""
    text = str(error or "")
    for pattern in _DELAY_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                seconds = float(match.group(1))
            except ValueError:
                continue
            if seconds >= 0:
                return seconds
    return None


def is_daily_exhaustion(error: object) -> bool:
    """Whether this refusal means "not today" rather than "not this second".

    A message naming both - Google's names the daily quota metric *and* gives a
    four second retryDelay - is read as daily, because the metric is the
    specific claim and the delay is boilerplate attached to every 429.
    """
    text = str(error or "").lower()
    if any(marker in text for marker in _DAILY_MARKERS):
        return True
    if any(marker in text for marker in _TRANSIENT_MARKERS):
        return False
    # An unexplained 429 is treated as the recoverable kind: the cost of being
    # wrong is one wasted request, against a provider lost for a day.
    return False
