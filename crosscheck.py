"""Where the sources disagree with each other.

Fact-checking flattened every source's key facts into one list before asking
the model to judge them, which threw away the only thing a cross-check needs:
who said what. Two sources giving different figures for the same quantity came
out as two claims in a heap, and the model was free to verify both, pick one,
or split the difference. On a contested subject - which is the kind this
channel takes on - that is the failure mode that matters, because the
disagreement *is* the story.

Two halves here, and the first is the reliable one:

* **Figures that do not match.** Deterministic, and the only kind of
  disagreement that can be found without judgement: the same quantity reported
  as two different numbers. Uses the same parser the chart builder does, so
  "≈ 45 metric tonnes" and "45,000 kg" are read as amounts rather than as
  strings that differ.
* **Attribution for everything else.** Claims are carried with the source that
  made them, so the model that judges them can be asked which source a
  disagreement is between rather than being handed an anonymous pile.

A disagreement is not an error. Nothing here throws a claim away; it marks it
so the script can say "sources differ" instead of stating one figure as fact.
"""

from __future__ import annotations

import re

import charts

# Two figures for one quantity this far apart are a real disagreement rather
# than rounding or a unit conversion nobody spelled out. 5% allows "≈ 45
# tonnes" against "45.6 tonnes"; it does not allow 45 against 60.
TOLERANCE = 0.05

_NOISE = re.compile(r"[^a-z0-9 ]+")
_STOP = {
    "the", "a", "an", "of", "in", "at", "on", "for", "to", "and", "or", "per",
    "total", "estimated", "approximate", "approximately", "about", "average",
    "number", "amount", "value", "figure",
}


def subject_of(metric: str) -> frozenset[str]:
    """The words that say what a figure is *of*, for matching one against another.

    "Peak annual production" and "Annual peak production" name the same thing
    and have to compare equal, so this is a bag of meaningful words rather than
    a normalised string.
    """
    words = _NOISE.sub(" ", (metric or "").lower()).split()
    return frozenset(word for word in words if len(word) > 2 and word not in _STOP)


def _same_subject(first: frozenset[str], second: frozenset[str]) -> bool:
    """Whether two metric names are naming the same quantity.

    One being contained in the other, rather than the two being equal: research
    writes "Total gold extracted" in one place and "Total gold extracted over
    the life of the mine" in another, and requiring the exact same words found
    no conflicts at all. Two words is the floor, so that a pair of one-word
    metrics does not match everything.
    """
    if len(first) < 2 or len(second) < 2:
        return False
    return first <= second or second <= first


def _disagree(first: tuple[float, str], second: tuple[float, str]) -> bool:
    """Whether two parsed figures are really different.

    Different units are not a disagreement: tonnes against troy ounces is the
    same quantity in two languages, and this has no business converting between
    them and guessing wrong.
    """
    (first_amount, first_unit), (second_amount, second_unit) = first, second
    if first_unit != second_unit:
        return False
    largest = max(abs(first_amount), abs(second_amount))
    if largest == 0:
        return False
    return abs(first_amount - second_amount) / largest > TOLERANCE


def conflicting_figures(entries: list[dict]) -> list[dict]:
    """Quantities reported twice with different numbers.

    Each entry is a `numbers_and_data` row - {metric, value, context} - and may
    carry a `source` naming where it came from.
    """
    parsed = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        figure = charts.parse_value(str(entry.get("value") or ""))
        subject = subject_of(str(entry.get("metric") or ""))
        if figure and subject:
            parsed.append((subject, figure, entry))

    conflicts = []
    seen: set[tuple] = set()

    for index, (subject, figure, entry) in enumerate(parsed):
        for other_subject, other_figure, other_entry in parsed[index + 1:]:
            if not _same_subject(subject, other_subject):
                continue
            if not _disagree(figure, other_figure):
                continue
            pair = tuple(sorted((str(entry.get("value")), str(other_entry.get("value")))))
            key = (subject, pair)
            if key in seen:
                continue
            seen.add(key)
            conflicts.append({
                "subject": str(entry.get("metric") or ""),
                "values": [str(entry.get("value") or ""), str(other_entry.get("value") or "")],
                "sources": [
                    str(entry.get("source") or "unattributed"),
                    str(other_entry.get("source") or "unattributed"),
                ],
            })

    return conflicts


def attributed_claims(sources: list[dict]) -> list[dict]:
    """Every key fact, still carrying the source that made it."""
    claims = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        title = str(source.get("title") or source.get("url") or "a source")
        for fact in source.get("key_facts") or []:
            text = str(fact).strip()
            if text:
                claims.append({"claim": text, "source": title})
    return claims


def describe(conflicts: list[dict]) -> str:
    """The conflicts as a line the fact-checking prompt can carry."""
    if not conflicts:
        return ""
    lines = [
        f"- {conflict['subject']}: {' vs '.join(conflict['values'])} "
        f"({' vs '.join(conflict['sources'])})"
        for conflict in conflicts
    ]
    return (
        "\nThese quantities were reported with different figures. Treat each as "
        "disputed rather than choosing one or averaging them:\n" + "\n".join(lines) + "\n"
    )
