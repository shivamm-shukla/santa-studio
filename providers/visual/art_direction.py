"""The camera brief behind a generated still.

A hint from the script is a subject, not a photograph. "Mine headframe" leaves
every decision that makes a picture look taken rather than rendered up to the
model, and left to itself the model makes the same six decisions every time:
the subject centred, the sun low behind it, the sky orange, everything sharp,
nothing in the foreground. Put twenty of those in one video and the video
announces what made it, no matter how good any single frame is.

So the brief is written here instead. Each still is given a film stock, a
lens and aperture, a light, a place to sit in the frame, something to sit
behind, and a flaw. Measured against the previous prompt on the same subject,
naming those lifted edge detail two to three times over - the model has the
detail, it just will not spend it unless the prompt implies a camera.

Two rules the vocabularies below encode, both learned by generating against
them:

* **No golden hour.** A low sun behind the subject is the single loudest tell,
  and it is what the model reaches for unprompted. The lights here are dull,
  flat, overcast, fluorescent, sodium - the light most photographs are
  actually taken in.
* **No second object.** An early brief asked for "a parked truck at the left
  edge for scale" and got a photograph of a truck. Anything named in a prompt
  competes to be the subject, so the variation is in how the subject is shot,
  never in what else is in the shot.

Selection is deterministic on the subject and a variation index, so the same
scene regenerates identically - the cache depends on it - while consecutive
shots in one video draw different cameras.
"""

from __future__ import annotations

import hashlib
import re

# Stock before camera, because the stock decides the colour and the grain and
# those read before anything else does.
# No stock is named, and that is the third rule learned by generating against
# it. Naming a medium - "35mm colour negative", "shot on Ektachrome" - kept
# returning a photograph *of* that medium: a print with a paper margin, a
# slide in its mount, a black frame line around the picture. Rephrasing it
# from a noun to "shot on" reduced it and did not stop it, because the brand
# is the part the model is matching on. So the look is described and the
# medium never mentioned, which removes the whole class of failure rather
# than arguing with it.
COLOUR_LOOK = (
    "fine grain, muted natural colour, warmth in the shadows",
    "soft grain, faded colour, low saturation",
    "a green cast through the midtones, grain visible in the flat areas",
    "cool colour, dense blacks, fine grain",
    "clean neutral colour, ungraded, very fine detail",
)

MONOCHROME_LOOK = (
    "black and white, coarse grain, deep blacks",
    "black and white, high contrast, grain visible in the sky",
)

# Colour outweighs monochrome three to one rather than being picked evenly.
# Even, black and white came up in a quarter of all shots, and a documentary
# that keeps dropping into monochrome for no reason looks stylised - which is
# a different way of looking made rather than taken. Monochrome stays in
# because for a genuinely archival subject it is the right answer.
MEDIUM = COLOUR_LOOK * 3 + MONOCHROME_LOOK

LENS = (
    "24mm at f/8, deep focus, mild wide-angle stretch at the edges",
    "28mm at f/8, everything from the foreground back in focus",
    "35mm at f/5.6",
    "50mm at f/4, background falling gently out of focus",
    "85mm at f/2.8, perspective compressed",
    "135mm telephoto, flattened planes, shallow depth",
)

# Deliberately no sunset, no golden hour, no rim light. See the module note.
#
# Every one of these is outdoor daylight, and that is the second rule the hard
# way. Interior fluorescent and sodium street light were in here, and asked
# for an outdoor subject under one of them the model moved the subject
# indoors: a brief for a mine headframe came back as a lit tunnel. A light
# that dictates a place overrides the subject, and the subject is the part
# that has to be right.
LIGHT = (
    "flat overcast midday light, no visible shadows",
    "hazy afternoon light through dust, low contrast",
    "high midday sun, short hard shadows, the sun itself out of frame",
    "thin grey winter light, everything desaturated",
    "dull light under rain cloud, wet surfaces, muted colour",
    "bright but sunless white sky, even light from every direction",
    "open shade, cool blue light bouncing in from the sky",
)

# Nothing here makes the subject small. A framing that did - "the subject
# small and low in the frame under a large sky" - came back as a landscape
# with a shed in it, which is a good photograph of the wrong thing. Variety
# is worth having right up to the point where it costs the subject.
FRAMING = (
    "the subject sitting on the right third of the frame, space to its left",
    "the subject on the left third, the frame open to the right",
    "a tight three-quarter view, the subject filling most of the frame",
    "eye level, square to the subject, plain and frontal",
    "shot from low, close to the ground, the subject rising above the lens",
    "shot from higher ground, looking slightly down across the subject",
    "close in on the subject, its edges running out of the frame",
)

FOREGROUND = (
    "a wall edge intruding at the near left, well out of focus",
    "weeds and gravel across the bottom of the frame",
    "nothing between the camera and the subject",
    "a wire fence immediately in front of the lens, defocused to a haze",
    "the ground running away from the lens in the lower quarter of the frame",
    "nothing between the camera and the subject",
)

# What a real frame has and a generated one does not: a mistake.
IMPERFECTION = (
    "slightly underexposed, detail held in the highlights",
    "the horizon a degree off level",
    "grain clearly visible in the shadows",
    "a few specks of dust and a fine scratch",
    "slightly over-exposed, the sky washed out to paper white",
    "a soft corner where the lens falls off",
)

# Everything the model adds when nobody stops it. "No AI" is not in here on
# purpose: naming it does nothing, and naming the specific looks does.
NEGATIVE = (
    "no text, no caption, no watermark, no logo, no signature, "
    "full bleed to the edge of the frame, no print border, no white margin, "
    "no film frame, no sprocket holes, no scan edge, no rounded corners, "
    "no letterbox bars, no collage or split frame, "
    "not an illustration, not a 3D render, not concept art, not a matte painting, "
    "no HDR glow, no bloom, no orange and teal grade, no sunset, "
    "no sun in the picture, no lens flare star, "
    "the photograph fills the whole image"
)

BRIEF = (
    "{medium}, {lens}. {framing}: {subject}. {light}. {foreground}. "
    "Authentic materials, real surface wear, dirt and repair where things are used. "
    "{imperfection}. {negative}"
)


def _pick(options: tuple[str, ...], subject: str, variation: int, salt: str) -> str:
    """One option, chosen deterministically but unpredictably.

    Hashed rather than taken modulo the index so that two shots one apart do
    not walk the vocabularies in lockstep - which would give every video the
    same *sequence* of looks, having only just fixed every video having the
    same look.
    """
    digest = hashlib.sha256(f"{salt}:{subject}:{variation}".encode("utf-8")).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]


def brief(subject: str, variation: int = 0) -> str:
    """A camera brief for `subject`, in the `variation`-th way of shooting it.

    Callers pass the scene index as the variation, which is what keeps a
    video's generated stills from sharing one light and one framing.
    """
    subject = (subject or "").strip().rstrip(".")
    if not subject:
        return ""

    return BRIEF.format(
        subject=subject,
        medium=_pick(MEDIUM, subject, variation, "medium"),
        lens=_pick(LENS, subject, variation, "lens"),
        light=_pick(LIGHT, subject, variation, "light"),
        framing=_pick(FRAMING, subject, variation, "framing"),
        foreground=_pick(FOREGROUND, subject, variation, "foreground"),
        imperfection=_pick(IMPERFECTION, subject, variation, "imperfection"),
        negative=NEGATIVE,
    )


# Subjects that cannot be photographed into existence without inventing a
# document. Asked for "official closure notice BGML 2001 Kolar gold fields"
# the generator produced a sign reading OFFICIALT NOTICE / CLOSED / LLGML 2001
# / "Postent, Incilled the be folwner vairy hears"; asked for "chart gold
# production 1910s Kolar peak 1919" it produced a table of invented figures -
# 1905 CIL, 1903 LIL, POLAL - about a real company and a real closure.
#
# The garbled lettering is the smaller half of the problem. The larger half is
# that a fabricated official record cut into a documentary is presented to the
# viewer as evidence, in a video whose whole claim is that its sources can be
# checked. No prompt fixes that, because the subject *is* the document.
#
# So these are refused outright. The right answer for them is a graphic built
# from a researched figure - which is a real feature this project does not
# have yet - and until it exists, nothing is better than something invented.
TEXT_ARTEFACTS = (
    "notice", "sign", "signage", "signboard", "billboard", "poster", "banner",
    "placard", "plaque", "document", "paper", "papers", "paperwork", "letter",
    "memo", "telegram", "certificate", "licence", "license", "permit", "form",
    "receipt", "invoice", "ledger", "register", "report", "newspaper", "press",
    "headline", "article", "clipping", "chart", "graph", "table", "diagram",
    "infographic", "blueprint", "schematic", "map", "timeline", "screenshot",
    "spreadsheet", "statistics", "figures",
)

_WORD = re.compile(r"[a-z]+")


def refuses(subject: str) -> str:
    """Why this subject must not be generated, or "" if it may be.

    Matching on whole words: a hint about a mine "sign" is refused, one about
    "designing" is not.
    """
    words = set(_WORD.findall((subject or "").lower()))
    named = sorted(words & set(TEXT_ARTEFACTS))
    if not named:
        return ""
    return (
        f"generating a {named[0]} would mean inventing a document; "
        "a real graphic belongs here instead"
    )


def without_artefacts(subject: str) -> str:
    """The same subject with the document words taken out.

    "Official closure notice BGML 2001 Kolar gold fields" becomes "official
    closure BGML 2001 Kolar gold fields" - the place and the event, without the
    piece of paper. That is a shot the generator can make honestly: a closed
    mine gate rather than an invented notice nailed to it.

    Deliberately a deletion and not a rewrite. Anything cleverer would be this
    module inventing what the scene is about, which is the failure it is here
    to prevent.
    """
    kept = [
        word for word in (subject or "").split()
        if _WORD.sub("", word.lower()) or _WORD.findall(word.lower())
        if not set(_WORD.findall(word.lower())) & set(TEXT_ARTEFACTS)
    ]
    return " ".join(kept).strip()
