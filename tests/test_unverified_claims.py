"""Nothing the fact-checker refused may be narrated.

One finished run made the case for this file on its own. Its fact-checker
verified none of the six claims it was given and flagged all six; the script
then stated all six, because they were also sitting in the research summary
and the figure list, which were handed to the writer regardless. The sourcing
document that shipped beside the video said those claims had been "kept out
of the script".

Three things had to be true for that to happen, so three things are pinned
here: the writer only sees material that survived checking, it refuses rather
than improvising when nothing did, and refusing sends the run back for better
sources instead of ending it.
"""

import manager
from agents import script_agent
from state import PipelineState


class _Refuses:
    """A script agent that fails the way an empty claim list makes it fail."""

    def __init__(self):
        self.calls = 0

    def run(self, input_data, config):
        self.calls += 1
        return {
            "success": False,
            "output": None,
            "error": "Nothing survived fact-checking, so there is nothing to state.",
        }


# ---------------------------------------------------------------------------
# What the writer is given
# ---------------------------------------------------------------------------


def _state_with_a_refused_figure():
    state = PipelineState(niche="history", user_topic="containers")
    state.topic = "how a metal box rewired world trade"
    state.research = {
        "research_summary": "A summary nobody checked.",
        "chronology": [{"date": "1956", "event": "The Ideal-X sails"}],
        "numbers_and_data": [{"metric": "loading cost", "value": "$5.86 per ton"}],
        "disputed_claims": [{"claim": "research's own guess at what is contested"}],
        "sources": [],
    }
    state.factcheck = {
        "verified_claims": ["Containers are standardised at 20 and 40 feet."],
        "flagged_claims": ["The Ideal-X sailed on 26 April 1956 with 58 containers."],
        "disputed_claims": [{"claim": "the one the checker actually found"}],
    }
    return state


def test_the_refused_figures_are_not_handed_to_the_writer_a_second_time():
    """They went through the checker as claims; what survived is in the list.

    Passing the raw chronology and figures across again is how a date the
    checker refused reaches the narration anyway.
    """
    given = manager._build_input(_state_with_a_refused_figure(), "SCRIPTING")

    assert "chronology" not in given
    assert "numbers_and_data" not in given


def test_the_disputes_the_writer_sees_are_the_checked_ones():
    given = manager._build_input(_state_with_a_refused_figure(), "SCRIPTING")

    assert given["disputed_claims"] == [{"claim": "the one the checker actually found"}]


# ---------------------------------------------------------------------------
# What the writer does with nothing
# ---------------------------------------------------------------------------


def test_no_script_is_written_when_nothing_was_verified():
    """Handed an empty list the model writes from the summary instead -
    fluently, and out of exactly the claims the checker had just refused."""
    result = script_agent.run({
        "research_summary": "On 26 April 1956 the Ideal-X sailed with 58 containers.",
        "verified_claims": [],
        "target_length_minutes": 2,
    }, {})

    assert result["success"] is False
    assert "survived fact-checking" in result["error"]


def test_a_figure_no_verified_claim_carries_is_named():
    """The prompt is where the rule lives; this is how we find out it held."""
    loose = script_agent._unsupported(
        "Cost fell to $0.16 per ton by 1968.",
        ["Costs fell to $0.16 per ton."],
    )

    assert loose == ["1968"]


def test_a_figure_the_claims_do_carry_is_not_reported():
    assert script_agent._unsupported(
        "Cost fell to $0.16 per ton.", ["Costs fell to $0.16 per ton."]
    ) == []


# ---------------------------------------------------------------------------
# What the run does about it
# ---------------------------------------------------------------------------


def test_refusing_sends_the_run_back_for_sources_rather_than_ending_it(tmp_path, monkeypatch):
    """The missing thing is sources, so the answer is to go and find sources.

    Re-running the writer against the same empty list would refuse again for
    the same reason and then halt a run whose topic was never the problem.
    """
    refusing = _Refuses()
    monkeypatch.setitem(manager.AGENT_FOR_STATE, "SCRIPTING", refusing)

    state = _state_with_a_refused_figure()
    state.current_state = "SCRIPTING"
    mgr = manager.PipelineManager(
        state,
        {"ACTIVE_PROVIDERS": {"publish": None}, "REVIEW_MODE": "autonomous"},
        approval_handler=None,
        runs_dir=str(tmp_path / "runs"),
    )

    result = mgr.step()

    assert result["state"] == "RESEARCHING"
    assert state.research_retries == 1
    # Refusing twice for the same reason is not worth the request it costs.
    assert refusing.calls == 1


def test_a_topic_with_no_sources_behind_it_stops_instead_of_searching_forever(tmp_path, monkeypatch):
    refusing = _Refuses()
    monkeypatch.setitem(manager.AGENT_FOR_STATE, "SCRIPTING", refusing)

    state = _state_with_a_refused_figure()
    state.current_state = "SCRIPTING"
    state.research_retries = manager.MAX_RESEARCH_RETRIES
    mgr = manager.PipelineManager(
        state,
        {"ACTIVE_PROVIDERS": {"publish": None}, "REVIEW_MODE": "autonomous"},
        approval_handler=None,
        runs_dir=str(tmp_path / "runs"),
    )

    try:
        mgr.step()
    except manager.PipelineHalted as halted:
        assert "SCRIPTING" in str(halted)
    else:
        raise AssertionError("a run with nothing to say should not carry on")


# ---------------------------------------------------------------------------
# The second pass has to be a different pass
# ---------------------------------------------------------------------------


def test_research_is_told_which_attempt_it_is_on():
    """Otherwise it spends the same requests to arrive at the same place."""
    state = _state_with_a_refused_figure()
    state.research_retries = 1

    assert manager._build_input(state, "RESEARCHING")["attempt"] == 1


# ---------------------------------------------------------------------------
# When the writer invents a figure anyway
# ---------------------------------------------------------------------------


class _Drafts:
    """Returns each canned draft in turn, recording what it was asked."""

    def __init__(self, *drafts):
        self.drafts = list(drafts)
        self.prompts = []

    def __call__(self, provider, prompt, system, list_key=None):
        self.prompts.append(prompt)
        text = self.drafts[min(len(self.prompts) - 1, len(self.drafts) - 1)]
        return {"scenes": [{"timestamp_estimate": "0:00-0:20", "text": text,
                            "visual_hint": "a port"}]}


CLAIMS = ["The Ideal X carried 58 containers on its 1956 voyage."]


def test_an_invented_figure_sends_the_draft_back_with_the_number_named(monkeypatch):
    """One draft narrated a ship stacking 1000 containers against 10,000
    pallets. Neither number is in any source; both were simply written."""
    drafts = _Drafts(
        "Ek ship ki deck pe 1000 containers stack hote the.",
        "1956 mein Ideal X ne 58 containers leke voyage kiya.",
    )
    monkeypatch.setattr(script_agent, "call_llm_json", drafts)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())

    result = script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "target_length_minutes": 1}, {}
    )

    assert result["success"] is True
    assert "1000" in drafts.prompts[1], "the redraft has to say which figure was invented"
    assert "unsupported_figures" not in result["output"]
    assert "1000" not in result["output"]["script_text"]


def test_a_writer_that_will_not_stop_inventing_ships_but_is_recorded(monkeypatch):
    """The video is worth more than the figures cost, so it goes out - and the
    sourcing document names them rather than letting them pass as sourced."""
    drafts = _Drafts("Ek ship pe 1000 containers the.")
    monkeypatch.setattr(script_agent, "call_llm_json", drafts)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())

    result = script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "target_length_minutes": 1}, {}
    )

    assert result["success"] is True
    assert result["output"]["unsupported_figures"] == ["1000"]
    assert len(drafts.prompts) == script_agent.DRAFTS


def test_a_clean_draft_is_not_written_twice(monkeypatch):
    drafts = _Drafts("1956 mein Ideal X ne 58 containers leke voyage kiya.")
    monkeypatch.setattr(script_agent, "call_llm_json", drafts)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())

    script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "target_length_minutes": 1}, {}
    )

    assert len(drafts.prompts) == 1


# --------------------------------------------------------------------------
# The other reason a draft goes back
# --------------------------------------------------------------------------

PROSE = (
    "The programme was significant because it demonstrated that an agency "
    "operating on a fraction of the budget available to its international "
    "peers could nevertheless achieve an outcome that had eluded far better "
    "funded organisations for several decades. Moreover, the approach taken "
    "departed substantially from the methods that had been established as "
    "standard practice throughout the preceding period. In conclusion, the "
    "achievement was notable for reasons extending well beyond the immediate "
    "scientific return obtained. It should be noted that costs stayed low."
)

SPEECH = (
    "Sochiye. Ek team, aur budget itna kam ki yakeen na ho. Sab maan chuke "
    "the ki yeh possible nahi hai. Phir kya hua? Ideal X chali. 1956 mein, "
    "58 containers ke saath. Aur shipping hamesha ke liye badal gayi."
)


def test_a_draft_that_reads_like_a_book_is_sent_back(monkeypatch):
    """The complaint was that the finished videos sounded read, not spoken.

    A draft can be perfectly sourced and still be unwatchable, so the
    redraft loop checks for both and says which one it is failing.
    """
    drafts = _Drafts(PROSE, SPEECH)
    monkeypatch.setattr(script_agent, "call_llm_json", drafts)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())

    result = script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "target_length_minutes": 1}, {}
    )

    assert result["success"] is True
    assert len(drafts.prompts) == 2
    assert "moreover" in drafts.prompts[1].lower(), "the redraft has to name what was wrong"
    assert "register_notes" not in result["output"]


def test_a_draft_that_is_both_wrong_and_unspeakable_is_told_both(monkeypatch):
    drafts = _Drafts(PROSE + " Ek ship pe 1000 containers the.", SPEECH)
    monkeypatch.setattr(script_agent, "call_llm_json", drafts)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())

    script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "target_length_minutes": 1}, {}
    )

    redraft = drafts.prompts[1]
    assert "1000" in redraft
    assert "read, not said" in redraft


def test_a_writer_that_will_not_stop_writing_prose_still_ships_and_says_so(monkeypatch):
    """A flat narrator is a watchable video, unlike a wrong one - but the
    desk has to say so, because it is obvious in the file and invisible in
    the log."""
    drafts = _Drafts(PROSE)
    monkeypatch.setattr(script_agent, "call_llm_json", drafts)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())

    result = script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "target_length_minutes": 1}, {}
    )

    assert result["success"] is True
    assert result["output"]["register_notes"]
    assert len(drafts.prompts) == script_agent.DRAFTS


def test_a_draft_that_reads_as_speech_is_not_written_twice(monkeypatch):
    drafts = _Drafts(SPEECH)
    monkeypatch.setattr(script_agent, "call_llm_json", drafts)
    monkeypatch.setattr(script_agent, "get_provider", lambda kind, config: object())

    script_agent.run(
        {"verified_claims": CLAIMS, "research_summary": "", "target_length_minutes": 1}, {}
    )

    assert len(drafts.prompts) == 1
