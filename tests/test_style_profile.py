"""Style profiles: the knobs, and the promise that changing them changes output."""

import random

import pytest

import style_profile as sp


def test_every_preset_loads():
    for name in sp.PRESETS:
        assert sp.load(name).name == name


def test_the_default_preset_exists():
    assert sp.DEFAULT_PRESET in sp.PRESETS
    assert sp.load().name == sp.DEFAULT_PRESET


def test_presets_are_actually_different_from_each_other():
    # A profile that does not visibly change the output is not worth having.
    rhythms = {name: sp.load(name).cut.cuts_per_minute for name in sp.PRESETS}
    assert len(set(rhythms.values())) == len(rhythms), rhythms
    densities = {name: sp.load(name).graphics.density for name in sp.PRESETS}
    assert len(set(densities.values())) == len(densities), densities


def test_the_fast_profile_really_does_cut_faster():
    assert sp.load("fast-explainer").cut.cuts_per_minute > sp.load("documentary").cut.cuts_per_minute
    assert sp.load("documentary").cut.cuts_per_minute > sp.load("calm-narrative").cut.cuts_per_minute


def test_ducking_is_always_below_the_resting_bed():
    for name in sp.PRESETS:
        music = sp.load(name).music
        assert music.duck_db < music.bed_db, f"{name} ducks upward"
        assert music.swell_db > music.bed_db, f"{name} swells downward"


# --------------------------------------------------------------------------
# Shot lengths
# --------------------------------------------------------------------------

@pytest.mark.parametrize("total", [1.0, 2.4, 5.0, 17.3, 60.0, 900.0])
@pytest.mark.parametrize("preset", list(sp.PRESETS))
def test_shot_lengths_fill_their_scene_exactly(preset, total):
    # A scene's shots must tile it precisely; a rounding drift becomes a black
    # gap or a dropped shot once the timeline is validated.
    lengths = sp.load(preset).cut.shot_lengths(total, random.Random(0))
    assert sum(lengths) == pytest.approx(total)
    assert all(length > 0 for length in lengths)


def test_a_scene_shorter_than_one_shot_stays_a_single_shot():
    profile = sp.load("calm-narrative")
    assert len(profile.cut.shot_lengths(1.0, random.Random(0))) == 1


def test_no_shot_is_left_too_short_to_read():
    rhythm = sp.load("documentary").cut
    lengths = rhythm.shot_lengths(31.7, random.Random(1))
    # The last shot absorbs the remainder rather than leaving a stub, so only
    # the single-shot case may fall under the minimum.
    assert min(lengths) >= rhythm.min_seconds or len(lengths) == 1


def test_a_faster_profile_produces_more_shots_for_the_same_scene():
    fast = sp.load("fast-explainer").cut.shot_lengths(60.0, random.Random(2))
    calm = sp.load("calm-narrative").cut.shot_lengths(60.0, random.Random(2))
    assert len(fast) > len(calm)


def test_variance_zero_is_metronomic():
    rhythm = sp.CutRhythm(target_seconds=4, min_seconds=2, max_seconds=8, variance=0.0)
    lengths = rhythm.shot_lengths(40.0, random.Random(0))
    assert len(set(round(length, 6) for length in lengths)) == 1


# --------------------------------------------------------------------------
# Transitions
# --------------------------------------------------------------------------

def test_transition_picks_follow_their_weights():
    style = sp.TransitionStyle(weights={"cut": 0.9, "crossfade": 0.1})
    rng = random.Random(4)
    picks = [style.pick(rng) for _ in range(1000)]
    assert picks.count("cut") > picks.count("crossfade") * 4


def test_a_cut_has_no_duration_but_a_crossfade_does():
    style = sp.TransitionStyle()
    assert style.duration_for("cut") == 0.0
    assert style.duration_for("crossfade") > 0
    assert style.duration_for("whip") > 0


# --------------------------------------------------------------------------
# Library
# --------------------------------------------------------------------------

def test_a_profile_round_trips_through_the_library(studio_home):
    profile = sp.load("fast-explainer")
    profile.name = "my-channel"
    profile.source = "analyzed:example"
    profile.save()

    loaded = sp.StyleProfile.load("my-channel")
    assert loaded.to_dict() == profile.to_dict()
    assert isinstance(loaded.music.mood_arc, tuple)
    assert isinstance(loaded.cut, sp.CutRhythm)


def test_saved_profiles_appear_alongside_the_presets(studio_home):
    profile = sp.load("documentary")
    profile.name = "learned-from-a-channel"
    profile.description = "measured off reference videos"
    profile.save()
    available = sp.list_available()
    assert "learned-from-a-channel" in available
    assert set(sp.PRESETS) <= set(available)


def test_an_unknown_profile_name_says_what_is_available(studio_home):
    with pytest.raises(ValueError) as caught:
        sp.StyleProfile.load("no-such-profile")
    assert "documentary" in str(caught.value)


def test_a_profile_written_by_a_later_build_still_loads(studio_home):
    import json

    payload = sp.load("documentary").to_dict()
    payload["a_field_added_later"] = True
    payload["cut"]["also_new"] = 1
    path = studio_home / "library" / "styles" / "future.json"
    path.write_text(json.dumps(payload))

    loaded = sp.StyleProfile.load("future")
    assert loaded.cut.target_seconds == 4.0
