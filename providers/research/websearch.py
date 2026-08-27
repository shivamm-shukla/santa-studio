"""The open web, for research that has to go past what an index already has.

`grounding.py` asks three catalogues about a subject they have already
catalogued: an encyclopedia entry, a paper with a DOI, a wire story. A
documentary is not built out of those alone. The report someone published,
the archive page, the transcript, the trade body's own numbers - those are
found by searching the way a person searches, and then reading what comes
back.

DuckDuckGo's lite endpoint is what does the searching here, because it needs
no account, no card and no key, which is the bar every other index in this
project clears. It answers in HTML meant for a browser, so it is parsed
rather than decoded, and when that page changes shape this returns nothing
and the run narrows instead of ending.

Nothing here raises. A search that fails is a thinner brief, never a dead
run.
"""

from __future__ import annotations

import re
import threading
import time
from html import unescape
from html.parser import HTMLParser

import requests

# A browser string, because the lite endpoint answers a scripted-looking
# caller with an empty page rather than an error.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

ENDPOINT = "https://lite.duckduckgo.com/lite/"
TIMEOUT = 20

# Searches go out from the research swarm's worker threads, and a burst of
# them from one address is what gets an address blocked. One request at a
# time, spaced - the whole sweep costs a few seconds and keeps working.
MIN_INTERVAL = 1.5
_pace = threading.Lock()
_last_call = 0.0


def _throttled_post(data: dict):
    global _last_call
    with _pace:
        wait = MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            return requests.post(
                ENDPOINT, data=data, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT
            )
        finally:
            _last_call = time.monotonic()


class _Results(HTMLParser):
    """Pulls (link, title, snippet) out of the lite endpoint's table.

    The page is one long table: a row holding an anchor of class
    `result-link`, then a row holding a cell of class `result-snippet` for
    the same result. Tracking which of the two we are inside is the whole
    parser - there is no nesting to speak of, which is why the lite endpoint
    is worth using over the full one.
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._in_link = False
        self._in_snippet = False
        self._title: list[str] = []
        self._snippet: list[str] = []
        self._url = ""

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "a" and "result-link" in classes:
            self._flush()
            self._in_link = True
            self._url = attributes.get("href") or ""
        elif "result-snippet" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            self._in_link = False
        elif tag == "td" and self._in_snippet:
            self._in_snippet = False

    def handle_data(self, data):
        if self._in_link:
            self._title.append(data)
        elif self._in_snippet:
            self._snippet.append(data)

    def _flush(self):
        title = " ".join("".join(self._title).split())
        if title and self._url.startswith("http"):
            self.results.append({
                "title": title,
                "url": self._url,
                "summary": " ".join("".join(self._snippet).split()),
                "kind": "web",
            })
        self._title, self._snippet, self._url = [], [], ""

    def close(self):
        super().close()
        self._flush()


def search(query: str, limit: int = 10) -> list[dict]:
    """What the web returns for `query`, as sources in this project's shape."""
    if not query.strip():
        return []
    try:
        response = _throttled_post({"q": query})
        if response.status_code != 200:
            return []
        parser = _Results()
        parser.feed(response.text)
        parser.close()
    except Exception:
        return []
    return parser.results[:limit]


# ---------------------------------------------------------------------------
# Reading a page, once searching has found one worth reading
# ---------------------------------------------------------------------------

_TAGS_TO_DROP = re.compile(
    r"<(script|style|noscript|nav|footer|header|form|aside)\b.*?</\1>",
    re.IGNORECASE | re.DOTALL,
)
_TAG = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\n{3,}")

READ_TIMEOUT = 20
READABLE_TYPES = ("text/html", "text/plain", "application/xhtml")


def read(url: str, limit: int = 6000) -> str:
    """The readable text of a page, or "" if there is none to be had.

    A title and a two-line snippet is enough to decide whether a source is
    worth citing and nowhere near enough to write from - a brief built out of
    search snippets is a brief built out of what a search engine chose to
    show, which is not the same thing as what the source says. This is how a
    claim in the script can come from the page rather than from the summary
    of it.

    Deliberately crude: tags out, whitespace collapsed, truncated. A parsing
    library would read more cleanly and is not worth a dependency for text
    that an LLM is about to read anyway.
    """
    try:
        response = requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=READ_TIMEOUT, stream=True
        )
        if response.status_code != 200:
            return ""
        content_type = (response.headers.get("Content-Type") or "").lower()
        if not any(kind in content_type for kind in READABLE_TYPES):
            return ""
        # Enough of the page to hold the argument, without pulling a whole
        # book down a connection this run is timing.
        raw = response.raw.read(400_000, decode_content=True) or b""
        html = raw.decode(response.encoding or "utf-8", errors="replace")
    except Exception:
        return ""
    finally:
        try:
            response.close()
        except Exception:
            pass

    text = _TAGS_TO_DROP.sub(" ", html)
    text = _TAG.sub("\n", text)
    text = unescape(text)
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    text = _BLANK_LINES.sub("\n\n", text)
    return text[:limit]
