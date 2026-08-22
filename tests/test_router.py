"""The LLM router: budgets, ordering, and not wasting calls.

No network. Providers are stubbed, because what is being tested is the routing
decision - which provider gets asked, and which gets skipped - not whether a
given API replies.
"""

import pytest

from providers.base import LLMProvider
from providers.llm import router as router_module
from providers.llm._openai_compatible import RateLimited
from providers.llm.budget import BudgetLedger
from providers.llm.router import ResponseCache, RouterLLMProvider


class Stub(LLMProvider):
    def __init__(self, name, fails=None):
        self.name = name
        self.fails = fails
        self.calls = 0

    def complete(self, prompt, system=None):
        self.calls += 1
        if self.fails:
            raise self.fails
        return {"text": f"{self.name} says hello", "raw": {}}


@pytest.fixture
def stubs(monkeypatch):
    """Replaces every provider with a stub and gives the test control of them."""
    built = {}

    def fake_build(name):
        return built.setdefault(name, Stub(name))

    monkeypatch.setattr(router_module, "_build", fake_build)
    return built


@pytest.fixture
def all_keys(monkeypatch):
    for env in router_module.KEY_ENV.values():
        monkeypatch.setenv(env, "test-key")


@pytest.fixture
def ledger(tmp_path):
    return BudgetLedger(tmp_path / "budget.json")


def make_router(ledger, **kwargs):
    return RouterLLMProvider(ledger=ledger, **kwargs)


# --------------------------------------------------------------------------
# Ordering
# --------------------------------------------------------------------------

def test_the_first_configured_provider_is_used(stubs, all_keys, ledger):
    result = make_router(ledger).complete("hi")
    assert result["provider"] == "gemini"
    assert stubs["gemini"].calls == 1


def test_a_failure_falls_through_to_the_next(stubs, all_keys, ledger, monkeypatch):
    monkeypatch.setattr(
        router_module, "_build",
        lambda name: stubs.setdefault(
            name, Stub(name, fails=RuntimeError("down") if name == "gemini" else None)
        ),
    )
    assert make_router(ledger).complete("hi")["provider"] == "groq"


def test_providers_without_a_key_are_never_tried(stubs, ledger, monkeypatch):
    # On a fresh checkout with one key, trying all four means three guaranteed
    # failures on every single call.
    for env in router_module.KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "test-key")

    assert make_router(ledger).complete("hi")["provider"] == "groq"
    assert "gemini" not in stubs


def test_no_keys_at_all_says_which_ones_to_set(stubs, ledger, monkeypatch):
    for env in router_module.KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    with pytest.raises(RuntimeError) as caught:
        make_router(ledger).complete("hi")
    assert "GEMINI_API_KEY" in str(caught.value)
    assert "free tier" in str(caught.value)


def test_every_provider_failing_reports_all_of_them(stubs, all_keys, ledger, monkeypatch):
    monkeypatch.setattr(
        router_module, "_build",
        lambda name: stubs.setdefault(name, Stub(name, fails=RuntimeError(f"{name} broke"))),
    )
    with pytest.raises(RuntimeError) as caught:
        make_router(ledger).complete("hi")
    message = str(caught.value)
    for name in router_module.CHAIN:
        assert f"{name} broke" in message


# --------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------

def test_a_successful_call_is_recorded(stubs, all_keys, ledger):
    make_router(ledger).complete("hi")
    assert ledger.usage("gemini").used == 1


def test_an_exhausted_provider_is_skipped_rather_than_tried(stubs, all_keys, ledger, monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_LIMIT", "2")
    for _ in range(2):
        ledger.record("gemini")

    assert make_router(ledger).complete("hi")["provider"] == "groq"
    assert "gemini" not in stubs, "an exhausted provider should not even be built"


def test_a_rate_limit_response_stops_further_attempts_today(stubs, all_keys, ledger, monkeypatch):
    monkeypatch.setenv("GEMINI_DAILY_LIMIT", "50")
    monkeypatch.setattr(
        router_module, "_build",
        lambda name: stubs.setdefault(
            name, Stub(name, fails=RateLimited("out of quota") if name == "gemini" else None)
        ),
    )
    router = make_router(ledger)
    assert router.complete("hi")["provider"] == "groq"
    # The provider's own 429 is believed over the local counter.
    assert ledger.usage("gemini").exhausted


def test_everything_exhausted_still_tries_rather_than_giving_up(stubs, all_keys, ledger, monkeypatch):
    # The ledger is a local guess; the real quota may have rolled over.
    for name in router_module.CHAIN:
        monkeypatch.setenv(f"{name.upper()}_DAILY_LIMIT", "1")
        ledger.record(name)
    assert make_router(ledger).complete("hi")["provider"] == "gemini"


def test_rate_limiting_asks_for_a_pause_between_calls(ledger, monkeypatch):
    monkeypatch.setenv("GEMINI_MIN_INTERVAL", "30")
    ledger.record("gemini")
    assert ledger.wait_needed("gemini") > 25


def test_counters_reset_on_a_new_day(ledger):
    ledger.record("groq")
    assert ledger.usage("groq").used == 1

    import json

    data = json.loads(open(ledger.path).read())
    data["day"] = "2000-01-01"
    open(ledger.path, "w").write(json.dumps(data))

    assert ledger.usage("groq").used == 0


def test_the_ledger_is_shared_between_processes(tmp_path):
    # Four frontends run as separate processes against one quota.
    first = BudgetLedger(tmp_path / "budget.json")
    second = BudgetLedger(tmp_path / "budget.json")
    first.record("groq")
    assert second.usage("groq").used == 1


def test_a_corrupt_ledger_does_not_break_routing(stubs, all_keys, tmp_path):
    path = tmp_path / "budget.json"
    path.write_text("{ this is not json")
    assert make_router(BudgetLedger(path)).complete("hi")["provider"] == "gemini"


# --------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------

def test_the_cache_is_off_by_default(stubs, all_keys, ledger, monkeypatch, tmp_path):
    # A review gate's regenerate sends the same prompt; a cache would hand back
    # the same answer, which is the opposite of what was asked for.
    monkeypatch.delenv("SANTA_STUDIO_LLM_CACHE", raising=False)
    router = make_router(ledger, cache=ResponseCache(tmp_path))
    router.complete("hi")
    router.complete("hi")
    assert stubs["gemini"].calls == 2


def test_the_cache_serves_a_repeat_when_switched_on(stubs, all_keys, ledger, monkeypatch, tmp_path):
    monkeypatch.setenv("SANTA_STUDIO_LLM_CACHE", "1")
    router = make_router(ledger, cache=ResponseCache(tmp_path))
    first = router.complete("hi", system="be brief")
    second = router.complete("hi", system="be brief")
    assert stubs["gemini"].calls == 1
    assert first == second


def test_the_cache_distinguishes_prompts_and_systems(stubs, all_keys, ledger, monkeypatch, tmp_path):
    monkeypatch.setenv("SANTA_STUDIO_LLM_CACHE", "1")
    router = make_router(ledger, cache=ResponseCache(tmp_path))
    router.complete("one")
    router.complete("two")
    router.complete("one", system="different")
    assert stubs["gemini"].calls == 3


def test_forgetting_an_entry_makes_a_regenerate_real(stubs, all_keys, ledger, monkeypatch, tmp_path):
    monkeypatch.setenv("SANTA_STUDIO_LLM_CACHE", "1")
    cache = ResponseCache(tmp_path)
    router = make_router(ledger, cache=cache)
    router.complete("hi")
    cache.forget("hi", None)
    router.complete("hi")
    assert stubs["gemini"].calls == 2


def test_an_unwritable_cache_does_not_fail_a_run(stubs, all_keys, ledger, monkeypatch):
    monkeypatch.setenv("SANTA_STUDIO_LLM_CACHE", "1")
    router = make_router(ledger, cache=ResponseCache("/proc/nowhere/at/all"))
    assert router.complete("hi")["text"]


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def test_status_reports_what_is_configured(stubs, ledger, monkeypatch):
    for env in router_module.KEY_ENV.values():
        monkeypatch.delenv(env, raising=False)
    monkeypatch.setenv("CEREBRAS_API_KEY", "test-key")

    status = make_router(ledger).status()
    assert status["configured"] == ["cerebras"]
    assert status["chain"] == list(router_module.CHAIN)
    assert "gemini" in status["budgets"]


def test_the_registry_resolves_the_router():
    from providers.registry import get_provider

    provider = get_provider("llm", {"ACTIVE_PROVIDERS": {"llm": "router"}})
    assert isinstance(provider, RouterLLMProvider)
