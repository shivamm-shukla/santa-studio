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
        seen[url] = {"title": title, "url": url, "key_facts": facts}

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


def document(topic: str, research: Optional[dict], factcheck: Optional[dict]) -> str:
    """The full sourcing record, as markdown."""
    sources = collect(research)
    factcheck = factcheck or {}
    verified = [str(c).strip() for c in factcheck.get("verified_claims") or [] if str(c).strip()]
    flagged = [str(c).strip() for c in factcheck.get("flagged_claims") or [] if str(c).strip()]
    confidence = factcheck.get("confidence_scores") or {}

    out = [f"# Sources — {topic or 'Untitled'}", "", f"_Compiled {date.today().isoformat()}._", ""]

    if not sources:
        out += ["No citable sources were recorded for this video.", ""]
    else:
        out += [f"## The {len(sources)} sources this video is built on", ""]
        for index, source in enumerate(sources, start=1):
            out.append(f"{index}. **{source['title']}**")
            out.append(f"   {source['url']}")
            for fact in source["key_facts"]:
                out.append(f"   - {fact}")
            out.append("")

    if verified:
        out += ["## Claims that passed fact-checking", ""]
        for claim in verified:
            grade = confidence.get(claim)
            out.append(f"- {claim}" + (f" _({grade} confidence)_" if grade else ""))
        out.append("")

    if flagged:
        out += [
            "## Claims that did not, and were kept out of the script",
            "",
            "Recorded so the omission is visible rather than silent.",
            "",
        ]
        for claim in flagged:
            out.append(f"- {claim}")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def write_document(topic: str, research: Optional[dict], factcheck: Optional[dict]) -> str:
    """Writes the record beside the master file and returns its path."""
    path = os.path.join(str(paths.scoped_dir("output")), "sources.md")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(document(topic, research, factcheck))
    return path
