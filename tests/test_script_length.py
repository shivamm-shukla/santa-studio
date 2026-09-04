"""Getting a video that is as long as it was asked to be.

Runs came out at one to three minutes against a five to twenty minute
target, and nothing anywhere compared the two. Two separate causes, both
pinned here: nobody measured the draft, and nobody could have written twenty
minutes in one reply even if they had.
"""

import pytest

from agents import script_agent

CLAIMS = [
    "The Ideal X carried 58 containers on its 1956 voyage.",
    "Container shipping cut port loading costs by more than 90 percent.",
]


class _Writer:
    """Stands in for the model, returning scripts of a chosen length.

    Records every prompt so a test can ask what the writer was actually
    told, which is where most of these faults live.
    """

    def __init__(self, *word_counts, outline=None):
        self.word_counts = list(word_counts)
        self.outline = outline
        self.prompts = []
        self.systems = []

    def __call__(self, provider, prompt, system, list_key=None):
        self.prompts.append(prompt)
        self.systems.append(system)

        if list_key == "chapters":
            return {"chapters": self.outline}

        words = self.word_counts[min(len(self.prompts) - 1, len(self.word_counts) - 1)]
        return {"scenes": [{
            "timestamp_estimate": "0:00-0:20",
            "text": " ".join(["shipping"] * words),
            "visual_hint": "a port",
        }]}


def _run(monkeypatch, writer, **overrides):
    monkeypatch.setattr(script_agent, "call_llm_json", writer)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())
    return script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "topic": "containers",
         **overrides},
        {},
    )


# --------------------------------------------------------------------------
# Measuring the draft
# --------------------------------------------------------------------------

def test_a_draft_far_under_the_target_is_sent_back(monkeypatch):
    writer = _Writer(200, 600)   # a 200-word reply against a 5-minute target
    result = _run(monkeypatch, writer, target_length_minutes=5)

    assert result["success"] is True
    assert len(writer.prompts) == 2, "the short draft has to be sent back"
    assert "too short" in writer.prompts[1]
    assert "200 words" in writer.prompts[1]
    assert "750" in writer.prompts[1], "the redraft has to say what the target is"


def test_being_short_is_never_a_reason_to_invent(monkeypatch):
    """The one thing a writer must not do to fill a length."""
    writer = _Writer(100, 700)
    _run(monkeypatch, writer, target_length_minutes=5)

    redraft = writer.prompts[1]
    assert "do not invent" in redraft.lower()
    assert "go deeper" in redraft.lower()


def test_a_draft_of_the_right_length_is_not_written_twice(monkeypatch):
    writer = _Writer(700)
    _run(monkeypatch, writer, target_length_minutes=5)

    assert len(writer.prompts) == 1


def test_a_writer_that_will_not_reach_the_length_still_ships_and_says_so(monkeypatch):
    """The verified material may genuinely not carry the length asked for.

    A short video is a video; failing the run over it would not make the
    sources any deeper.
    """
    writer = _Writer(150)
    result = _run(monkeypatch, writer, target_length_minutes=5)

    assert result["success"] is True
    assert result["output"]["short_by_words"] == 750 - 150
    assert len(writer.prompts) == script_agent.DRAFTS


def test_a_little_under_the_target_is_close_enough(monkeypatch):
    """The writer is also told to say less rather than pad.

    Those two instructions have to be able to coexist, so the floor is a
    proportion of the target rather than the target itself.
    """
    writer = _Writer(int(750 * script_agent.MIN_LENGTH_RATIO) + 10)
    _run(monkeypatch, writer, target_length_minutes=5)

    assert len(writer.prompts) == 1


# --------------------------------------------------------------------------
# Writing it in chapters
# --------------------------------------------------------------------------

OUTLINE = [
    {"title": "The box", "purpose": "open the question", "beats": ["a dock in 1956"],
     "claims": [CLAIMS[0]], "target_words": 600},
    {"title": "What it cost", "purpose": "raise the stakes", "beats": ["the strike"],
     "claims": [CLAIMS[1]], "target_words": 600},
    {"title": "After", "purpose": "land it", "beats": ["today"],
     "claims": [CLAIMS[1]], "target_words": 600},
]


def test_a_long_video_is_planned_before_it_is_written(monkeypatch):
    """Twenty minutes asked for in one reply comes back as two.

    Every model here hits an output ceiling or simply stops, and the salvage
    path keeps whatever arrived - so the length was lost with no error. A
    long script is outlined and then written a chapter at a time.
    """
    writer = _Writer(600, outline=OUTLINE)
    result = _run(monkeypatch, writer, target_length_minutes=12)

    assert result["success"] is True
    assert writer.systems[0] == script_agent.OUTLINE_SYSTEM
    assert len(writer.prompts) == 1 + len(OUTLINE), "one outline, then one call per chapter"
    assert len(result["output"]["script_text"].split()) == 600 * len(OUTLINE)


def test_a_short_video_is_not_outlined(monkeypatch):
    """Outlining six scenes would spend a request from a daily allowance."""
    writer = _Writer(700)
    _run(monkeypatch, writer, target_length_minutes=5)

    assert len(writer.prompts) == 1
    assert script_agent.OUTLINE_SYSTEM not in writer.systems


def test_each_chapter_is_told_where_it_sits_and_what_it_owes(monkeypatch):
    writer = _Writer(600, outline=OUTLINE)
    _run(monkeypatch, writer, target_length_minutes=12)

    opening, middle, closing = writer.prompts[1], writer.prompts[2], writer.prompts[3]
    assert "Start cold" in opening
    assert "owing the next one something" in middle
    assert "last chapter" in closing


def test_the_outlines_word_budgets_are_made_to_sum_to_the_target(monkeypatch):
    """An outline whose chapters add up to nine hundred words is a plan for a
    six-minute video however long it says it is at the top."""
    thin = [dict(chapter, target_words=100) for chapter in OUTLINE]
    budgeted = script_agent._budget(thin, 1800)

    assert sum(c["target_words"] for c in budgeted) == pytest.approx(1800, abs=5)


def test_a_chapter_with_no_budget_at_all_still_gets_one():
    broken = [{"title": "a"}, {"title": "b", "target_words": "not a number"}]
    budgeted = script_agent._budget(broken, 1200)

    assert all(c["target_words"] >= 120 for c in budgeted)


def test_timestamps_run_continuously_through_the_assembled_script(monkeypatch):
    """Each chapter numbers itself from zero.

    The timeline builder reads these to decide how long each scene holds the
    screen, and refuses a sequence that does not increase - so before this
    every long video was silently falling back to word counts.
    """
    writer = _Writer(600, outline=OUTLINE)
    result = _run(monkeypatch, writer, target_length_minutes=12)

    import timeline_builder

    scenes = result["output"]["scenes"]
    starts = [timeline_builder._parse_timestamp(s["timestamp_estimate"]) for s in scenes]
    assert None not in starts
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts)
    assert timeline_builder._spans_from_estimates(scenes) is not None


def test_a_plan_written_for_other_material_is_not_reused(monkeypatch, tmp_path):
    """A script is re-run when something upstream changed, too.

    Research goes back for better sources, the fact-checker passes a
    different set of claims - and an outline drawn up for the old claims
    would quietly write the old video again.
    """
    import runlog

    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    with runlog.bind("run-material", "SCRIPTING"):
        one = script_agent._plan_key("the claims we had", 1800)
        two = script_agent._plan_key("an entirely different set of claims", 1800)
        again = script_agent._plan_key("the claims we had", 1800)

    assert one != two
    assert one == again, "the same material has to reach the same saved plan"


def test_a_longer_target_is_not_written_from_the_short_ones_plan(monkeypatch, tmp_path):
    import runlog

    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))
    with runlog.bind("run-target", "SCRIPTING"):
        assert script_agent._plan_key("same claims", 900) != script_agent._plan_key("same claims", 3000)


def test_run_it_again_does_not_hand_back_the_script_that_was_just_rejected(monkeypatch, tmp_path):
    """The gate's "run it again" is a request for a different script.

    Chapters are checkpointed because a long script is expensive to write,
    and that saving is right for a stage being retried after a failure. It
    is exactly wrong for somebody who has read the script and asked for
    another one.
    """
    import runlog

    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))

    writer = _Writer(600, outline=OUTLINE)
    with runlog.bind("run-regenerate", "SCRIPTING"):
        _run(monkeypatch, writer, target_length_minutes=12)
        after_first = len(writer.prompts)
        _run(monkeypatch, writer, target_length_minutes=12)

    assert len(writer.prompts) > after_first, "the rejected script was handed straight back"


def test_a_stage_that_failed_partway_still_gets_its_saved_chapters_back(monkeypatch, tmp_path):
    """A retry after a failure has not finished a script, so nothing changed
    about what was asked - and re-outlining would spend the allowance twice."""
    import runlog

    monkeypatch.setenv("SANTA_STUDIO_HOME", str(tmp_path))

    boom = _Writer(600, outline=OUTLINE)
    calls = {"n": 0}
    original = boom.__call__

    def fail_on_the_last_chapter(provider, prompt, system, list_key=None):
        calls["n"] += 1
        if calls["n"] == 1 + len(OUTLINE):
            raise RuntimeError("the provider gave out")
        return original(provider, prompt, system, list_key=list_key)

    with runlog.bind("run-retry", "SCRIPTING"):
        failed = _run(monkeypatch, fail_on_the_last_chapter, target_length_minutes=12)
        assert failed["success"] is False

        retry = _Writer(600, outline=OUTLINE)
        _run(monkeypatch, retry, target_length_minutes=12)

    # The outline and the chapters written before the failure came back from
    # disk; only the one that never finished was asked for again.
    assert len(retry.prompts) == 1
