"""The camera brief, and the two rules it exists to enforce.

Left to itself the model makes the same photograph every time - subject
centred, sun low behind it, sky orange, nothing in the foreground - and twenty
of those in one video is what makes a video look generated regardless of how
good any one frame is. These cover that the brief varies, that it varies
deterministically so the cache still holds, and that it does not reach for the
looks that give the game away.
"""

from providers.visual import art_direction as ad

SUBJECT = "abandoned gold mine headframe, Kolar Gold Fields"


def test_the_subject_survives_into_the_brief():
    assert SUBJECT in ad.brief(SUBJECT)


def test_a_brief_specifies_a_camera_and_not_just_a_scene():
    brief = ad.brief(SUBJECT)

    assert "f/" in brief or "telephoto" in brief, "no aperture and no lens"
    assert "mm" in brief


def test_the_same_shot_asked_for_twice_is_the_same_brief():
    """The generated-still cache is keyed on the shot, so this has to hold."""
    assert ad.brief(SUBJECT, 4) == ad.brief(SUBJECT, 4)


def test_two_scenes_are_not_photographed_the_same_way():
    briefs = {ad.brief(SUBJECT, v) for v in range(8)}

    assert len(briefs) >= 6, "the same subject is being shot the same way each time"


def test_consecutive_scenes_do_not_walk_the_vocabularies_in_step():
    """Otherwise every video shares one sequence of looks instead of one look."""
    lights = [next(l for l in ad.LIGHT if l in ad.brief(SUBJECT, v)) for v in range(6)]
    positions = [ad.LIGHT.index(l) for l in lights]
    steps = {(b - a) % len(ad.LIGHT) for a, b in zip(positions, positions[1:])}

    assert len(steps) > 1, "the light is advancing by a fixed step"


def test_no_brief_asks_for_the_light_that_gives_it_away():
    """A low sun behind the subject is the loudest tell there is."""
    for variation in range(40):
        brief = ad.brief(SUBJECT, variation).lower()
        assert "golden hour" not in brief
        assert "sunset" not in brief.replace("no sunset", "")


def test_black_and_white_stays_the_exception():
    """A documentary that keeps dropping into monochrome looks stylised."""
    mono = sum("black and white" in ad.brief(SUBJECT, v) for v in range(80))

    assert 0 < mono <= 16, f"{mono} of 80 shots in monochrome"


def test_the_brief_refuses_what_the_model_adds_unasked():
    brief = ad.brief(SUBJECT)

    for unwanted in ("no watermark", "no logo", "not a 3D render", "no letterbox bars"):
        assert unwanted in brief


def test_an_empty_subject_is_not_dressed_up_as_a_photograph():
    assert ad.brief("") == ""
    assert ad.brief("   ") == ""


def test_no_brief_names_a_film_stock():
    """Naming a medium returned photographs of that medium - a print with a
    paper margin, a slide in its mount - which then has to be cropped back out
    of the frame. The look is described instead."""
    brands = ("portra", "ektachrome", "tri-x", "ilford", "kodak", "fujifilm", "superia", "35mm film")

    for variation in range(40):
        brief = ad.brief(SUBJECT, variation).lower()
        for brand in brands:
            assert brand not in brief, f"{brand} named in variation {variation}"


def test_no_brief_puts_the_sun_in_the_picture():
    """A sun disc in frame reads as rendered every time."""
    for variation in range(40):
        assert "no sun in the picture" in ad.brief(SUBJECT, variation)


def test_no_framing_makes_the_subject_small():
    """A landscape with the subject in it is a good photograph of the wrong thing."""
    for framing in ad.FRAMING:
        assert "small" not in framing


# ---------------------------------------------------------------------------
# Shots that must not be generated at all
# ---------------------------------------------------------------------------

def test_a_document_is_refused_rather_than_invented():
    """Asked for an official closure notice, the generator produced a sign
    reading OFFICIALT NOTICE / CLOSED / LLGML 2001 and a line of garbled
    English - a fabricated official record about a real company, cut into a
    documentary whose whole claim is that its sources can be checked."""
    assert ad.refuses("official closure notice BGML 2001 Kolar gold fields")


def test_a_chart_of_invented_figures_is_refused_too():
    assert ad.refuses("chart gold production 1910s Kolar peak 1919")


def test_a_photographable_subject_is_not_refused():
    assert ad.refuses("deep underground gold mine shaft Kolar") == ""
    assert ad.refuses("aerial view of a mining township") == ""


def test_the_refusal_matches_whole_words_only():
    """A hint about a sign is refused; one about designing is not."""
    assert ad.refuses("designing a new headframe") == ""
    assert ad.refuses("a warning sign at the pit head")


def test_the_refusal_says_which_word_caused_it():
    assert "notice" in ad.refuses("a closure notice on the gate")


# ---- photographing the place instead ---------------------------------------


def test_the_paperwork_comes_out_and_the_place_stays():
    stripped = ad.without_artefacts("official closure notice BGML 2001 Kolar gold fields")

    assert "notice" not in stripped
    assert "Kolar" in stripped and "closure" in stripped


def test_what_is_left_is_something_that_can_be_generated():
    stripped = ad.without_artefacts("chart gold production 1910s Kolar peak 1919")

    assert ad.refuses(stripped) == ""
    assert ad.brief(stripped)


def test_a_subject_with_no_paperwork_in_it_is_untouched():
    subject = "deep underground gold mine shaft Kolar"

    assert ad.without_artefacts(subject) == subject
