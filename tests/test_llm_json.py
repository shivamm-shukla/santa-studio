"""Getting the answer out of an LLM reply, without quietly losing most of it.

The helper every agent parses through used to scan for the first `{` in the
reply and return whatever object it found. When a model answered a request for
{"scenes": [...]} with the bare array instead - which they do regularly - that
scan found the array's *first scene* and handed it back as the whole script.
Eight scenes vanished and nothing anywhere said so.
"""

import pytest

from agents._llm_utils import call_llm_json


class _Provider:
    def __init__(self, text):
        self.text = text

    def complete(self, prompt, system=None):
        return {"text": self.text, "raw": {}}


def _call(text, **kwargs):
    return call_llm_json(_Provider(text), "prompt", "system", **kwargs)


SCENES = '[{"text": "one"}, {"text": "two"}, {"text": "three"}]'


# ---- the object the prompt asked for ---------------------------------------


def test_a_plain_object_comes_back_as_it_is():
    assert _call('{"scenes": [{"text": "one"}]}') == {"scenes": [{"text": "one"}]}


def test_an_object_in_a_code_fence_is_unwrapped():
    assert _call('```json\n{"a": 1}\n```') == {"a": 1}


def test_an_object_after_conversational_padding_is_found():
    assert _call('Sure! Here is the script:\n{"a": 1}\nHope that helps.') == {"a": 1}


# ---- the array the model sent instead --------------------------------------


def test_a_bare_array_becomes_the_list_the_caller_named():
    assert _call(SCENES, list_key="scenes") == {"scenes": [
        {"text": "one"}, {"text": "two"}, {"text": "three"},
    ]}


def test_an_array_in_a_code_fence_is_also_unwrapped():
    assert len(_call(f'```json\n{SCENES}\n```', list_key="scenes")["scenes"]) == 3


def test_an_array_after_conversational_padding_is_found():
    reply = f"Here you go:\n{SCENES}\nLet me know if you want more."

    assert len(_call(reply, list_key="scenes")["scenes"]) == 3


def test_the_whole_array_survives_and_not_just_its_first_item():
    """The bug this file exists for: eight of nine scenes silently dropped."""
    result = _call(SCENES, list_key="scenes")

    assert result["scenes"] != [{"text": "one"}]
    assert [scene["text"] for scene in result["scenes"]] == ["one", "two", "three"]


def test_a_caller_that_cannot_use_a_list_is_told_rather_than_guessed_at():
    with pytest.raises(ValueError, match="top-level array"):
        _call(SCENES)


# ---- nothing usable --------------------------------------------------------


def test_a_reply_with_no_json_at_all_raises():
    with pytest.raises(ValueError, match="No valid JSON"):
        _call("I am afraid I cannot do that.")


def test_an_empty_array_is_passed_on_for_the_caller_to_judge():
    """Parsing and validating are different jobs. An empty list is a parse
    that worked, and script_agent already refuses a script with no scenes -
    with a better message than this helper could write."""
    assert _call("[]", list_key="scenes") == {"scenes": []}
