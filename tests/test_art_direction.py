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
