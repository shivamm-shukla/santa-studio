"""What the topic agent is given to work from.

Left to itself the model proposes the three topics a language model finds
plausible, which is a different thing from the three a viewer wants. These
cover that real readership reaches the prompt, and that a niche nobody is
reading about does not stop a run.
"""

import agents.topic_agent as topic_agent


class _Provider:
    def __init__(self):
        self.prompt = ""

    def complete(self, prompt, system=None):
        self.prompt = prompt
        return {"text": '{"topics": ["One", "Two", "Three"]}', "raw": {}}


def _run(monkeypatch, articles):
    provider = _Provider()
    monkeypatch.setattr(topic_agent, "get_provider", lambda kind, cfg: provider)
    monkeypatch.setattr(topic_agent.trending, "candidates", lambda *a, **k: articles)
    result = topic_agent.run(
        {"niche": "industrial history", "preferences": {}, "user_topic": None}, {}
    )
    return result, provider


TRENDING = [
    {"title": "Proto-industrialization", "daily_views": 306, "momentum": 1.57, "score": 3.89},
    {"title": "Industrial Revolution", "daily_views": 2217, "momentum": 1.09, "score": 3.65},
]


def test_the_subjects_people_are_reading_reach_the_prompt(monkeypatch):
    result, provider = _run(monkeypatch, TRENDING)

    assert result["success"]
    assert "Proto-industrialization" in provider.prompt
    assert "Industrial Revolution" in provider.prompt


def test_the_numbers_go_with_them(monkeypatch):
    """A subject read more than usual is the signal; the model needs to see it."""
    _, provider = _run(monkeypatch, TRENDING)

    assert "306" in provider.prompt
    assert "1.57x" in provider.prompt


def test_the_model_is_told_not_to_wander_off_them(monkeypatch):
    _, provider = _run(monkeypatch, TRENDING)

    assert "Do not propose a topic that has nothing to do with any of them" in provider.prompt


def test_a_niche_nobody_reads_about_still_proposes_topics(monkeypatch):
    """Not knowing what is trending should narrow the choice, not end the run."""
    result, provider = _run(monkeypatch, [])

    assert result["success"]
    assert result["output"]["topics"] == ["One", "Two", "Three"]
    assert "actually reading" not in provider.prompt


def test_a_topic_the_owner_gave_is_taken_as_it_is(monkeypatch):
    """No search, no readership lookup, no model call."""
    monkeypatch.setattr(
        topic_agent.trending, "candidates",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("looked up trends anyway")),
    )

    result = topic_agent.run({"niche": "x", "user_topic": "Why KGF closed"}, {})

    assert result["output"]["topics"] == ["Why KGF closed"]
