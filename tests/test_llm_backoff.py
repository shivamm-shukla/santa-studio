"""Telling "not this second" apart from "not today".

A free tier says no in two ways and the router used to treat them identically,
so one brush against a tokens-per-minute ceiling took a provider out for the
rest of the day - and a run halted reporting every provider failed while two
of them would have answered thirteen seconds later. The strings below are the
real refusals that caused it, trimmed.
"""

from providers.llm import backoff

GROQ_PER_MINUTE = (
    "Groq API error: Error code: 429 - {'error': {'message': 'Rate limit reached for "
    "model `openai/gpt-oss-120b` in organization `org_01m` service tier `on_demand` on "
    "tokens per minute (TPM): Limit 8000, Used 5642, Requested 4082. Please try again "
    "in 12.93s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
)

GEMINI_PER_DAY = (
    "Gemini API error: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You "
    "exceeded your current quota. Quota exceeded for metric: generativelanguage."
    "googleapis.com/generate_content_free_tier_requests, limit: 20, model: "
    "gemini-3.6-flash. Please retry in 3.956498757s.', 'details': [{'quotaId': "
    "'GenerateRequestsPerDayPerProjectPerModel-FreeTier'}, {'retryDelay': '3s'}]}}"
)


# ---- how long to wait ------------------------------------------------------


def test_a_delay_written_in_prose_is_read():
    assert backoff.retry_after(GROQ_PER_MINUTE) == 12.93


def test_a_delay_in_a_structured_field_is_read():
    assert backoff.retry_after("{'retryDelay': '3s'}") == 3.0


def test_a_retry_after_header_is_read():
    assert backoff.retry_after("Retry-After: 8") == 8.0


def test_a_refusal_that_names_no_delay_gets_none():
    """A wait we invented is worse than moving to the next provider."""
    assert backoff.retry_after("429 Too Many Requests") is None
    assert backoff.retry_after("") is None
    assert backoff.retry_after(None) is None


# ---- whether the day is done -----------------------------------------------


def test_a_tokens_per_minute_ceiling_is_not_the_end_of_the_day():
    assert backoff.is_daily_exhaustion(GROQ_PER_MINUTE) is False


def test_a_spent_daily_quota_is():
    assert backoff.is_daily_exhaustion(GEMINI_PER_DAY) is True


def test_a_daily_metric_wins_over_the_delay_attached_to_every_429():
    """Google's reply names the daily quota and still says retry in 3s. The
    metric is the specific claim; the delay is boilerplate."""
    assert backoff.retry_after(GEMINI_PER_DAY) is not None
    assert backoff.is_daily_exhaustion(GEMINI_PER_DAY) is True


def test_an_unexplained_refusal_is_treated_as_the_recoverable_kind():
    """One wasted request against losing a provider for a day."""
    assert backoff.is_daily_exhaustion("429 Too Many Requests") is False
