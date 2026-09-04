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
