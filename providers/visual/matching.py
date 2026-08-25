"""Whether a stock result is actually of the thing that was asked for.

The stock libraries answer every query. Asked for "chart gold production 1910s
Kolar peak 1919" Pexels reports eight thousand results and returns a
cryptocurrency trading room; asked for "official closure notice BGML 2001" it
returns a photograph of signs on a wire fence. It is not matching the query so
much as falling back to what is popular, and the visual agent took the first
result unconditionally - so a documentary about an Indian gold mine carried a
Binance chart and a Turkish military zone sign.

There is a description to check against, even though `alt` comes back null:
the result's own page URL is a slug written by a human -
`dynamic-cryptocurrency-trading-room-setup`. Comparing that with the words of
the query separates the three cases above cleanly, and costs no key, no quota
and no network call.

What this deliberately does not do is insist on the whole query. A hint like
"official closure notice BGML 2001 Kolar gold fields" contains a company
acronym, a year and a place name that no stock library has ever heard of. Only
the ordinary nouns can match, and requiring more than that would reject
everything - including the results that are genuinely fine.
"""

from __future__ import annotations

import re

_WORDS = re.compile(r"[a-z]+")

# Words that carry no subject: they match everything and mean nothing.
STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "with", "and", "or",
    "from", "by", "into", "over", "under", "this", "that", "these", "those",
    "video", "footage", "clip", "stock", "shot", "scene", "image", "photo",
    "background", "free", "hd", "shows", "showing",
}

# Enough overlap to believe the result is of the subject. Two ordinary nouns
# in common is the line these three real cases fall either side of.
MIN_MATCHES = 2

# Words that name a *kind of thing* rather than a subject. When a hint asks for
# one, a picture of the place is not a substitute: searching Commons for "map
# of Karnataka India" returns a photograph of a water tank in Hampi, which
# shares two words with the query and is not a map. So these have to appear in
# the result's own description, not merely be outnumbered by other matches.
ARTEFACT_TERMS = (
    "map", "chart", "graph", "diagram", "blueprint", "schematic", "plan",
    "timeline", "table",
)


def _stem(word: str) -> str:
    """Crude suffix stripping, so `mine` and `mining` are the same word.

    Not a real stemmer and does not need to be: it exists so that a plural or
    a gerund in a slug still matches the singular in a hint.
    """
    for suffix in ("ing", "ers", "er", "ies", "es", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    # And a trailing silent e, so that stripping "ing" off `mining` lands on
    # the same stem as `mine` rather than one letter short of it.
    if len(word) > 3 and word.endswith("e"):
        word = word[:-1]
    return word


def terms(text: str) -> set[str]:
    """The meaningful words in a query or a description, stemmed."""
    return {
        _stem(word)
        for word in _WORDS.findall((text or "").lower())
        if len(word) > 2 and word not in STOPWORDS
    }


def slug_words(url: str) -> str:
    """The human description inside a stock library's page URL.

    Trailing digits are dropped because every slug ends in the asset's id, and
    an id shares no meaning with a year in the query.
    """
    tail = (url or "").rstrip("/").rsplit("/", 1)[-1]
    return " ".join(part for part in tail.split("-") if not part.isdigit())


def overlap(query: str, *descriptions: str) -> int:
    """How many of the query's words the description accounts for."""
    wanted = terms(query)
    if not wanted:
        return 0
    described = set()
    for description in descriptions:
        described |= terms(description)
    return len(wanted & described)


def required(query: str) -> set[str]:
    """Words the result must carry, not merely score against."""
    return terms(query) & {_stem(word) for word in ARTEFACT_TERMS}


def describes(query: str, *descriptions: str) -> bool:
    """Whether this result is plausibly of what the query asked for."""
    described = set()
    for description in descriptions:
        described |= terms(description)

    if not required(query) <= described:
        return False
    return overlap(query, *descriptions) >= MIN_MATCHES
