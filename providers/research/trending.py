"""What people are actually reading, for a channel choosing what to make next.

`topic_agent` asks an LLM to invent three topics for a niche. That is a guess
dressed as research: the model has no idea what anyone is searching for, and
its three suggestions are the three a language model finds plausible, which is
a different thing from the three a viewer wants.

Wikipedia publishes readership, keyless and free, and it is the closest thing
to a public record of what people are curious about this week. Two endpoints
between them answer the question:

* **Search** finds the articles that exist about a niche at all.
* **Per-article pageviews** say how much each one is read, and - more usefully -
  whether it is read *more than usual* right now.

Ranking on momentum alone would be a mistake: an article that went from one
reader to two is up a hundred per cent and is not a story. So an article has
to clear a floor of real readership before its trend counts for anything, and
the score is interest and momentum together.

Everything returns [] rather than raising, like `grounding`. Not knowing what
is trending should narrow the choice, not end the run.
"""

from __future__ import annotations

import math
import urllib.parse
from datetime import date, timedelta

import requests

USER_AGENT = "SantaStudio/1.0 (contact@santastudio.dev)"
SEARCH_API = "https://{project}.org/w/api.php"
VIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"

TIMEOUT = 20

# Pageview data lags a day or two, so today's date returns nothing.
LAG_DAYS = 2
WINDOW_DAYS = 30
RECENT_DAYS = 7

# Below this a "rising" article is noise: one reader becoming two is up a
# hundred per cent and is not a story.
MIN_DAILY_VIEWS = 25

# Namespaces and housekeeping pages that are read constantly and are not
# subjects. Matched on the title, which is what search returns.
NOT_A_SUBJECT = (
    "main page", "special:", "wikipedia:", "portal:", "category:", "template:",
    "help:", "talk:", "file:", "deaths in", "list of", "index of", "timeline of",
    "(disambiguation)",
)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return session


def is_a_subject(title: str) -> bool:
    """Whether this is an article about something, rather than scaffolding."""
    lowered = (title or "").strip().lower()
    if not lowered:
        return False
    return not any(marker in lowered for marker in NOT_A_SUBJECT)


def search(niche: str, limit: int = 10, project: str = "en.wikipedia") -> list[str]:
    """Article titles that exist about this niche."""
    try:
        response = _session().get(
            SEARCH_API.format(project=project),
            params={
                "action": "query", "list": "search", "srsearch": niche,
                "srlimit": limit, "format": "json",
            },
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        hits = ((response.json().get("query") or {}).get("search")) or []
    except Exception:
        return []

    return [str(hit.get("title") or "") for hit in hits if is_a_subject(str(hit.get("title") or ""))]


def views(title: str, project: str = "en.wikipedia", session=None) -> list[int]:
    """Daily readership for one article over the measuring window."""
    end = date.today() - timedelta(days=LAG_DAYS)
    start = end - timedelta(days=WINDOW_DAYS)
    encoded = urllib.parse.quote(str(title).replace(" ", "_"), safe="")

    try:
        response = (session or _session()).get(
            f"{VIEWS_API}/{project}/all-access/user/{encoded}/daily/"
            f"{start:%Y%m%d}/{end:%Y%m%d}",
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return []
        return [int(item.get("views") or 0) for item in response.json().get("items") or []]
    except Exception:
        return []


def _measure(daily: list[int]) -> tuple[float, float] | None:
    """(readership, momentum) for one article, or None if there is too little."""
    if len(daily) < RECENT_DAYS * 2:
        return None

    recent = sum(daily[-RECENT_DAYS:]) / RECENT_DAYS
    earlier = daily[:-RECENT_DAYS]
    baseline = sum(earlier) / len(earlier)

    if recent < MIN_DAILY_VIEWS:
        return None
    return recent, (recent / baseline if baseline else 1.0)


def candidates(niche: str, limit: int = 5, project: str = "en.wikipedia") -> list[dict]:
    """Articles about this niche that people are reading, most promising first.

    Scored on readership and momentum together. Readership goes in as a
    logarithm, because the difference between fifty readers a day and five
    hundred matters and the difference between fifty thousand and five hundred
    thousand does not - past a point it is simply a famous subject, and a
    famous subject is not the same as a timely one.
    """
    session = _session()
    found = []

    for title in search(niche, limit=max(limit * 2, 8), project=project):
        measured = _measure(views(title, project=project, session=session))
        if not measured:
            continue
        readership, momentum = measured
        found.append({
            "title": title,
            "daily_views": round(readership),
            "momentum": round(momentum, 2),
            "score": round(momentum * math.log10(max(readership, 10)), 3),
        })

    found.sort(key=lambda item: item["score"], reverse=True)
    return found[:limit]
