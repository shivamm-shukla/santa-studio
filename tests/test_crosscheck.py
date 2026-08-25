"""Where the sources disagree, and why that must not be resolved silently.

Fact-checking flattened every source's key facts into one list before judging
them, which threw away the only thing a cross-check needs: who said what. Two
sources giving different figures for the same quantity arrived as two claims in
a heap, and the model was free to verify both, pick one, or split the
difference. On a contested subject the disagreement is the story.
"""

import crosscheck


def _figure(metric, value, source="a source"):
    return {"metric": metric, "value": value, "source": source}


# ---- figures that do not match ---------------------------------------------


def test_two_figures_for_one_quantity_are_a_disagreement():
    conflicts = crosscheck.conflicting_figures([
        _figure("Total gold extracted", "≈ 45 metric tonnes", "Wikipedia"),
        _figure("Total gold extracted", "60 tonnes", "OpenAlex"),
    ])

    assert len(conflicts) == 1
    assert conflicts[0]["values"] == ["≈ 45 metric tonnes", "60 tonnes"]
    assert conflicts[0]["sources"] == ["Wikipedia", "OpenAlex"]


def test_rounding_is_not_a_disagreement():
    """2,500 against 2,550 is one source being approximate, not a dispute."""
    assert crosscheck.conflicting_figures([
        _figure("Peak annual production", "≈ 2,500 kg"),
        _figure("Peak annual production", "2,550 kg"),
    ]) == []


def test_the_same_quantity_described_at_different_lengths_still_matches():
    """Research writes one name in one place and a longer one in another;
    requiring the exact same words found no conflicts at all."""
    conflicts = crosscheck.conflicting_figures([
        _figure("Total gold extracted", "45 tonnes"),
        _figure("Total gold extracted over the life of the mine", "60 tonnes"),
    ])

    assert len(conflicts) == 1


def test_word_order_does_not_hide_a_disagreement():
    conflicts = crosscheck.conflicting_figures([
        _figure("Peak annual production", "2,500 kg"),
        _figure("Annual peak production", "4,000 kg"),
    ])

    assert len(conflicts) == 1


def test_different_quantities_are_not_compared():
    assert crosscheck.conflicting_figures([
        _figure("Total gold extracted", "45 tonnes"),
        _figure("Depth of the deepest shaft", "3,200 m"),
    ]) == []


def test_the_same_amount_in_another_unit_is_not_a_disagreement():
    """Tonnes against troy ounces is one quantity in two languages, and this
    has no business converting between them and guessing wrong."""
    assert crosscheck.conflicting_figures([
        _figure("Total gold extracted", "45 tonnes"),
        _figure("Total gold extracted", "1,450,000 troy ounces"),
    ]) == []


def test_one_word_metrics_do_not_match_everything():
    assert crosscheck.conflicting_figures([
        _figure("Depth", "3,200 m"),
        _figure("Length", "115 m"),
    ]) == []


def test_a_disagreement_is_only_reported_once():
    conflicts = crosscheck.conflicting_figures([
        _figure("Total gold extracted", "45 tonnes", "A"),
        _figure("Total gold extracted", "60 tonnes", "B"),
        _figure("Total gold extracted", "45 tonnes", "C"),
    ])

    assert len(conflicts) == 1


def test_values_with_no_number_are_skipped():
    assert crosscheck.conflicting_figures([
        _figure("Total gold extracted", "a great deal"),
        _figure("Total gold extracted", "rather less"),
    ]) == []


def test_nothing_at_all_is_handled():
    assert crosscheck.conflicting_figures([]) == []
    assert crosscheck.conflicting_figures(None) == []
    assert crosscheck.conflicting_figures(["not a dict"]) == []


# ---- keeping the attribution -----------------------------------------------


def test_a_claim_carries_the_source_that_made_it():
    claims = crosscheck.attributed_claims([
        {"title": "Wikipedia", "key_facts": ["The mine closed in 2001."]},
        {"title": "OpenAlex", "key_facts": ["Cyanide persisted in the tailings."]},
    ])

    assert claims == [
        {"claim": "The mine closed in 2001.", "source": "Wikipedia"},
        {"claim": "Cyanide persisted in the tailings.", "source": "OpenAlex"},
    ]


def test_a_source_with_no_title_is_named_by_its_url():
    claims = crosscheck.attributed_claims([
        {"url": "https://doi.org/10.1/2", "key_facts": ["A finding."]},
    ])

    assert claims[0]["source"] == "https://doi.org/10.1/2"


def test_empty_facts_are_not_claims():
    assert crosscheck.attributed_claims([{"title": "A", "key_facts": ["", "   "]}]) == []
    assert crosscheck.attributed_claims([]) == []


# ---- what the fact-checker is told ------------------------------------------


def test_the_prompt_says_not_to_resolve_the_disagreement():
    text = crosscheck.describe([
        {"subject": "Total gold extracted", "values": ["45 tonnes", "60 tonnes"],
         "sources": ["Wikipedia", "OpenAlex"]},
    ])

    assert "disputed" in text
    assert "averaging" in text
    assert "45 tonnes vs 60 tonnes" in text


def test_no_conflicts_adds_nothing_to_the_prompt():
    assert crosscheck.describe([]) == ""
