"""Charts built from the figures research returned, and the ones it refuses to build.

The visual chain will not generate a chart, because an image model asked for
one invents the numbers - a real run produced a table reading 1905 CIL, 1903
LIL, POLAL about a real company. That refusal left a hole this fills, from the
`numbers_and_data` a run already produces.

The thing these mostly guard is the refusal to plot. A run returns 45 tonnes of
gold, a 3,200 metre shaft, $500 an ounce and 3,000 workers; a chart of those
means nothing while looking authoritative, which is the invented table again
in a tidier font.
"""

import charts


# ---- reading a figure out of the sentence research wrote -------------------

def test_a_plain_figure_and_its_unit():
    assert charts.parse_value("3,200 m (≈ 10,500 ft)") == (3200.0, "m")


def test_only_the_first_figure_is_read():
    """What follows in brackets is the same quantity in another unit."""
    assert charts.parse_value("≈ 2,500 kg (≈ 80,300 troy ounces)") == (2500.0, "kg")


def test_an_adjective_between_the_number_and_the_unit_is_stepped_over():
    assert charts.parse_value("≈ 45 metric tonnes") == (45.0, "tonnes")


def test_a_scale_word_multiplies_rather_than_becoming_the_unit():
    assert charts.parse_value("≈ 0.2 million tonnes of ore") == (200000.0, "tonnes")


def test_a_currency_stays_with_what_it_is_per():
    assert charts.parse_value("$500 USD / oz") == (500.0, "usd/oz")


def test_two_currencies_do_not_share_an_axis():
    dollars = charts.parse_value("$350 USD / oz")
    rupees = charts.parse_value("₹21,000 / oz")

    assert dollars and rupees and dollars[1] != rupees[1]


def test_a_value_with_no_number_in_it_is_not_a_figure():
    assert charts.parse_value("several thousand") is None
    assert charts.parse_value("") is None


# ---- what may be plotted together ------------------------------------------

def _entry(metric, value):
    return {"metric": metric, "value": value}


def test_figures_sharing_a_unit_make_a_chart():
    series = charts.comparable([
        _entry("Extraction cost", "$500 USD / oz"),
        _entry("Gold price", "$350 USD / oz"),
    ])

    assert [row[1] for row in series] == [500.0, 350.0]


def test_figures_in_different_units_do_not():
    assert charts.comparable([
        _entry("Gold extracted", "45 tonnes"),
        _entry("Deepest shaft", "3,200 m"),
        _entry("Employees", "3,000 workers"),
    ]) == []


def test_the_same_unit_on_different_things_is_still_refused():
    """45 tonnes of gold against 200,000 tonnes of ore share a word and
    nothing else, and one bar would be a line of pixels."""
    assert charts.comparable([
        _entry("Gold extracted", "45 tonnes"),
        _entry("Ore remaining", "0.2 million tonnes"),
    ]) == []


def test_one_figure_on_its_own_is_not_a_comparison():
    assert charts.comparable([_entry("Extraction cost", "$500 USD / oz")]) == []


def test_nothing_at_all_is_handled():
    assert charts.comparable([]) == []
    assert charts.comparable(None) == []
    assert charts.comparable(["not a dict"]) == []


# ---- the single figure, when nothing is comparable --------------------------

def test_the_headline_is_the_figure_worth_remembering():
    picked = charts.headline([
        _entry("Average grade", "0.5 g / t"),
        _entry("Deepest shaft", "3,200 m"),
    ])

    assert picked["metric"] == "Deepest shaft"


def test_no_figures_means_no_headline():
    assert charts.headline([]) is None


# ---- drawing ---------------------------------------------------------------

def test_a_chart_is_drawn_transparent_so_it_sits_over_the_picture():
    series = [("Extraction cost", 500.0, "usd/oz"), ("Gold price", 350.0, "usd/oz")]
    card = charts.bar_chart(series, "Compared", (960, 540))

    assert card.mode == "RGBA"
    assert card.size == (960, 540)
    assert card.getchannel("A").getextrema()[0] == 0, "the whole frame was painted"


def test_the_bars_grow_with_the_build():
    import numpy as np

    series = [("Extraction cost", 500.0, "usd/oz"), ("Gold price", 350.0, "usd/oz")]
    early = np.asarray(charts.bar_chart(series, "", (960, 540), progress=0.2))
    late = np.asarray(charts.bar_chart(series, "", (960, 540), progress=1.0))

    assert late[:, :, 3].sum() > early[:, :, 3].sum()


def test_the_panel_is_the_height_of_what_is_in_it():
    """Drawn at a fixed height it left two thirds of itself empty under a
    two-bar chart, which reads as a slide someone forgot to finish."""
    import numpy as np

    two = np.asarray(charts.bar_chart(
        [("a", 1.0, "kg"), ("b", 2.0, "kg")], "T", (960, 540)))
    four = np.asarray(charts.bar_chart(
        [("a", 1.0, "kg"), ("b", 2.0, "kg"), ("c", 3.0, "kg"), ("d", 4.0, "kg")], "T", (960, 540)))

    assert four[:, :, 3].sum() > two[:, :, 3].sum()


def test_an_empty_series_draws_nothing_rather_than_an_empty_card():
    card = charts.bar_chart([], "Compared", (960, 540))

    assert card.getchannel("A").getextrema() == (0, 0)
