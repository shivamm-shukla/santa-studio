"""The overlay layer: what gets drawn on top, and when.

Timeline.overlays existed, the renderer knew how to draw four kinds of
overlay, and GraphicsStyle.density was filled in by reference analysis -
but timeline_builder set `overlays = []` and nothing ever wrote to it, so
every video shipped with the layer empty.

These tests assert the two things that make the layer worth having: the
callouts land on the word being spoken, and the profile's density budget is
respected in both directions.
"""

import pytest

import graphics
import style_profile as sp
from timeline import Overlay


def _words(pairs):
    """[(word, start)] -> word_timestamps, half a second each."""
    return [{"word": w, "start": float(t), "end": float(t) + 0.5} for w, t in pairs]


SPOKEN = _words([
    ("Aaj", 0.0), ("hum", 0.6), ("baat", 1.2), ("karenge", 1.8),
    ("Lord", 12.0), ("Rayleigh", 12.6), ("ne", 13.2), ("1871", 20.0),
    ("mein", 20.6), ("yeh", 21.2), ("prove", 21.8), ("kiya.", 22.4),
    ("Nitrogen", 30.0), ("aur", 30.6), ("oxygen", 31.2), ("molecules", 31.8),
    ("78%", 40.0), ("hissa", 40.6), ("hai.", 41.2),
])


# ---------------------------------------------------------------------------
# Placement
# ---------------------------------------------------------------------------


def test_a_callout_appears_on_the_word_it_labels():
    """This is the whole point of the layer, and why alignment had to be
    fixed first: against evenly-spread estimates these land in roughly the
    right minute rather than on the beat."""
    overlays = graphics.build_overlays(SPOKEN, 60.0, sp.load("documentary"))

    by_text = {o.text: o for o in overlays}
    assert "1871" in by_text
    assert by_text["1871"].start == pytest.approx(20.0, abs=0.01)
    assert by_text["78%"].start == pytest.approx(40.0, abs=0.01)


def test_consecutive_names_become_one_callout():
    overlays = graphics.build_overlays(SPOKEN, 60.0, sp.load("documentary"))
    assert any(o.text == "Lord Rayleigh" for o in overlays)
    assert not any(o.text == "Lord" for o in overlays)


def test_quantities_render_as_counters_and_names_as_text():
    overlays = graphics.build_overlays(SPOKEN, 60.0, sp.load("documentary"))
    kinds = {o.text: o.kind for o in overlays}
    assert kinds.get("78%") == "counter"
    assert kinds.get("1871") == "counter"
    assert kinds.get("Lord Rayleigh") == "text"


def test_sentence_openers_are_not_mistaken_for_names():
    """'Aaj hum baat karenge' opens a sentence; capitalisation there is
    grammar, not emphasis."""
    overlays = graphics.build_overlays(SPOKEN, 60.0, sp.load("documentary"))
    assert not any(o.text.startswith("Aaj") for o in overlays)


def test_callouts_never_bunch_up():
    dense = _words([(f"Name{i}", i * 0.4) for i in range(60)])
    overlays = [o for o in graphics.build_overlays(dense, 60.0, sp.load("documentary"))
                if o.kind != "lower_third"]

    starts = sorted(o.start for o in overlays)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert all(g >= graphics.MIN_GAP_SECONDS - 0.01 for g in gaps), gaps


def test_callouts_sit_clear_of_the_caption_band():
    """Captions own the bottom of the frame; two stacked text layers are
    unreadable."""
    profile = sp.load("documentary")
    overlays = graphics.build_overlays(SPOKEN, 60.0, profile, topic="Why the sky is blue")

    for overlay in overlays:
        if overlay.kind == "lower_third":
            continue
        assert overlay.position[1] < profile.captions.position - 0.1


# ---------------------------------------------------------------------------
# Density budget
# ---------------------------------------------------------------------------


def test_density_is_a_budget_in_overlays_per_minute():
    profile = sp.load("documentary")
    profile.graphics.density = 6.0

    overlays = [o for o in graphics.build_overlays(SPOKEN, 120.0, profile)
                if o.kind not in ("lower_third",)]

    # 6/min over two minutes, minus the citation card which is not a callout.
    assert len(overlays) <= 12 + 1


def test_zero_density_draws_nothing_but_the_topic_card():
    profile = sp.load("documentary")
    profile.graphics.density = 0.0

    overlays = graphics.build_overlays(SPOKEN, 60.0, profile, topic="A topic")

    assert all(o.kind == "lower_third" for o in overlays)


def test_a_denser_profile_draws_more():
    calm = sp.load("documentary")
    calm.graphics.density = 2.0
    busy = sp.load("documentary")
    busy.graphics.density = 12.0

    few = graphics.build_overlays(SPOKEN, 60.0, calm)
    many = graphics.build_overlays(SPOKEN, 60.0, busy)

    assert len(many) > len(few)


# ---------------------------------------------------------------------------
# Never break the timeline
# ---------------------------------------------------------------------------


def test_every_overlay_produced_passes_the_schema():
    """clips/editor once emitted kind='color' and kind='zoom', neither of
    which the validator accepts - overlays that cannot go in a Timeline are
    worse than none."""
    for name in sp.PRESETS:
        overlays = graphics.build_overlays(
            SPOKEN, 60.0, sp.load(name),
            topic="Why the sky is blue",
            sources=["https://en.wikipedia.org/wiki/Rayleigh_scattering"],
        )
        for index, overlay in enumerate(overlays):
            assert overlay.problems(index) == []
            assert overlay.kind in Overlay.KINDS


def test_nothing_is_drawn_past_the_end_of_the_video():
    overlays = graphics.build_overlays(SPOKEN, 42.0, sp.load("documentary"),
                                       topic="A topic")
    for overlay in overlays:
        assert overlay.end <= 42.0 + 0.01


def test_no_aligned_words_means_no_callouts_not_a_crash():
    overlays = graphics.build_overlays([], 60.0, sp.load("documentary"), topic="A topic")
    assert all(o.kind == "lower_third" for o in overlays)


def test_a_profile_without_graphics_is_handled():
    class Bare:
        graphics = None

    assert graphics.build_overlays(SPOKEN, 60.0, Bare()) == []


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sources", [
    ["https://en.wikipedia.org/wiki/Sky"],
    [{"url": "https://en.wikipedia.org/wiki/Sky"}],
])
def test_citation_card_reads_whatever_shape_research_produced(sources):
    overlays = graphics.build_overlays(SPOKEN, 60.0, sp.load("documentary"),
                                       sources=sources)
    assert any("en.wikipedia.org" in o.text for o in overlays)


def test_unparseable_sources_produce_no_card():
    overlays = graphics.build_overlays(SPOKEN, 60.0, sp.load("documentary"),
                                       sources=["not a url", {"nope": 1}])
    assert not any(o.text.startswith("Sources:") for o in overlays)


# ---------------------------------------------------------------------------
# Which counters count
# ---------------------------------------------------------------------------

def test_a_quantity_is_marked_to_count_up_from_nothing():
    words = [{"word": "45,000", "start": 1.0, "end": 1.4}]
    candidates = graphics._candidates(words)

    assert candidates and candidates[0]["kind"] == "counter"
    assert candidates[0]["countable"] is True


def test_a_year_is_a_counter_that_does_not_count():
    """Counting to 1902 from zero spins through four millennia to land on a
    date, which reads as a broken effect rather than as emphasis."""
    words = [{"word": "1902", "start": 1.0, "end": 1.4}]
    candidates = graphics._candidates(words)

    assert candidates and candidates[0]["kind"] == "counter"
    assert candidates[0]["countable"] is False
