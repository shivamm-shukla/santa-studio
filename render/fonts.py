"""Picking a font file that can actually draw the text it is given.

The studio's default output language is Hinglish, and the same run can put
Latin text on screen while another caption is in Devanagari. A font without the
glyphs does not raise - it draws tofu boxes, and the failure only surfaces in
the finished video. That is exactly what happened the first time captions were
rendered here.

Two things matter and both are easy to get wrong:

* The drawing backend wants a **file path**, not a family name. Pillow's
  `truetype("Noto Sans Devanagari", ...)` raises OSError; it needs
  `/usr/share/fonts/.../NotoSansDevanagari-Regular.ttf`.
* `fc-match` always returns something. Asking it for a font that is not
  installed hands back the system default, which is how you end up confidently
  passing a Latin-only font to Devanagari text.

So candidates are checked against fontconfig's own language database, which is
built for precisely this question, and the chosen file is opened before it is
returned.

No font is bundled. Shipping one would mean auditing its licence for
commercial redistribution, and every platform this runs on already has
something workable.
"""

from __future__ import annotations

import functools
import os
import subprocess

# Ordered by preference. Noto leads because it has the widest coverage and is
# packaged nearly everywhere.
LATIN_CANDIDATES = (
    "Noto Sans",
    "DejaVu Sans",
    "Liberation Sans",
    "FreeSans",
    "Arial",
    "Helvetica",
)

DEVANAGARI_CANDIDATES = (
    "Noto Sans Devanagari",
    "Noto Serif Devanagari",
    "Lohit Devanagari",
    "Samyak Devanagari",
    "FreeSans",
    "Mangal",
)

# fontconfig language tags for the scripts we care about.
DEVANAGARI_LANG = "hi"
LATIN_LANG = "en"


def has_devanagari(text: str) -> bool:
    """True if any character needs a Devanagari-capable font.

    Covers the main block plus Vedic extensions, which is what turns up in
    Hindi script output.
    """
    return any("ऀ" <= ch <= "ॿ" or "᳐" <= ch <= "᳿" for ch in text)


def _run_fc(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


# fc-list emits every style of a family in no useful order, so the first hit
# for "Noto Sans" is as likely to be BoldItalic as Regular - which is how
# captions ended up in bold italic the first time round. Lower score wins.
_STYLE_PENALTY = {
    "regular": 0,
    "book": 0,
    "normal": 0,
    "medium": 2,
    "light": 3,
    "semibold": 4,
    "bold": 5,
    "italic": 6,
    "oblique": 6,
    "thin": 7,
    "black": 7,
    "condensed": 8,
    "extra": 8,
}


def _style_score(style: str) -> int:
    """How far a style is from the plain upright cut of its family."""
    lowered = style.strip().lower()
    if not lowered or lowered in ("regular", "book", "normal"):
        return 0
    return sum(penalty for token, penalty in _STYLE_PENALTY.items() if token in lowered) or 1


@functools.lru_cache(maxsize=8)
def _families_for_language(lang: str) -> dict[str, str]:
    """Maps family name (lowercased) -> font file, for fonts covering `lang`.

    Built from `fc-list :lang=<lang>`, so a font only appears here if
    fontconfig believes it can render that language. That is the check that
    stops a Latin-only font being handed Devanagari text.
    """
    output = _run_fc(["fc-list", f":lang={lang}", "file", "family", "style"])
    best: dict[str, tuple[int, str]] = {}
    for line in output.splitlines():
        path, _, rest = line.partition(":")
        path = path.strip()
        if not path:
            continue
        families, _, style = rest.partition(":style=")
        score = _style_score(style)
        for alias in families.split(","):
            alias = alias.strip().lower()
            if not alias:
                continue
            if alias not in best or score < best[alias][0]:
                best[alias] = (score, path)
    return {alias: path for alias, (_, path) in best.items()}


def _usable(path: str) -> bool:
    """Whether the drawing backend can actually open this file."""
    if not path or not os.path.exists(path):
        return False
    try:
        from PIL import ImageFont

        ImageFont.truetype(path, 24)
        return True
    except Exception:
        return False


@functools.lru_cache(maxsize=64)
def _resolve_cached(needs_devanagari: bool, preferred: str) -> str | None:
    lang = DEVANAGARI_LANG if needs_devanagari else LATIN_LANG
    available = _families_for_language(lang)
    if not available:
        return None  # no fontconfig; let the drawing library choose

    candidates = list(DEVANAGARI_CANDIDATES if needs_devanagari else LATIN_CANDIDATES)
    if preferred:
        candidates.insert(0, preferred)

    for family in candidates:
        path = available.get(family.lower())
        if path and _usable(path):
            return path

    # Nothing preferred is installed, but something covers the language.
    for path in available.values():
        if _usable(path):
            return path
    return None


def resolve(text: str = "", preferred: str = "") -> str | None:
    """Path to the best available font file for `text`, or None.

    None rather than a guess: the drawing library's own default is a reasonable
    fallback, and naming a font that cannot be opened fails harder than not
    naming one.
    """
    return _resolve_cached(has_devanagari(text), preferred or "")


def describe() -> dict:
    """What the doctor check reports."""
    latin = resolve("Latin sample")
    devanagari = resolve("नमस्ते")
    return {
        "fontconfig_available": bool(_families_for_language(LATIN_LANG)),
        "latin": latin,
        "devanagari": devanagari,
        "can_render_hindi": bool(devanagari),
    }
