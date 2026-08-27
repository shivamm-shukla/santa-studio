"""A run that stopped because an allowance ran out, not because it broke.

These are different situations and they used to end identically: the second
retry was spent on a request that could not possibly succeed, and the run
halted with a message blaming the agent for something a provider decided. A
real run ended that way twice in one afternoon - once on Gemini's daily
request cap, once on Groq's tokens per minute.
"""

import pytest
import time
from datetime import datetime, timezone

import pytest

import manager


GEMINI_DAILY = (
    "Gemini API error: 429 RESOURCE_EXHAUSTED. You exceeded your current quota. "
    "Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 20"
)
GROQ_MINUTE = (
    "Rate limit reached on tokens per minute (TPM): Limit 8000, Used 5642. "
    "Please try again in 12.93s."
)


# ---- telling the two apart --------------------------------------------------


def test_a_spent_daily_allowance_parks_until_the_rollover():
    when = manager._quota_wait(GEMINI_DAILY)

    assert when is not None
    moment = datetime.fromtimestamp(when, tz=timezone.utc)
    assert moment.hour == 0, "daily allowances roll over at midnight UTC"
    assert when > time.time()


def test_a_per_minute_limit_is_not_worth_parking_for():
    """The router already waits out a short delay and falls through to the
    next provider. Stopping a run for thirteen seconds helps nobody; if every
    provider still failed, an ordinary retry is the right answer."""
    assert manager._quota_wait(GROQ_MINUTE) is None


def test_an_ordinary_failure_is_not_a_parked_run():
    """Parking a genuinely broken agent turns a run that stops loudly into one
    that looks like it is waiting."""
    assert manager._quota_wait("KeyError: 'scenes'") is None
    assert manager._quota_wait("") is None
    assert manager._quota_wait(None) is None


def test_a_429_with_no_stated_delay_is_not_guessed_at():
    assert manager._quota_wait("429 Too Many Requests") is None


# ---- what the pipeline does with it ----------------------------------------


class _Agent:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def run(self, input_data, config):
        self.calls += 1
        return {"success": False, "output": None, "error": self.error}


@pytest.fixture
def parked_manager(tmp_path, monkeypatch):
    from state import PipelineState

    def build(error):
        agent = _Agent(error)
        monkeypatch.setitem(manager.AGENT_FOR_STATE, "TOPIC_SELECTION", agent)
        state = PipelineState(niche="mining", user_topic="Kolar", current_state="TOPIC_SELECTION")
        pipeline = manager.PipelineManager(state, {"ACTIVE_PROVIDERS": {}}, None,
                                           runs_dir=str(tmp_path))
        return pipeline, agent, state

    return build


def test_a_spent_allowance_does_not_burn_the_retry(parked_manager):
    """The same request a second later fails the same way."""
    pipeline, agent, _ = parked_manager(GEMINI_DAILY)

    with pytest.raises(manager.PipelineParked):
        pipeline._run_agent_with_retry("TOPIC_SELECTION")

    assert agent.calls == 1


def test_an_ordinary_failure_still_gets_its_second_chance(parked_manager):
    pipeline, agent, _ = parked_manager("KeyError: 'scenes'")

    with pytest.raises(manager.PipelineHalted):
        pipeline._run_agent_with_retry("TOPIC_SELECTION")

    assert agent.calls == 2


def test_the_state_remembers_when_to_come_back(parked_manager):
    pipeline, _, state = parked_manager(GEMINI_DAILY)

    with pytest.raises(manager.PipelineParked) as raised:
        pipeline._run_agent_with_retry("TOPIC_SELECTION")

    assert state.parked_until == raised.value.resume_after
    assert state.parked_until > time.time()


def test_parking_is_recorded_as_parked_and_not_as_an_error(parked_manager):
    pipeline, _, state = parked_manager(GEMINI_DAILY)

    with pytest.raises(manager.PipelineParked):
        pipeline._run_agent_with_retry("TOPIC_SELECTION")

    events = [entry["event"] for entry in state.history]
    assert "parked" in events
    assert "error" not in events


def test_a_parked_run_is_still_caught_by_anything_watching_for_a_halt(parked_manager):
    """Every existing caller catches PipelineHalted; none of them knew about
    parking until now."""
    pipeline, _, _ = parked_manager(GEMINI_DAILY)

    with pytest.raises(manager.PipelineHalted):
        pipeline._run_agent_with_retry("TOPIC_SELECTION")


def test_the_message_says_what_it_is_waiting_for(parked_manager):
    pipeline, _, _ = parked_manager(GEMINI_DAILY)

    with pytest.raises(manager.PipelineParked) as raised:
        pipeline._run_agent_with_retry("TOPIC_SELECTION")

    message = str(raised.value)
    assert "out of allowance" in message and "not broken" in message
    assert "Parked until" in message


# ---------------------------------------------------------------------------
# When to come back, according to the providers rather than the calendar
# ---------------------------------------------------------------------------

GROQ_AND_GEMINI = """Every configured LLM provider failed:
  - gemini: Gemini API error: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429,
    'message': 'Quota exceeded for metric:
    generativelanguage.googleapis.com/generate_content_free_tier_requests,
    limit: 20, model: gemini-3.6-flash. Please retry in 21.563970791s.'}}
  - groq: Groq API error: Error code: 429 - {'error': {'message': 'Rate limit
    reached for model `openai/gpt-oss-120b` on tokens per day (TPD): Limit
    200000, Used 198702. Please try again in 14m49.056s.'}}"""


def test_a_provider_that_says_when_it_will_be_back_is_believed():
    """Groq's daily token budget is a rolling window and it says so. Taking
    midnight UTC for an answer parked a run for ten hours to wait out fifteen
    minutes."""
    import time

    import manager

    when = manager._quota_wait(GROQ_AND_GEMINI)

    assert when is not None
    waits = (when - time.time()) / 60
    assert 10 < waits < 25, f"expected about fifteen minutes, got {waits:.0f}"


def test_the_run_comes_back_when_the_first_provider_does_not_the_last():
    """One working provider is enough to carry on."""
    import time

    import manager

    only_gemini = GROQ_AND_GEMINI.split("- groq")[0]
    both = manager._quota_wait(GROQ_AND_GEMINI)
    gemini_alone = manager._quota_wait(only_gemini)

    assert both < gemini_alone, "the provider that recovers first should decide"
    assert (gemini_alone - time.time()) > 3600, "a daily request cap waits for the day"


def test_the_boilerplate_delay_on_a_daily_cap_is_not_mistaken_for_an_answer():
    """Google attaches a few seconds to every 429, including the ones it will
    not honour until tomorrow."""
    import time

    import manager

    daily = ("Quota exceeded for metric: generate_content_free_tier_requests, "
             "limit: 20. Please retry in 21.5s.")

    assert (manager._quota_wait(daily) - time.time()) > 3600


def test_a_per_minute_ceiling_is_still_not_parked():
    import manager

    assert manager._quota_wait("rate_limit_exceeded on tokens per minute (TPM)") is None
    assert manager._quota_wait("connection reset") is None


def test_each_provider_the_router_tried_is_read_on_its_own():
    import manager

    assert len(manager._per_provider(GROQ_AND_GEMINI)) == 2
    assert len(manager._per_provider("a single unstructured failure")) == 1


def test_a_delay_written_in_minutes_is_not_read_as_seconds():
    """"14m49.056s" came out as fourteen seconds."""
    from providers.llm import backoff

    assert backoff.retry_after("Please try again in 14m49.056s") == pytest.approx(889, abs=1)
    assert backoff.retry_after("try again in 1h2m3s") == pytest.approx(3723, abs=1)
    assert backoff.retry_after("Please retry in 21.5s") == pytest.approx(21.5)
    assert backoff.retry_after("Retry-After: 30") == pytest.approx(30)
