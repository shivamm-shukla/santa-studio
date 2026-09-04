"""Chooses what gets drawn on top of the picture.

The Timeline has carried an `overlays` list since the schema was written, the
renderer has known how to draw text, lower thirds, counters and highlight
boxes for just as long, and the Style Profile has a `GraphicsStyle.density`
that reference analysis fills in from real channels. Nothing ever put an
overlay in the list. Every video shipped with the layer empty - which on an
explainer channel is roughly half of what is on screen.

The problem this solves is not drawing; it is deciding *what* to draw and
*when*, without spending an LLM call. Two things already in the state answer
that between them:

* the script's own words, which say what the video is about, and
* the word-level timings from forced alignment, which say exactly when each
  of those words is spoken.

So a number on screen appears on the beat the narrator says it, and a name
appears while it is being named. That is the whole mechanism, and it is why
alignment had to be fixed first - against evenly-spread estimates these would
land in roughly the right minute rather than on the word.

What gets picked, in priority order:

1. **counters** - quantities and years. A figure heard once is forgotten; the
   same figure read off the screen is the thing people quote back.
2. **text callouts** - proper nouns, the names the video keeps returning to.
3. **lower third** - the topic, once, under the hook.
4. **highlight** - a soft box behind a moment with nothing else to label.

`density` is a budget in overlays per minute, so a profile that wants a busy
screen gets one and `calm-narrative` (density 0) gets none at all.
"""

from __future__ import annotations

import re

from timeline import Overlay

# A quantity worth putting on screen: 1,200 / 47% / $30 / 3.5. Bare single
# digits are excluded - "one of the two reasons" is not a statistic.
_QUANTITY = re.compile(r"^[₹$€£]?\d[\d,]*(?:\.\d+)?%?$")
_YEAR = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")

# Sentence-initial capitals are grammar, not emphasis, so a candidate name has
# to survive being stripped of leading punctuation and still look deliberate.
_STRIP = re.compile(r"^[^\w₹$€£]+|[^\w%]+$")

# Words that start a sentence in Hinglish or English and would otherwise read
# as proper nouns every time they appear.
_NOT_A_NAME = {
    "the", "this", "that", "these", "those", "and", "but", "so", "then", "now",
    "here", "there", "what", "why", "how", "when", "where", "who", "it", "its",
    "a", "an", "in", "on", "at", "of", "to", "for", "with", "by", "from",
    "aaj", "yeh", "woh", "toh", "aur", "lekin", "phir", "abhi", "kya", "kyun",
    "kaise", "jab", "agar", "hum", "main", "aap", "iska", "uska", "par", "ek",
}

# A chart has to be read, not glanced at, so it holds far longer than a
# callout does - and it goes in the middle third, where a viewer is following
# an argument rather than being hooked or sent off.
CHART_SECONDS = 5.5
CHART_WINDOW = (0.35, 0.65)

# Overlays this close together read as flicker rather than as emphasis.
MIN_GAP_SECONDS = 3.5
# Long enough to read a short phrase without dominating the shot.
HOLD_SECONDS = 2.6
# The topic card under the hook, which is the one overlay that can run longer.
LOWER_THIRD_SECONDS = 3.6

# Vertical placement, as a fraction of frame height. Callouts sit high because
# captions own the bottom of the frame (CaptionStyle.position defaults to
# 0.82) and two stacked text layers are unreadable.
CALLOUT_Y = 0.20
LOWER_THIRD_Y = 0.68
HIGHLIGHT_Y = 0.5


def _clean(word: str) -> str:
    return _STRIP.sub("", word or "")


def _is_quantity(word: str) -> bool:
    return bool(_QUANTITY.match(word)) and (
        len(word.strip("₹$€£%")) > 1 or word.endswith("%")
    )


def _is_name(word: str, is_sentence_start: bool) -> bool:
    if is_sentence_start or len(word) < 4:
        return False
    if word.lower() in _NOT_A_NAME:
        return False
    return word[0].isupper() and not word.isupper()


def _candidates(word_timestamps: list[dict]) -> list[dict]:
    """Moments worth marking, in the order they are spoken.

    Consecutive capitalised words are merged, so "Rayleigh Scattering" is one
    callout rather than two fighting for the same second of screen time.
    """
    found: list[dict] = []
    index = 0
    ends_sentence = True  # the first word of the script starts a sentence

    while index < len(word_timestamps):
        entry = word_timestamps[index]
        raw = str(entry.get("word", ""))
        word = _clean(raw)
        starts_sentence = ends_sentence
        ends_sentence = raw.rstrip().endswith((".", "!", "?", "।"))

        if not word:
            index += 1
            continue

        if _YEAR.match(word) or _is_quantity(word):
            quantity = _is_quantity(word) and not _YEAR.match(word)
            found.append({
                "kind": "counter",
                "text": word,
                "start": float(entry.get("start", 0.0)),
                "weight": 3.0 if quantity else 2.5,
                "countable": quantity,
            })
            index += 1
            continue

        if _is_name(word, starts_sentence):
            phrase = [word]
            last = entry
            look = index + 1
            while look < len(word_timestamps) and len(phrase) < 3:
                nxt = word_timestamps[look]
                nxt_word = _clean(str(nxt.get("word", "")))
                if not _is_name(nxt_word, False):
                    break
                phrase.append(nxt_word)
                last = nxt
                look += 1

            found.append({
                "kind": "text",
                "text": " ".join(phrase),
                "start": float(entry.get("start", 0.0)),
                "weight": 2.0 + 0.4 * len(phrase),
            })
            ends_sentence = str(last.get("word", "")).rstrip().endswith((".", "!", "?", "।"))
            index = look
            continue

        index += 1

    return found


def _spread(candidates: list[dict], budget: int, duration: float) -> list[dict]:
    """Picks `budget` moments, best first, never bunched together.

    Taking the top N by weight alone clusters them wherever the script
    happens to be dense with numbers, leaving minutes of bare picture either
    side. Enforcing a gap as they are accepted spreads them out for free.
    """
    if budget <= 0:
        return []

    chosen: list[dict] = []
    for candidate in sorted(candidates, key=lambda c: (-c["weight"], c["start"])):
        if candidate["start"] + HOLD_SECONDS > duration:
            continue
        if any(abs(candidate["start"] - c["start"]) < MIN_GAP_SECONDS for c in chosen):
            continue
        chosen.append(candidate)
        if len(chosen) >= budget:
            break

    return sorted(chosen, key=lambda c: c["start"])


def _style(profile, *, size_ratio: float) -> dict:
    graphics = profile.graphics
    return {
        "font_size_ratio": size_ratio,
        "color": "#FFFFFF",
        "stroke_color": "black",
        "stroke_width": 2,
        "accent_color": graphics.accent_color,
        "width_ratio": 0.8,
    }


def _accent_rgb(colour: str) -> tuple[int, int, int]:
    value = (colour or "").lstrip("#")
    if len(value) != 6:
        return (232, 133, 60)
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return (232, 133, 60)


# A chapter card holds longer than a callout does. It is not a label on
# something happening; it is the thing happening, and a viewer has to have
# time to read it and register that the video has moved on.
CHAPTER_CARD_SECONDS = 2.8


def build_overlays(
    word_timestamps: list[dict],
    duration: float,
    profile,
    topic: str = "",
    sources: list | None = None,
    figures: list | None = None,
    chapters: list | None = None,
) -> list[Overlay]:
    """The overlay layer for one video.

    Returns an empty list rather than raising whenever there is nothing to
    work with - a profile with density 0, a run with no aligned words, a
    script with no names or numbers in it. An empty overlay layer is a valid
    Timeline; a broken one is not.
    """
    graphics = getattr(profile, "graphics", None)
    if graphics is None or duration <= 0:
        return []

    kinds = set(graphics.kinds or ())
    overlays: list[Overlay] = []
    taken: list[float] = []

    def free(at: float) -> bool:
        return all(abs(at - other) >= MIN_GAP_SECONDS for other in taken)

    # 1. The topic, once, under the hook.
    if topic and "lower_third" in kinds and duration > LOWER_THIRD_SECONDS + 2:
        overlays.append(Overlay(
            start=1.0,
            duration=LOWER_THIRD_SECONDS,
            kind="lower_third",
            text=topic,
            position=(0.5, LOWER_THIRD_Y),
            anchor="center",
            style=_style(profile, size_ratio=0.052),
            animate_in=graphics.animate_in,
            animate_out=graphics.animate_out,
        ))
        taken.append(1.0)

    # 1b. The chapter titles, where each chapter begins.
    #
    # A long video needs to tell a viewer where they are in it - that is
    # what a section card is for, and it is one of the most recognisable
    # things a documentary channel does. The titles have existed since the
    # script started being planned as chapters; nothing was drawing them.
    #
    # They are laid down before the budget is worked out and are not counted
    # against it: a chapter card is structure rather than decoration, and a
    # dense profile should not crowd out the one overlay that says where you
    # are.
    for mark in chapters or []:
        if not isinstance(mark, dict):
            continue
        title = str(mark.get("title") or "").strip()
        try:
            at = float(mark.get("at"))
        except (TypeError, ValueError):
            continue
        # The opening card is the topic's; the closing seconds are the
        # citation's. A chapter that starts inside either would be drawn over
        # something already there.
        if not title or at < LOWER_THIRD_SECONDS + 1 or at > duration - CHAPTER_CARD_SECONDS - 1:
            continue
        overlays.append(Overlay(
            start=at,
            duration=CHAPTER_CARD_SECONDS,
            kind="lower_third",
            text=title,
            position=(0.5, LOWER_THIRD_Y),
            anchor="center",
            style=_style(profile, size_ratio=0.052),
            animate_in=graphics.animate_in,
            animate_out=graphics.animate_out,
        ))
        taken.append(at)

    budget = int(round((graphics.density or 0.0) * duration / 60.0))
    if budget <= 0:
        return overlays

    # 2 and 3. Numbers and names, on the word they are spoken.
    for candidate in _spread(_candidates(word_timestamps), budget, duration):
        kind = candidate["kind"]
        if kind not in kinds:
            kind = "text" if "text" in kinds else next(iter(kinds), "text")
        if not free(candidate["start"]):
            continue

        is_counter = kind == "counter"
        overlay = Overlay(
            start=round(candidate["start"], 2),
            duration=min(HOLD_SECONDS, duration - candidate["start"]),
            kind=kind,
            text=candidate["text"],
            position=(0.5, CALLOUT_Y),
            anchor="center",
            style=_style(profile, size_ratio=0.075 if is_counter else 0.055),
            animate_in=graphics.animate_in,
            animate_out=graphics.animate_out,
        )
        if is_counter:
            overlay.data = {"to": candidate["text"]}
            # A quantity counts up from nothing; a year does not. Counting to
            # 1902 from zero spins through four millennia to land on a date,
            # which reads as a broken effect rather than an emphasis. Only a
            # quantity gets a starting value, and the renderer counts exactly
            # those overlays that carry one.
            if candidate.get("countable"):
                overlay.data["from"] = "0"
        overlays.append(overlay)
        taken.append(candidate["start"])

    # 3b. One chart, from the run's own researched figures.
    #
    # This exists because the visual chain refuses to *generate* a chart - an
    # image model asked for one invents the numbers - which left a scene that
    # wants to show production figures getting a photograph of a mining yard.
    # charts.py only returns a series when two or more figures share a unit and
    # sit within sight of each other, so most runs get nothing here, which is
    # the correct outcome rather than a missing feature.
    if "chart" in kinds and duration > CHART_SECONDS + 4:
        import charts

        series = charts.comparable(figures or [])
        if series:
            start = _chart_moment(duration, taken)
            if start is not None:
                overlays.append(Overlay(
                    start=round(start, 2),
                    duration=CHART_SECONDS,
                    kind="chart",
                    text="",
                    position=(0.5, 0.5),
                    anchor="center",
                    style=_style(profile, size_ratio=0.045),
                    animate_in=graphics.animate_in,
                    animate_out=graphics.animate_out,
                    data={
                        "series": [[label, amount, unit] for label, amount, unit in series],
                        "title": _chart_title(series),
                    },
                ))
                taken.append(start)

    # 4. A citation card at the end, if the run recorded where it read.
    if graphics.show_source_citations and sources and duration > 6:
        label = _citation_label(sources)
        if label and "text" in kinds:
            start = max(0.0, duration - 4.5)
            if free(start):
                overlays.append(Overlay(
                    start=round(start, 2),
                    duration=min(3.5, duration - start),
                    kind="text",
                    text=label,
                    position=(0.5, CALLOUT_Y),
                    anchor="center",
                    style=_style(profile, size_ratio=0.032),
                    animate_in="fade",
                    animate_out="fade",
                ))

    return sorted(overlays, key=lambda o: o.start)


def _citation_label(sources: list) -> str:
    """"Sources: en.wikipedia.org, nasa.gov" from whatever shape the research
    agent produced - a list of urls, or of dicts carrying one."""
    hosts: list[str] = []
    for source in sources[:6]:
        url = source if isinstance(source, str) else (
            source.get("url") or source.get("source") or "" if isinstance(source, dict) else ""
        )
        match = re.search(r"https?://([^/]+)", str(url))
        if not match:
            continue
        host = match.group(1).lower().removeprefix("www.")
        if host and host not in hosts:
            hosts.append(host)
    return "Sources: " + ", ".join(hosts[:3]) if hosts else ""


def _chart_moment(duration: float, taken: list[float]) -> float | None:
    """A clear stretch in the middle third long enough to hold a chart."""
    first, last = CHART_WINDOW
    step = 0.5
    at = duration * first
    while at + CHART_SECONDS <= duration * last + CHART_SECONDS:
        if at + CHART_SECONDS > duration:
            break
        if all(abs(at - other) >= CHART_SECONDS for other in taken):
            return at
        at += step
    return None


def _chart_title(series: list) -> str:
    """What the bars have in common, which is the unit they share."""
    unit = series[0][2] if series else ""
    return f"Compared, in {unit}" if unit else "Compared"
