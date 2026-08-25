"""Work finished inside a stage, kept so a retry does not repeat it.

The manager re-runs a whole agent when its output fails validation. The
research swarm's three parallel calls are three of a free tier's twenty
requests for the day, so spending them twice to re-derive answers already on
disk is how a run ends up parked for want of allowance it had already used.
"""

import checkpoints
import runlog


def _bind(monkeypatch, tmp_path, run_id="run-1"):
    """A bound run whose project lives under tmp_path."""
    import paths

    monkeypatch.setattr(runlog, "current", lambda: (run_id, "RESEARCHING"))
    monkeypatch.setattr(
        paths, "project_dir",
        lambda rid, topic="", create=True: tmp_path / rid,
    )
    (tmp_path / run_id).mkdir(parents=True, exist_ok=True)


def test_what_was_saved_comes_back(monkeypatch, tmp_path):
    _bind(monkeypatch, tmp_path)

    checkpoints.save("numbers", {"metrics": [{"value": "45 tonnes"}]})

    assert checkpoints.load("numbers") == {"metrics": [{"value": "45 tonnes"}]}


def test_a_key_that_was_never_saved_is_none(monkeypatch, tmp_path):
    _bind(monkeypatch, tmp_path)

    assert checkpoints.load("never written") is None


def test_two_runs_do_not_share_anything(monkeypatch, tmp_path):
    """A checkpoint is not a cache; a different run is a different question."""
    _bind(monkeypatch, tmp_path, "run-a")
    checkpoints.save("numbers", ["a"])

    _bind(monkeypatch, tmp_path, "run-b")
    assert checkpoints.load("numbers") is None


def test_nothing_is_written_when_no_run_is_bound(monkeypatch, tmp_path):
    """A script or a test would otherwise write into somebody's project."""
    monkeypatch.setattr(runlog, "current", lambda: None)

    checkpoints.save("numbers", ["a"])

    assert checkpoints.load("numbers") is None
    assert not list(tmp_path.rglob(checkpoints.DIRECTORY))


def test_clearing_throws_the_run_s_work_away(monkeypatch, tmp_path):
    _bind(monkeypatch, tmp_path)
    checkpoints.save("numbers", ["a"])

    checkpoints.clear()

    assert checkpoints.load("numbers") is None


def test_a_key_cannot_escape_the_checkpoint_directory(monkeypatch, tmp_path):
    _bind(monkeypatch, tmp_path)

    checkpoints.save("../../escaped", ["a"])

    assert checkpoints.load("../../escaped") == ["a"]
    assert not (tmp_path / "escaped.json").exists()


def test_an_unwritable_directory_is_a_missed_saving_not_a_failure(monkeypatch, tmp_path):
    """Losing a stage over a checkpoint would be the wrong way round."""
    import paths

    monkeypatch.setattr(runlog, "current", lambda: ("run-1", "RESEARCHING"))
    monkeypatch.setattr(paths, "project_dir",
                        lambda rid, topic="", create=True: (_ for _ in ()).throw(OSError("no")))

    checkpoints.save("numbers", ["a"])
    assert checkpoints.load("numbers") is None


# ---- what the research swarm does with it ----------------------------------


def test_a_specialist_that_already_reported_is_not_asked_again(monkeypatch, tmp_path):
    _bind(monkeypatch, tmp_path)
    import agents.research_agent as research

    calls = []

    def once(provider, prompt, system):
        calls.append(prompt)
        return {"metrics": [{"value": "45 tonnes"}]}

    monkeypatch.setattr(research, "call_llm_json", once)

    first = research._run_specialist_research("numbers", "Extract the figures", None)
    second = research._run_specialist_research("numbers", "Extract the figures", None)

    assert first == second
    assert len(calls) == 1, "the day's allowance was spent twice on one specialist"


def test_a_different_question_is_still_asked(monkeypatch, tmp_path):
    _bind(monkeypatch, tmp_path)
    import agents.research_agent as research

    calls = []
    monkeypatch.setattr(research, "call_llm_json",
                        lambda p, prompt, s: (calls.append(prompt), {"metrics": []})[1] or {"a": 1})

    research._run_specialist_research("numbers", "Extract the figures", None)
    research._run_specialist_research("numbers", "Extract the chronology", None)

    assert len(calls) == 2


def test_an_empty_answer_is_not_pinned_in_place(monkeypatch, tmp_path):
    """Saving a failure would make every later attempt reuse it."""
    _bind(monkeypatch, tmp_path)
    import agents.research_agent as research

    attempts = {"n": 0}

    def flaky(provider, prompt, system):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("429")
        return {"metrics": [{"value": "45 tonnes"}]}

    monkeypatch.setattr(research, "call_llm_json", flaky)

    assert research._run_specialist_research("numbers", "Extract the figures", None) == {}
    assert research._run_specialist_research("numbers", "Extract the figures", None) != {}
