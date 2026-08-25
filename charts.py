"""Charts built from the figures research actually returned.

The visual chain refuses to generate a chart, because asked for one the image
model invents a table - 1905 CIL, 1903 LIL, POLAL - about a real company. That
refusal is right and it leaves a hole: a scene that wants to show production
figures gets a photograph of a mining yard instead. This fills it, from the
`numbers_and_data` a research run already produces (eleven entries on the run
this was written against).

The one thing this must not do is chart figures that do not belong on the same
axis. A run returns 45 tonnes of gold, a 3,200 metre shaft, $500 an ounce and
3,000 workers; putting those in one bar chart produces a picture that means
nothing while looking authoritative, which is the same failure as the invented
table in a tidier font. So a chart is only drawn when two or more figures share
a unit, and everything else is shown as a single stat card.

On the run this was built against that rule finds the comparison the whole
story turns on by itself: $500 an ounce to dig it out against $350 an ounce to
sell it.
"""

from __future__ import annotations

import re

# Multiplier words that appear inside a value string rather than as a unit.
SCALES = {
    "thousand": 1_000.0,
    "lakh": 100_000.0,
    "million": 1_000_000.0,
    "crore": 10_000_000.0,
    "billion": 1_000_000_000.0,
}

# Currency symbols read as part of the unit, so dollars and rupees do not end
# up on one axis.
CURRENCY = {"$": "usd", "₹": "inr", "€": "eur", "£": "gbp"}

_NUMBER = re.compile(r"([₹$€£]?)\s*(\d[\d,]*(?:\.\d+)?)")
_WORD = re.compile(r"[a-z/]+")

# Words that follow a number without being its unit.
NOT_A_UNIT = {
    "of", "in", "the", "a", "an", "and", "or", "at", "to", "per", "approx",
    "about", "around", "over", "under", "each", "every", "from",
    # Adjectives that sit between the number and its actual unit.
    "metric", "troy", "total", "annual", "average", "estimated", "roughly",
    "nearly", "approximately", "short", "long",
}

# How far apart two figures may be and still make a chart. Beyond this the
# smaller bar is a line of pixels, and - more to the point - quantities this
# different are usually not the same kind of thing wearing the same unit: a
# run returns 45 tonnes of gold and 200,000 tonnes of ore, which share "tonnes"
# and belong nowhere near the same axis.
MAX_RATIO = 100.0


def parse_value(text: str) -> tuple[float, str] | None:
    """The first figure in a value string, as (amount, unit).

    Handles the shapes research actually returns: "≈ 45 metric tonnes",
    "3,200 m (≈ 10,500 ft)", "$500 USD / oz", "≈ 0.2 million tonnes of ore".
    Only the first figure is read - the ones in brackets after it are the same
    quantity said again in another unit, and charting both would double it.
    """
    text = (text or "").strip()
    match = _NUMBER.search(text)
    if not match:
        return None

    symbol, digits = match.groups()
    try:
        amount = float(digits.replace(",", ""))
    except ValueError:
        return None

    tail = text[match.end():].lower()
    words = [word for word in _WORD.findall(tail) if word not in NOT_A_UNIT]

    if words and words[0] in SCALES:
        amount *= SCALES[words[0]]
        words = words[1:]

    if symbol:
        unit = CURRENCY.get(symbol, symbol)
        # "$500 USD / oz" - the currency is already known, so what matters is
        # what it is per.
        if "oz" in words:
            unit += "/oz"
        elif "tonne" in words or "tonnes" in words:
            unit += "/tonne"
        return amount, unit

    return amount, (words[0].rstrip(".") if words else "")


def _label(entry: dict) -> str:
    return str(entry.get("metric") or "").strip()


def comparable(entries: list[dict], minimum: int = 2) -> list[tuple[str, float, str]]:
    """The largest group of figures that share a unit, or [] if none does.

    Returns nothing rather than something when the figures are not comparable.
    A chart of unrelated quantities looks authoritative and means nothing,
    which is worse than no chart.
    """
    groups: dict[str, list[tuple[str, float, str]]] = {}
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        parsed = parse_value(str(entry.get("value") or ""))
        label = _label(entry)
        if not parsed or not label:
            continue
        amount, unit = parsed
        if not unit:
            continue
        groups.setdefault(unit, []).append((label, amount, unit))

    usable = [group for group in groups.values() if _plottable(group, minimum)]
    if not usable:
        return []
    return max(usable, key=len)


def _plottable(group: list[tuple[str, float, str]], minimum: int) -> bool:
    """Whether these figures belong on one axis together."""
    if len(group) < minimum:
        return False
    amounts = [amount for _, amount, _ in group if amount > 0]
    if len(amounts) < minimum:
        return False
    return max(amounts) / min(amounts) <= MAX_RATIO


def headline(entries: list[dict]) -> dict | None:
    """The single figure worth a card when nothing is comparable.

    The largest number, which on this data is the one a viewer remembers - the
    depth, the tonnage, the headcount - rather than the first one the model
    happened to list.
    """
    scored = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        parsed = parse_value(str(entry.get("value") or ""))
        if parsed and _label(entry):
            scored.append((parsed[0], entry))
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------

# Horizontal bars, because the labels are sentences - "Projected annual gold
# yield from the remaining reserves" does not fit under a vertical bar at any
# readable size.
CARD_MARGIN = 0.06        # of the frame, on every side
BAR_HEIGHT = 0.075        # of the frame height
BAR_GAP = 0.035
TITLE_GAP = 0.05


def _font(size: int, text: str = ""):
    from PIL import ImageFont

    from render import fonts

    try:
        return ImageFont.truetype(fonts.resolve(text), size)
    except Exception:
        return ImageFont.load_default()


def _shorten(text: str, limit: int = 46) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _format(amount: float) -> str:
    if amount >= 1000:
        return f"{amount:,.0f}"
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:,.1f}"


def bar_chart(series, title: str, size, accent=(232, 133, 60), progress: float = 1.0):
    """A comparison of figures that share a unit, drawn at `progress` complete.

    Bars grow from nothing to their value, which is what makes a chart read as
    a finding arriving rather than as a slide being shown.
    """
    from PIL import Image, ImageDraw

    width, height = int(size[0]), int(size[1])
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not series:
        return card

    draw = ImageDraw.Draw(card)
    margin = int(width * CARD_MARGIN)

    title_size = max(16, int(height * 0.045))
    label_size = max(13, int(height * 0.032))
    bar_height = int(height * BAR_HEIGHT)
    gap = int(height * BAR_GAP)

    # Laid out before anything is drawn, so the panel is the height of what is
    # in it. Drawn at a fixed height it left two thirds of itself empty under
    # a two-bar chart, which reads as a slide someone forgot to finish.
    rows = len(series)
    content = rows * (label_size + int(height * 0.012) + bar_height) + max(0, rows - 1) * gap
    if title:
        content += title_size + int(height * TITLE_GAP)
    padding = int(height * 0.06)

    panel_height = min(height - 2 * margin, content + 2 * padding)
    panel_top = (height - panel_height) // 2
    panel = (margin, panel_top, width - margin, panel_top + panel_height)
    draw.rounded_rectangle(panel, radius=int(height * 0.03), fill=(12, 14, 18, 225))

    inner = margin + int(width * 0.035)
    top = panel_top + padding

    if title:
        draw.text((inner, top), _shorten(title, 60), font=_font(title_size, title), fill=(240, 240, 245, 255))
        top += title_size + int(height * TITLE_GAP)

    largest = max(amount for _, amount, _ in series) or 1.0
    bar_height = int(height * BAR_HEIGHT)
    gap = int(height * BAR_GAP)
    full_width = panel[2] - inner - int(width * 0.16)

    eased = max(0.0, min(1.0, progress))
    eased = 1.0 - (1.0 - eased) ** 3

    for label, amount, unit in series:
        draw.text((inner, top), _shorten(label), font=_font(label_size, label), fill=(196, 200, 210, 255))
        bar_top = top + label_size + int(height * 0.012)
        length = int(full_width * (amount / largest) * eased)
        if length > 2:
            draw.rounded_rectangle(
                (inner, bar_top, inner + length, bar_top + bar_height),
                radius=int(bar_height * 0.25),
                fill=(*accent, 255),
            )
        shown = _format(amount * eased)
        draw.text(
            (inner + length + int(width * 0.012), bar_top + bar_height * 0.15),
            f"{shown} {unit}".strip(),
            font=_font(label_size, unit),
            fill=(240, 240, 245, 255),
        )
        top = bar_top + bar_height + gap

    return card


def stat_card(metric: str, value: str, size, accent=(232, 133, 60), progress: float = 1.0):
    """One figure, large, for when nothing in the run is comparable."""
    from PIL import Image, ImageDraw

    width, height = int(size[0]), int(size[1])
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(card)

    margin = int(width * CARD_MARGIN)
    panel = (margin, int(height * 0.3), width - margin, int(height * 0.7))
    draw.rounded_rectangle(panel, radius=int(height * 0.03), fill=(12, 14, 18, 225))

    value_size = max(28, int(height * 0.14))
    metric_size = max(14, int(height * 0.038))
    inner = margin + int(width * 0.04)

    draw.text((inner, panel[1] + int(height * 0.05)), _shorten(str(value), 24),
              font=_font(value_size, str(value)), fill=(*accent, 255))
    draw.text((inner, panel[1] + int(height * 0.05) + value_size + int(height * 0.02)),
              _shorten(metric, 52), font=_font(metric_size, metric), fill=(212, 216, 224, 255))

    if progress < 1.0:
        card.putalpha(card.getchannel("A").point(lambda a: int(a * max(0.0, min(1.0, progress)))))
    return card
