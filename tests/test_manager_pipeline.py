"""End-to-end tests for the orchestrator itself.

Every other test in this suite hands a module a correctly-shaped input and
checks what comes back. That leaves the seam where most of the real bugs
live unguarded: whether the manager actually *builds* that correctly-shaped
input from the state it is holding.

It did not, for one state. VIDEO_ASSEMBLY was handed `script_text` but no
`scenes`, so the assembler fell back to treating the whole script as a
single scene - throwing away the per-scene timings and every downloaded
asset that was not tagged scene_index 0. Every unit test still passed,
because each one called the assembler directly with a scene list the
manager never sent.

So these tests drive PipelineManager with stub agents that record what they
were given. They are fast (no LLM, no network, no render) and they assert
the contract between the state machine and the agents rather than the
behaviour of any one agent.
"""

import pytest

import manager
from manager import PipelineHalted, PipelineManager
from state import PipelineState


class StubAgent:
    """Records every input it is handed and returns a canned output."""

    def __init__(self, output):
        self.output = output
        self.calls = []

    def run(self, input_data, config):
        self.calls.append(input_data)
        return {"success": True, "output": dict(self.output), "error": None}

    @property
    def last_input(self):
        return self.calls[-1]


SCENES = [
    {"timestamp_estimate": "0:00-0:10", "text": "Hook line here.", "visual_hint": "blue sky"},
    {"timestamp_estimate": "0:10-0:25", "text": "The explanation part.", "visual_hint": "prism"},
    {"timestamp_estimate": "0:25-0:40", "text": "And the payoff.", "visual_hint": "sunset"},
]

SCRIPT = {
    "script_text": "Hook line here.\nThe explanation part.\nAnd the payoff.",
    "scenes": SCENES,
}

SCENE_ASSETS = [
    {"scene_index": 0, "asset_type": "video", "asset_path": "/tmp/a.mp4"},
    {"scene_index": 1, "asset_type": "video", "asset_path": "/tmp/b.mp4"},
    {"scene_index": 2, "asset_type": "image", "asset_path": "/tmp/c.jpg"},
]


@pytest.fixture
def stubs(tmp_path, monkeypatch):
    """Replaces every agent with a stub, and points voice output at a real file."""
    voice_file = tmp_path / "narration.wav"
    voice_file.write_bytes(b"RIFF0000WAVE")  # only has to exist; nothing reads it

    agents = {
        "TOPIC_SELECTION": StubAgent({"topics": ["Why the sky is blue"]}),
        "REFERENCE_ANALYSIS": StubAgent(
            {"style_notes": "s", "structure_notes": "t", "angle_notes": "a"}
        ),
        "RESEARCHING": StubAgent({"research_summary": "summary", "sources": ["http://x"]}),
        "FACT_CHECKING": StubAgent({"verified_claims": ["c"], "flagged_claims": []}),
        "SCRIPTING": StubAgent(SCRIPT),
        "VOICE_GENERATION": StubAgent(
            {
                "audio_path": str(voice_file),
                "word_timestamps": [{"word": "Hook", "start": 0.0, "end": 0.4}],
            }
        ),
        "VISUAL_SELECTION": StubAgent({"scene_assets": SCENE_ASSETS}),
        "VIDEO_ASSEMBLY": StubAgent(
            {"video_path": str(tmp_path / "master.mp4"), "timeline_path": str(tmp_path / "t.json")}
        ),
        "SHORTS_EXTRACTION": StubAgent({"short_path": str(tmp_path / "short.mp4")}),
        "THUMBNAIL": StubAgent(
            {"thumbnails": [{"variant": "bottom-bar", "path": "/tmp/t.jpg", "text": "T"}]}
        ),
        "YOUTUBE_PUBLISH": StubAgent(
            {"video_url": "https://youtu.be/x", "video_id": "x", "published": True}
        ),
    }
    monkeypatch.setattr(manager, "AGENT_FOR_STATE", agents)
    return agents


def _manager(tmp_path, stubs, shorts=True, **config_overrides):
    config = {"ACTIVE_PROVIDERS": {"publish": None}, "REVIEW_MODE": "autonomous"}
    config.update(config_overrides)
    # Shorts are opt-in now - the cutting bench makes them from any finished
    # run - so a test that wants to see the shorts stage has to ask for them
    # the way the brief does.
    state = PipelineState(
        niche="science",
        user_topic="Why the sky is blue",
        preferences={"shorts": True} if shorts else {},
    )
    return PipelineManager(state, config, approval_handler=None, runs_dir=str(tmp_path / "runs"))


def _drive(mgr, max_steps=40):
    """Steps to completion, approving every gate."""
    seen = []
    for _ in range(max_steps):
        result = mgr.step()
        if result["type"] == "done":
            return seen
        if result["type"] == "awaiting_approval":
            seen.append(result["checkpoint"])
            mgr.step(decision="approve")
        else:
            seen.append(result["state"])
    raise AssertionError("pipeline did not reach DONE")


# ---------------------------------------------------------------------------
# The regression this file exists for
# ---------------------------------------------------------------------------


def test_assembler_receives_the_scripts_scenes(tmp_path, stubs):
    """The assembler needs the scene list, not just the flattened script text.

    Without it the Timeline is built from one synthetic scene: every asset
    beyond the first scene's is dropped and the script's own timings are
    ignored, which is the difference between a cut video and a two-shot
    slideshow.
    """
    mgr = _manager(tmp_path, stubs)
    _drive(mgr)

    handed_over = stubs["VIDEO_ASSEMBLY"].last_input
    assert handed_over["scenes"] == SCENES
    assert handed_over["script"]["scenes"] == SCENES
    assert handed_over["scene_assets"] == SCENE_ASSETS
    assert handed_over["topic"] == "Why the sky is blue"


def test_assembler_input_survives_a_normalize_round_trip(tmp_path, stubs):
    """What the manager sends must be what the assembler knows how to read.

    The two halves of this contract live in different files, so assert them
    against each other rather than trusting that they still agree.
    """
    from agents.assembler_agent import _normalize_state

    mgr = _manager(tmp_path, stubs)
    _drive(mgr)

    normalized = _normalize_state(stubs["VIDEO_ASSEMBLY"].last_input)
    assert len(normalized["script"]["scenes"]) == len(SCENES)
    assert normalized["visual_output"]["scene_assets"] == SCENE_ASSETS
    assert normalized["voice_output"]["audio_path"]


# ---------------------------------------------------------------------------
# Every other state's contract, asserted the same way
# ---------------------------------------------------------------------------


def test_every_agent_gets_the_keys_it_reads(tmp_path, stubs):
    mgr = _manager(tmp_path, stubs)
    _drive(mgr)

    expected = {
        "TOPIC_SELECTION": ("niche", "preferences", "user_topic"),
        "RESEARCHING": ("topic",),
        "FACT_CHECKING": ("research_summary", "sources"),
        "SCRIPTING": ("topic", "research_summary", "verified_claims", "target_length_minutes"),
        "VOICE_GENERATION": ("script_text", "voice_profile_id"),
        "VISUAL_SELECTION": ("scenes",),
        "VIDEO_ASSEMBLY": ("audio_path", "scene_assets", "scenes", "script", "run_id"),
        "SHORTS_EXTRACTION": ("video_path", "script", "run_id"),
        "THUMBNAIL": ("topic", "scenes", "run_id"),
    }
    for state, keys in expected.items():
        given = stubs[state].last_input
        missing = [k for k in keys if k not in given]
        assert not missing, f"{state} was not given {missing}"


def test_visual_and_assembly_agree_on_scene_indices(tmp_path, stubs):
    """Assets are matched to scenes by index, so both stages must see the
    same list in the same order."""
    mgr = _manager(tmp_path, stubs)
    _drive(mgr)

    visual_scenes = stubs["VISUAL_SELECTION"].last_input["scenes"]
    assembly_scenes = stubs["VIDEO_ASSEMBLY"].last_input["scenes"]
    assert visual_scenes == assembly_scenes
    highest_index = max(a["scene_index"] for a in SCENE_ASSETS)
    assert highest_index < len(assembly_scenes)


# ---------------------------------------------------------------------------
# State machine behaviour
# ---------------------------------------------------------------------------


def test_run_without_publish_provider_ends_at_done(tmp_path, stubs):
    mgr = _manager(tmp_path, stubs)
    seen = _drive(mgr)

    assert "AWAITING_APPROVAL" in seen
    assert "AWAITING_PUBLISH" not in seen
    assert mgr.state.current_state == "DONE"
    assert not stubs["YOUTUBE_PUBLISH"].calls


def test_run_with_publish_provider_reaches_the_upload(tmp_path, stubs):
    mgr = _manager(tmp_path, stubs, ACTIVE_PROVIDERS={"publish": "youtube"})
    seen = _drive(mgr)

    assert "AWAITING_PUBLISH" in seen
    assert stubs["YOUTUBE_PUBLISH"].calls
    assert mgr.state.publish_output["video_url"] == "https://youtu.be/x"
    # The gate's metadata is what ships.
    assert "video_path" in stubs["YOUTUBE_PUBLISH"].last_input


def test_checkpoints_mode_pauses_after_research_and_script(tmp_path, stubs):
    mgr = _manager(tmp_path, stubs, REVIEW_MODE="checkpoints")
    seen = _drive(mgr)

    assert "RESEARCHING" in seen and "SCRIPTING" in seen
    assert mgr.state.current_state == "DONE"


def test_blocking_run_matches_step_for_step(tmp_path, stubs):
    """run() and step() are two drivers over one state machine; a video made
    from the CLI must be the same video the web app makes."""

    class AlwaysApprove:
        def request_approval(self, checkpoint, payload):
            return "approve"

        def request_edit(self, checkpoint, payload):
            return payload

        def notify(self, message):
            pass

    config = {"ACTIVE_PROVIDERS": {"publish": None}, "REVIEW_MODE": "autonomous"}
    state = PipelineState(niche="science", user_topic="Why the sky is blue")
    mgr = PipelineManager(state, config, AlwaysApprove(), runs_dir=str(tmp_path / "runs"))
    final = mgr.run()

    assert final.current_state == "DONE"
    assert stubs["VIDEO_ASSEMBLY"].last_input["scenes"] == SCENES


def test_state_persists_after_every_transition(tmp_path, stubs):
    from state import load_state

    mgr = _manager(tmp_path, stubs)
    _drive(mgr)

    reloaded = load_state(mgr._state_path())
    assert reloaded.current_state == "DONE"
    assert reloaded.script["scenes"] == SCENES
    assert reloaded.run_id == mgr.state.run_id


def test_a_failing_agent_halts_with_the_state_saved(tmp_path, stubs):
    class Failing:
        def run(self, input_data, config):
            return {"success": False, "output": None, "error": "boom"}

    stubs["SCRIPTING"] = Failing()
    mgr = _manager(tmp_path, stubs)

    with pytest.raises(PipelineHalted, match="boom"):
        for _ in range(20):
            mgr.step()

    from state import load_state

    assert load_state(mgr._state_path()).current_state == "SCRIPTING"
