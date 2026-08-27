"""Real sources for a topic, from the catalogues that need no key.

Wikipedia alone is thin for the subjects this channel takes on. A claim about
a mine closing needs the encyclopedia for the shape of the story, the academic
record for whether anyone measured it, and the news record for who argued
about it at the time. None of these needs an account:

* **Wikipedia** - the shape of the subject. Searched from
  agents/research_agent.py, which owns the queries.
* **OpenAlex** - the academic record, with DOIs. A DOI is the strongest
  citation this project can offer a viewer.
* **GDELT** - news coverage, which is where a contested subject shows its
  disagreement. Rate-limited by the service itself, so it is asked once per
  query and never in a loop.

The open web is the fourth, and it lives in websearch.py because searching it
is a different job: these three answer questions about things they have
already catalogued, and most of what a documentary stands on was never
catalogued by anyone.

Everything here returns [] rather than raising. Grounding that fails should
narrow the brief, not end the run.
"""

from __future__ import annotations

import requests

USER_AGENT = "SantaStudio/1.0 (contact@santastudio.dev)"
CONTACT = "contact@santastudio.dev"

OPENALEX_TIMEOUT = 15
GDELT_TIMEOUT = 20


def academic(topic: str, limit: int = 4) -> list[dict]:
    """Peer-reviewed work on the topic, newest and most cited first.

    The DOI is preferred over OpenAlex's own landing page: it is the citation
    a reader can check anywhere, and it does not depend on us.
    """
    try:
        response = requests.get(
            "https://api.openalex.org/works",
            params={
                "search": topic,
                "per-page": limit,
                "sort": "relevance_score:desc",
                # OpenAlex asks callers to identify themselves for the faster
                # pool; it is a courtesy that costs nothing and is honoured.
                "mailto": CONTACT,
            },
            headers={"User-Agent": USER_AGENT},
            timeout=OPENALEX_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("results") or []
    except Exception:
        return []

    sources = []
    for work in results:
        title = (work.get("display_name") or "").strip()
        url = (work.get("doi") or "").strip() or (work.get("id") or "").strip()
        if not title or not url.startswith("http"):
            continue

        year = work.get("publication_year")
        venue = (
            ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
            or ""
        )
        cited = work.get("cited_by_count")

        detail = ", ".join(
            part for part in (venue, str(year) if year else "", f"cited {cited} times" if cited else "")
            if part
        )
        sources.append({
            "title": title,
            "url": url,
            "summary": detail or "Peer-reviewed work on this subject.",
            "kind": "academic",
        })
    return sources


def news(topic: str, limit: int = 5) -> list[dict]:
    """Contemporary coverage, which is where a contested subject disagrees."""
    try:
        response = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": topic,
                "mode": "artlist",
                "maxrecords": limit,
                "format": "json",
                "sort": "hybridrel",
            },
            headers={"User-Agent": USER_AGENT},
            timeout=GDELT_TIMEOUT,
        )
        # GDELT answers a rate-limited caller with a 429 and plain text, so a
        # bad status has to be checked before the body is treated as JSON.
        if response.status_code != 200:
            return []
        articles = response.json().get("articles") or []
    except Exception:
        return []

    sources = []
    for article in articles:
        title = (article.get("title") or "").strip()
        url = (article.get("url") or "").strip()
        if not title or not url.startswith("http"):
            continue
        seen = (article.get("seendate") or "")[:8]
        domain = article.get("domain") or ""
        sources.append({
            "title": title,
            "url": url,
            "summary": ", ".join(p for p in (domain, seen) if p) or "Contemporary coverage.",
            "kind": "news",
        })
    return sources


def merge(*groups: list[dict]) -> list[dict]:
    """One list, one entry per URL, in the order the groups were given."""
    seen: set[str] = set()
    merged: list[dict] = []
    for group in groups:
        for source in group or []:
            url = (source.get("url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(source)
    return merged
