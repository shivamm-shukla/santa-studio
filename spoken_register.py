"""Whether a draft reads as speech or as prose.

The script agent already checks one thing about a draft mechanically - that
every figure in it comes from a verified claim - and rewrites the draft when
it does not. This is the same idea applied to the other half of the
complaint about the finished videos: that they sound like someone reading a
book aloud.

That is not a vague quality. It has specific, countable causes, and a model
that is told "write in a natural spoken voice" and then handed two hundred
words of fact-checking constraint will produce all of them anyway, because
the constraint is concrete and the instruction is not.

    A long average sentence. Speech runs about twelve to fifteen words a
    sentence, because that is roughly what fits in a breath. Prose runs
    twenty-five and up, and a narrator reading twenty-five-word sentences
    sounds like a narrator reading.

    Sentences nobody could say. One in seven at thirty words or more is a
    paragraph pretending to be a line of narration.

    Connectives that exist only on the page. Nobody says "moreover" out
    loud, or "uparokt", or "in conclusion". Each one is a small signal that
    what is being read was written to be read.

The checks return notes rather than a verdict, because the caller shows them
to the writer and asks for the scene again - the same loop the invented
figures go through.
"""

from __future__ import annotations

import re

# Roughly a breath. Spoken narration sits near thirteen; the ceiling is set
# above that so a draft is only pulled up when it is genuinely writing prose,
# not when it happens to have a couple of long lines.
MAX_MEAN_WORDS = 17.0

# A sentence this long cannot be delivered in one piece, so the voice has to
# break it somewhere the writing did not ask it to.
LONG_SENTENCE_WORDS = 30

# Some are fine. Every seventh is a habit.
MAX_LONG_FRACTION = 0.15

# Below this there is not enough text to measure anything about it.
MIN_SENTENCES = 4

_SENTENCE_END = re.compile(r"[.!?।\n]+")

# Words and phrases that belong to writing rather than to speech. The Hindi
# half is the literary register specifically - "lekin" is what people say and
# "parantu" is what textbooks print, and a script full of the second is
# exactly the "reading from a book" complaint.
WRITTEN_ONLY = (
    "moreover",
    "furthermore",
    "additionally",
    "consequently",
    "nevertheless",
    "nonetheless",
    "henceforth",
    "aforementioned",
    "whereby",
    "thereby",
    "herein",
    "in conclusion",
    "in summary",
    "it is important to note",
    "it should be noted",
    "as previously mentioned",
    "this article",
    "firstly",
    "secondly",
    "uparokt",
    "iske atirikt",
    "nishkarsh",
    "tatpashchat",
    "yadyapi",
    "tathapi",
    "parantu",
    "kintu",
    "prastut",
)

_PHRASES = tuple(
    (phrase, re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE))
    for phrase in WRITTEN_ONLY
)


# How a video must not begin. Every one of these is a writer clearing their
# throat: the viewer already knows they are watching a video, already knows
# what it is called, and is deciding in the first few seconds whether to keep
# watching. A channel-level greeting is the most expensive sentence in the
# script, because it is spent before anyone has a reason to stay.
THROAT_CLEARING = (
    "in this video",
    "in today's video",
    "welcome back",
    "welcome to",
    "hello friends",
    "hi guys",
    "hey guys",
    "before we begin",
    "before we start",
    "let's dive in",
    "let's get started",
    "today we will",
    "today we're going to",
    "i want to talk about",
    "is video mein",
    "aaj ke video mein",
    "aaj hum baat karenge",
    "aaj hum jaanenge",
    "namaskar doston",
    "namaste doston",
    "swagat hai",
    "chaliye shuru karte hain",
    "toh chaliye",
    "dosto aaj",
)

_OPENERS = tuple(
    (phrase, re.compile(r"\b" + re.escape(phrase) + r"\b", re.IGNORECASE))
    for phrase in THROAT_CLEARING
)

# How much of the script counts as the opening. Roughly the first fifteen
# seconds at narration pace, which is the window a viewer decides in.
HOOK_WORDS = 40


def opening_problems(text: str) -> list[str]:
    """What is wrong with how this script starts, if anything.

    Kept apart from `problems` because it is about one specific stretch of
    the script rather than about the writing throughout, and because the
    first fifteen seconds are worth their own check: nothing else in a video
    decides as much about whether it gets watched.
    """
    opening = " ".join((text or "").split()[:HOOK_WORDS])
    if not opening:
        return []

    found = [phrase for phrase, pattern in _OPENERS if pattern.search(opening)]
    if not found:
        return []

    return [
        "It opens by clearing its throat: "
        + ", ".join(f"{phrase!r}" for phrase in found)
        + ". The viewer knows they are watching a video and is deciding in "
        "the first few seconds whether to keep watching. Open in the middle "
        "of something concrete instead - a moment, a number that should not "
        "be true, a question they cannot put down."
    ]


def sentences(text: str) -> list[str]:
    """The draft split into things a narrator has to say in one go."""
    return [part.strip() for part in _SENTENCE_END.split(text or "") if part.strip()]


def written_phrases(text: str) -> list[str]:
    """Page-only connectives the draft used, in the order they are listed."""
    return [phrase for phrase, pattern in _PHRASES if pattern.search(text or "")]


def measure(text: str) -> dict:
    """The countable facts about how a draft reads."""
    lines = sentences(text)
    lengths = [len(line.split()) for line in lines]
    long_ones = [n for n in lengths if n >= LONG_SENTENCE_WORDS]

    return {
        "sentences": len(lines),
        "mean_words": (sum(lengths) / len(lengths)) if lengths else 0.0,
        "longest_words": max(lengths) if lengths else 0,
        "long_fraction": (len(long_ones) / len(lengths)) if lengths else 0.0,
        "written_phrases": written_phrases(text),
    }


def problems(text: str) -> list[str]:
    """What reads as prose in this draft. Empty means it reads as speech.

    Each note is written to be handed straight back to the writer, so it says
    what is wrong and what the target is rather than naming a rule.
    """
    found = measure(text)
    if found["sentences"] < MIN_SENTENCES:
        return []

    notes = []
    if found["mean_words"] > MAX_MEAN_WORDS:
        notes.append(
            f"The sentences average {found['mean_words']:.0f} words. Spoken "
            f"narration sits near 13, because that is what fits in a breath. "
            f"Break the long ones up."
        )
    if found["long_fraction"] > MAX_LONG_FRACTION:
        notes.append(
            f"{found['long_fraction'] * 100:.0f}% of the sentences run "
            f"{LONG_SENTENCE_WORDS} words or more, the longest at "
            f"{found['longest_words']}. Nobody can say those in one piece."
        )
    if found["written_phrases"]:
        notes.append(
            "These are written connectives, not spoken ones - nobody says "
            f"them out loud: {', '.join(found['written_phrases'])}."
        )
    return notes
