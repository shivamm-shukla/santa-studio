"""A run that stopped because an allowance ran out, not because it broke.

These are different situations and they used to end identically: the second
retry was spent on a request that could not possibly succeed, and the run
halted with a message blaming the agent for something a provider decided. A
real run ended that way twice in one afternoon - once on Gemini's daily
request cap, once on Groq's tokens per minute.
"""

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
