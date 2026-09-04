"""Whether a draft reads as speech or as prose.

The complaint these exist for is that the finished videos sounded like
someone reading a book aloud. That is not a matter of taste - it has
countable causes, and this is where they are counted.
"""

import spoken_register as register

ESSAY = (
    "The mission was significant because it demonstrated that a space agency "
    "operating on a fraction of the budget available to its international "
    "peers could nevertheless achieve an outcome that had eluded far better "
    "funded organisations for several decades. Moreover, the technical "
    "approach adopted by the engineering team departed substantially from the "
    "methods that had been established as standard practice throughout the "
    "preceding period of the programme. In conclusion, the achievement was "
    "notable for reasons that extend well beyond the immediate scientific "
    "return that was obtained from the instruments carried aboard. It should "
    "be noted that the costs involved remainedlow throughout."
)

SPOKEN = (
    "Sochiye. Ek engineer, ek desk, ek budget jo Hollywood film se bhi kam "
    "hai. Aur usne wo kar diya jo bade desh saalon se nahi kar paaye. Kaise? "
    "Yahin se kahani shuru hoti hai. Pehle ek cheez samajh lijiye. Sab log "
    "maan chuke the ki yeh possible hi nahi hai."
)


def test_a_page_written_paragraph_is_caught():
    notes = register.problems(ESSAY)
    assert notes
    assert any("30 words or more" in note for note in notes)
    assert any("moreover" in note.lower() for note in notes)


def test_something_written_to_be_said_passes():
    assert register.problems(SPOKEN) == []


def test_the_literary_hindi_register_counts_as_written():
    """"Lekin" is what people say; "parantu" is what textbooks print."""
    assert "parantu" in register.written_phrases("Yeh sach hai, parantu adhura hai.")
    assert "kintu" in register.written_phrases("Kintu sawaal yahi hai.")
    assert register.written_phrases("Yeh sach hai, lekin adhura hai.") == []


def test_a_long_average_is_flagged_even_when_no_single_sentence_is_huge():
    """Uniform mid-length sentences are what makes narration drone."""
    line = (
        "The committee reviewed the proposal at length and then decided to "
        "postpone the vote until the spring session had formally opened. "
    )
    notes = register.problems(line * 6)
    assert any("average" in note for note in notes)


def test_a_hook_too_short_to_measure_is_not_judged():
    """Two sentences say nothing about how a writer writes."""
    assert register.problems("A single very long opening sentence that runs on and on and on.") == []


def test_the_measurements_are_reported_as_numbers():
    found = register.measure(SPOKEN)
    assert found["sentences"] > 4
    assert 0 < found["mean_words"] < register.MAX_MEAN_WORDS
    assert found["written_phrases"] == []


def test_notes_say_what_to_do_rather_than_naming_a_rule():
    """They go straight back to the writer, so they have to read as direction."""
    for note in register.problems(ESSAY):
        assert note.endswith(".")
        assert "MAX_" not in note


# --------------------------------------------------------------------------
# The first fifteen seconds
# --------------------------------------------------------------------------

def test_a_script_that_clears_its_throat_is_caught():
    """Nothing else in a video decides as much about whether it gets watched.

    A greeting is the most expensive sentence in a script: it is spent
    before anyone has a reason to stay.
    """
    notes = register.opening_problems(
        "Namaskar doston, aaj hum baat karenge ek aisi cheez ki jo sab badal degi."
    )
    assert notes
    assert "namaskar doston" in notes[0]
    assert "aaj hum baat karenge" in notes[0]


def test_the_english_version_is_caught_too():
    assert register.opening_problems("Hey guys, welcome back to the channel. In this video we look at ships.")


def test_a_cold_open_passes():
    assert register.opening_problems(
        "1956. Ek dock. Ek aadmi ne ek metal box uthaya, aur duniya ka trade "
        "hamesha ke liye badal gaya."
    ) == []


def test_only_the_opening_is_judged():
    """A phrase four minutes in is not how the video starts.

    "In this video" said once at the end of a long recap is a different thing
    from it being the first thing a viewer hears.
    """
    late = " ".join(["shipping"] * 60) + " and in this video we saw why."
    assert register.opening_problems(late) == []


def test_the_note_says_what_to_do_instead():
    notes = register.opening_problems("Welcome to the channel. Today we will talk about ports.")
    assert "Open in the middle of something concrete" in notes[0]


def test_an_empty_script_has_no_opening_to_judge():
    assert register.opening_problems("") == []
