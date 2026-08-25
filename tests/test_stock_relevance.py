"""Whether a stock result is of the thing that was asked for.

A finished two-minute video about a gold mine in Karnataka carried a Binance
trading chart and a Turkish military security zone sign, both cut in as
straight B-roll. Neither was a bug in the search: Pexels reports eight
thousand results for every query, including "chart gold production 1910s Kolar
peak 1919", and the provider took the first one. The strings in these tests
are the real slugs those queries returned.
"""

from providers.visual import matching
from providers.visual import pexels_provider, pixabay_provider


# ---- reading the words -----------------------------------------------------


def test_the_description_hiding_in_a_page_url_is_recovered():
    slug = matching.slug_words(
        "https://www.pexels.com/video/dynamic-cryptocurrency-trading-room-setup-38687555/"
    )

    assert slug == "dynamic cryptocurrency trading room setup"


def test_the_asset_id_on_the_end_of_a_slug_is_not_a_word():
    """Every slug ends in the id, and an id shares no meaning with a year."""
    assert "38687555" not in matching.slug_words(
        "https://www.pexels.com/video/trading-room-38687555/"
    )


def test_a_plural_and_a_gerund_reach_the_same_word_as_the_singular():
    assert matching._stem("mining") == matching._stem("mine")
    assert matching._stem("fields") == matching._stem("field")


def test_words_that_match_everything_are_not_counted():
    assert matching.overlap("stock footage of a mine", "free stock video clip") == 0


# ---- what gets rejected ----------------------------------------------------


def test_a_trading_desk_is_not_a_chart_of_gold_production():
    assert not matching.describes(
        "chart gold production 1910s Kolar peak 1919",
        "dynamic cryptocurrency trading room setup",
    )


def test_signs_on_a_fence_are_not_a_mine_closure_notice():
    assert not matching.describes(
        "official closure notice BGML 2001 Kolar gold fields",
        "signages hanging on wire fence",
    )


def test_a_flag_is_not_a_government_takeover():
    assert not matching.describes(
        "Indian government takeover 1956 BGML office Kolar",
        "indian flag waving against clear blue sky",
    )


# ---- what gets through -----------------------------------------------------


def test_an_aerial_of_a_mine_answers_a_request_for_one():
    assert matching.describes(
        "historical gold mine aerial view Kolar India",
        "aerial view of coal mining operations",
    )


def test_a_proper_noun_nobody_has_footage_of_is_not_required():
    """A hint carries a company acronym, a year and a place name that no stock
    library has heard of. Only the ordinary nouns can ever match."""
    assert matching.describes(
        "deep underground gold mine shaft Gold Hill Kolar depth",
        "underground mine shaft tunnel workers",
    )


# ---- choosing between candidates -------------------------------------------

def _video(slug, tags=None):
    return {"url": f"https://www.pexels.com/video/{slug}-123/", "tags": tags or []}


def test_the_relevant_candidate_is_taken_over_the_libraries_first():
    results = [
        _video("dynamic-cryptocurrency-trading-room-setup"),
        _video("aerial-view-of-coal-mining-operations"),
    ]

    chosen = pexels_provider._most_relevant("historical gold mine aerial view Kolar", results)
    assert chosen is results[1]


def test_the_libraries_own_ranking_breaks_a_tie():
    results = [
        _video("underground-mine-shaft-tunnel"),
        _video("underground-mine-shaft-workers"),
    ]

    chosen = pexels_provider._most_relevant("deep underground mine shaft", results)
    assert chosen is results[0]


def test_nothing_relevant_is_no_result_at_all():
    """Which sends the shot down the chain to generation - the case generation
    was built for: a specific place in a specific decade."""
    results = [_video("dynamic-cryptocurrency-trading-room-setup")]

    assert pexels_provider._most_relevant("chart gold production 1919 Kolar", results) is None


def test_an_empty_search_is_not_a_result():
    assert pexels_provider._most_relevant("anything at all", []) is None


def test_pixabay_checks_its_tags_as_well_as_its_slug():
    hits = [
        {"tags": "bitcoin, trading, screen", "pageURL": "https://pixabay.com/videos/trading-1/"},
        {"tags": "mine, shaft, underground", "pageURL": "https://pixabay.com/videos/mine-2/"},
    ]

    chosen = pixabay_provider._most_relevant("underground gold mine shaft Kolar", hits)
    assert chosen is hits[1]


def test_pixabay_rejects_a_hit_about_something_else():
    hits = [{"tags": "bitcoin, trading, screen", "pageURL": "https://pixabay.com/videos/trading-1/"}]

    assert pixabay_provider._most_relevant("underground gold mine shaft", hits) is None


# ---- when the hint asks for a kind of thing, not a subject ------------------

def test_a_photograph_of_the_place_is_not_a_map_of_it():
    """Commons answers "map of Karnataka India" with a photograph of a water
    tank in Hampi. It shares two words with the query and is not a map."""
    assert not matching.describes(
        "map of Karnataka India",
        "File:Dancing Girls Bath (Hampi water tank), Hampi, Vijayanagara, Karnataka",
    )


def test_a_real_map_is_accepted():
    assert matching.describes("map of Karnataka India", "File:India Karnataka relief map.svg")


def test_the_artefact_word_has_to_appear_not_merely_be_outvoted():
    """Two ordinary nouns in common is enough for a subject and not for a
    kind: the whole point of asking for a map is that it is a map."""
    description = "photograph of a temple in Karnataka, India"

    assert matching.overlap("map of Karnataka India", description) >= matching.MIN_MATCHES
    assert not matching.describes("map of Karnataka India", description)


def test_a_hint_naming_no_kind_of_thing_is_unaffected():
    assert matching.required("historical gold mine aerial view Kolar India") == set()
    assert matching.describes(
        "historical gold mine aerial view Kolar India",
        "aerial view of coal mining operations",
    )


def test_a_chart_hint_will_not_take_a_photograph_either():
    assert not matching.describes(
        "chart of gold production at Kolar",
        "aerial view of coal mining operations",
    )


def test_a_map_that_does_not_say_map_is_missed():
    """A known cost of the rule, written down rather than discovered later.
    Commons carries "146-Kolar Gold Fields constituency.svg", which is a map
    and does not say so; its categories come back empty, so there is nothing
    else to read. Refusing it is the price of refusing the temple photograph."""
    assert not matching.describes(
        "map of Kolar Gold Fields Karnataka",
        "File:146-Kolar Gold Fields constituency.svg",
    )
