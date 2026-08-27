"""The sources behind a video, as a deliverable rather than an internal note.

These videos take positions on things people argue about, so "trust us" is
not an available answer. Two things come out of here:

* a **description block** - a numbered, clickable list that ships in the
  YouTube description, because a link a viewer cannot click is not a citation;
* a **sources document** - the full record written next to the master file:
  every source, the claims drawn from it, and, separately, the claims that did
  not survive fact-checking.

The flagged claims are in the document on purpose. A viewer who wants to know
what we decided *not* to say is exactly the viewer worth keeping.
"""

from __future__ import annotations

import os
import re
from datetime import date
from typing import Optional

import paths

# YouTube allows 5000 characters of description. The drafted copy comes first
# and the sources follow it, so the block gets a budget rather than the lot.
DESCRIPTION_LIMIT = 5000
SOURCES_BUDGET = 2500


def collect(research: Optional[dict]) -> list[dict]:
    """Citable sources, in citation order, one entry per URL.

    A source with no URL cannot be checked by anybody, so it is not a source
    for this purpose however good its facts are.
    """
    seen: dict[str, dict] = {}
    for source in (research or {}).get("sources") or []:
        # An entry is usually {title, url, key_facts}, but a bare URL string
        # turns up too - from a research provider that had nothing else to
        # say about it. A link on its own is still a link a viewer can check.
        if isinstance(source, str):
            source = {"url": source}
        elif not isinstance(source, dict):
            continue

        url = str(source.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        title = str(source.get("title") or url).strip()
        facts = [str(f).strip() for f in source.get("key_facts") or [] if str(f).strip()]

        if url in seen:
            for fact in facts:
                if fact not in seen[url]["key_facts"]:
                    seen[url]["key_facts"].append(fact)
            continue
        # What a paper is - its journal and year - rather than what it claims.
        # It belongs on the citation and not in front of the fact-checker.
        seen[url] = {
            "title": title,
            "url": url,
            "key_facts": facts,
            "note": str(source.get("note") or "").strip(),
        }

    return list(seen.values())


def description_block(sources: list[dict], budget: int = SOURCES_BUDGET) -> str:
    """The numbered list that goes in the description, inside `budget` chars.

    Truncating mid-list is fine; truncating mid-URL is not, so entries are
    added whole or not at all.
    """
    if not sources:
        return ""

    header = "Sources"
    lines: list[str] = []
    used = len(header) + 1

    for index, source in enumerate(sources, start=1):
        entry = f"{index}. {source['title']}\n{source['url']}"
        if used + len(entry) + 1 > budget:
            break
        lines.append(entry)
        used += len(entry) + 1

    if not lines:
        return ""
    return header + "\n" + "\n".join(lines)


def with_sources(description: str, research: Optional[dict]) -> str:
    """`description` with the sources appended, inside YouTube's own limit."""
    block = description_block(collect(research))
    if not block:
        return description[:DESCRIPTION_LIMIT]

    body = (description or "").rstrip()
    room = DESCRIPTION_LIMIT - len(block) - 2
    if room < 0:
        return block[:DESCRIPTION_LIMIT]
    return (body[:room].rstrip() + "\n\n" + block) if body else block


_FIGURE = re.compile(r"\d[\d,.]*")

# Below this, a lone shared number is a coincidence rather than a citation:
# two sentences about the same video both saying "three" prove nothing, while
# both saying "1967" or "5.86" are almost certainly the same claim.
_DISTINCTIVE = 1000


def figures(text: str) -> set[str]:
    """The numbers in `text`, normalised enough to compare across languages.

    A claim and the narration carrying it are rarely the same words - the
    script is written in Hinglish and the claim is in English - but a figure
    survives translation intact. $5.86 a ton is $5.86 a ton either way. The
    numbers are what make it possible to ask whether a claim reached the
    script at all.
    """
    found = set()
    for match in _FIGURE.findall(text or ""):
        cleaned = match.replace(",", "").strip(".")
        if cleaned:
            found.add(cleaned)
    return found


def reached_the_script(claim: str, script_text: str) -> bool:
    """Whether the script appears to be stating `claim`.

    A heuristic, and named as one. Two shared figures is the bar, or one that
    is precise enough to stand alone. A claim carrying no figures cannot be
    traced this way and is never reported, which is the cautious direction to
    be wrong in: this exists to stop the document asserting an omission that
    did not happen, so accusing the script falsely would be the worse error.
    """
    shared = figures(claim) & figures(script_text)
    if len(shared) >= 2:
        return True
    return any(
        value.replace(".", "").isdigit()
        and (float(value) >= _DISTINCTIVE or "." in value)
        for value in shared
    )


def _script_text(script) -> str:
    """The narration out of whatever the caller had to hand."""
    if isinstance(script, str):
        return script
    if isinstance(script, dict):
        return " ".join(
            str(script.get(key) or "") for key in ("script_text", "script_spoken")
        )
    return ""


def document(
    topic: str,
    research: Optional[dict],
    factcheck: Optional[dict],
    script=None,
) -> str:
    """The full sourcing record, as markdown.

    `script` is optional because the record is first written at fact-checking
    time, when there is no script yet - a run that dies before it has one
    still owes its sources. Given a script, the claim that the flagged
    material was kept out of it is checked rather than asserted.
    """
    sources = collect(research)
    factcheck = factcheck or {}
    verified = [str(c).strip() for c in factcheck.get("verified_claims") or [] if str(c).strip()]
    flagged = [str(c).strip() for c in factcheck.get("flagged_claims") or [] if str(c).strip()]
    confidence = factcheck.get("confidence_scores") or {}

    narration = _script_text(script)
    stated = [c for c in flagged if narration and reached_the_script(c, narration)]
    kept_out = [c for c in flagged if c not in stated]

    out = [f"# Sources — {topic or 'Untitled'}", "", f"_Compiled {date.today().isoformat()}._", ""]

    if not sources:
        out += ["No citable sources were recorded for this video.", ""]
    else:
        out += [f"## The {len(sources)} sources this video is built on", ""]
        for index, source in enumerate(sources, start=1):
            out.append(f"{index}. **{source['title']}**")
            out.append(f"   {source['url']}")
            if source.get("note"):
                out.append(f"   _{source['note']}_")
            for fact in source["key_facts"]:
                out.append(f"   - {fact}")
            out.append("")

    if verified:
        out += ["## Claims that passed fact-checking", ""]
        for claim in verified:
            grade = confidence.get(claim)
            out.append(f"- {claim}" + (f" _({grade} confidence)_" if grade else ""))
        out.append("")

    if kept_out:
        out += [
            (
                "## Claims that did not, and were kept out of the script"
                if narration
                else "## Claims that did not pass fact-checking"
            ),
            "",
            (
                "Recorded so the omission is visible rather than silent. "
                "Checked against the narration that shipped."
                if narration
                else "Recorded so the omission is visible rather than silent. "
                     "None of these is available to the script."
            ),
            "",
        ]
        for claim in kept_out:
            out.append(f"- {claim}")
        out.append("")

    # Figures the writer put in after three drafts of being told not to. The
    # video ships with them because it is worth more than they cost, and this
    # is the price of that: they are named, so nobody mistakes them for
    # something a source said.
    invented = []
    if isinstance(script, dict):
        invented = [str(f) for f in script.get("unsupported_figures") or []]
    if invented:
        out += [
            "## Figures in the narration that no source carries",
            "",
            "Stated in the video, supported by nothing here. Read them as the "
            "narrator's, not as the record's.",
            "",
            "- " + ", ".join(invented),
            "",
        ]

    # Printed rather than quietly dropped. A sourcing document that hides its
    # own failure is worth less than no document: the whole promise here is
    # that what we would rather not admit is admitted anyway.
    if stated:
        out += [
            "## Flagged claims the script stated anyway",
            "",
            "These did not pass fact-checking and the narration carries them "
            "regardless. Treat them as unsourced.",
            "",
        ]
        for claim in stated:
            out.append(f"- {claim}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def write_document(
    topic: str,
    research: Optional[dict],
    factcheck: Optional[dict],
    script=None,
) -> str:
    """Writes the record beside the master file and returns its path."""
    path = os.path.join(str(paths.scoped_dir("output")), "sources.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document(topic, research, factcheck, script))
    return path
