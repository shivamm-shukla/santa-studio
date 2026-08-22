"""Tests for Phase 5 Research Swarm: specialist tracks, synthesis, and confidence fact-checking."""

import pytest

import agents.factcheck_agent as factcheck_agent
import agents.research_agent as research_agent


def test_research_swarm_synthesis(monkeypatch):
    class FakeLLMProvider:
        def complete(self, prompt, system=None):
            if "Synthesize" in prompt:
                return {
                    "text": '{"research_summary": "Tipu Sultan revolutionized rocketry in 18th century India with iron casing.", "sources": [{"title": "Mysorean rockets", "url": "https://en.wikipedia.org/wiki/Mysorean_rockets", "key_facts": ["Iron casings allowed higher burst pressure"]}]}',
                    "raw": {}
                }
            elif "timeline" in prompt:
                return {
                    "text": '{"timeline": [{"date": "1792", "event": "Battle of Srirangapatna", "significance": "Rocket deployment"}]}',
                    "raw": {}
                }
            elif "metrics" in prompt:
                return {
                    "text": '{"metrics": [{"metric": "Range", "value": "2 km", "context": "Iron-cased rockets"}]}',
                    "raw": {}
                }
            elif "disputes" in prompt:
                return {
                    "text": '{"disputes": [{"claim": "Invented rockets", "viewpoint_a": "First military use", "viewpoint_b": "Song dynasty origins"}]}',
                    "raw": {}
                }
            return {"text": "{}", "raw": {}}

    monkeypatch.setattr(research_agent, "get_provider", lambda kind, cfg: FakeLLMProvider())

    res = research_agent.run({"topic": "Mysorean rockets"}, {"ACTIVE_PROVIDERS": {"llm": "fake"}})
    assert res["success"] is True
    output = res["output"]
    assert "research_summary" in output
    assert len(output["chronology"]) >= 1
    assert len(output["numbers_and_data"]) >= 1
    assert len(output["disputed_claims"]) >= 1
    assert len(output["sources"]) >= 1


def test_factcheck_agent_confidence_scoring(monkeypatch):
    class FakeLLMProvider:
        def complete(self, prompt, system=None):
            return {
                "text": '{"verified_claims": ["Iron-cased rockets were used in 1792"], "flagged_claims": ["Rockets reached outer space"], "confidence": {"Iron-cased rockets were used in 1792": "high", "Rockets reached outer space": "low"}}',
                "raw": {}
            }

    monkeypatch.setattr(factcheck_agent, "get_provider", lambda kind, cfg: FakeLLMProvider())

    input_data = {
        "research_summary": "Summary text",
        "sources": [{"title": "Source 1", "key_facts": ["Iron-cased rockets were used in 1792"]}],
        "numbers_and_data": [{"metric": "Range", "value": "2km", "context": "test"}],
    }

    res = factcheck_agent.run(input_data, {"ACTIVE_PROVIDERS": {"llm": "fake"}})
    assert res["success"] is True
    output = res["output"]
    assert len(output["verified_claims"]) == 1
    assert len(output["flagged_claims"]) == 1
    assert output["confidence_scores"]["Iron-cased rockets were used in 1792"] == "high"
