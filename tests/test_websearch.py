"""Searching the open web, and reading what it returns.

The catalogues in grounding.py answer questions about subjects they have
already catalogued. Most of what a documentary stands on was never
catalogued - the report, the archive page, the trade body's own figures - so
there has to be a way to search the way a person does.

The endpoint answers in HTML meant for a browser, which means this is a
parser, and a parser against somebody else's markup is the thing most likely
to quietly start returning nothing. So the markup is pinned here, and so is
the promise that a failure narrows a brief rather than ending a run.
"""

from providers.research import websearch


class _Response:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


LITE_PAGE = """
<table border="0">
  <tr>
    <td valign="top">1.&nbsp;</td>
    <td><a rel="nofollow" href="https://en.wikipedia.org/wiki/Containerization"
       class='result-link'>Containerization - Wikipedia</a></td>
  </tr>
  <tr>
    <td>&nbsp;</td>
    <td class='result-snippet'>
      <b>Containerization</b> dramatically reduced the costs of transport.
    </td>
  </tr>
  <tr>
    <td valign="top">2.&nbsp;</td>
    <td><a rel="nofollow" href="https://example.org/the-box"
       class='result-link'>The Box, reviewed</a></td>
  </tr>
  <tr>
    <td>&nbsp;</td>
    <td class='result-snippet'>Marc Levinson&#x27;s history of the container.</td>
  </tr>
</table>
"""


def test_a_result_carries_its_title_link_and_snippet(monkeypatch):
    monkeypatch.setattr(websearch, "_throttled_post", lambda data: _Response(LITE_PAGE))

    results = websearch.search("containerization world trade")

    assert [r["url"] for r in results] == [
        "https://en.wikipedia.org/wiki/Containerization",
        "https://example.org/the-box",
    ]
    assert results[0]["title"] == "Containerization - Wikipedia"
    assert "reduced the costs of transport" in results[0]["summary"]
    assert results[0]["kind"] == "web"


def test_an_escaped_character_in_a_snippet_survives_the_parse(monkeypatch):
    monkeypatch.setattr(websearch, "_throttled_post", lambda data: _Response(LITE_PAGE))

    assert "Levinson's" in websearch.search("the box")[1]["summary"]


def test_the_page_changing_shape_returns_nothing_rather_than_rubbish(monkeypatch):
    """The day this markup changes, a run should get a thinner brief - not a
    list of sources scraped out of the wrong part of the page."""
    monkeypatch.setattr(
        websearch, "_throttled_post",
        lambda data: _Response("<html><body><p>nothing familiar here</p></body></html>"),
    )

    assert websearch.search("anything") == []


def test_being_blocked_is_read_as_no_results_not_as_a_failure(monkeypatch):
    monkeypatch.setattr(websearch, "_throttled_post", lambda data: _Response("", status_code=403))

    assert websearch.search("anything") == []


def test_the_search_being_down_narrows_the_brief_instead_of_ending_it(monkeypatch):
    def refuse(data):
        raise ConnectionError("down")

    monkeypatch.setattr(websearch, "_throttled_post", refuse)

    assert websearch.search("anything") == []


def test_an_empty_query_is_not_sent_at_all(monkeypatch):
    def fail(data):
        raise AssertionError("an empty query should never reach the endpoint")

    monkeypatch.setattr(websearch, "_throttled_post", fail)

    assert websearch.search("   ") == []


# ---------------------------------------------------------------------------
# Reading a page, once one is worth reading
# ---------------------------------------------------------------------------


class _Page:
    def __init__(self, body, content_type="text/html", status_code=200):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.encoding = "utf-8"
        self.raw = self
        self._body = body.encode("utf-8")

    def read(self, size, decode_content=True):
        return self._body[:size]

    def close(self):
        pass


def test_the_text_of_a_page_comes_back_without_its_markup(monkeypatch):
    """A title and a two-line snippet is enough to decide whether to cite a
    source and nowhere near enough to write from."""
    page = _Page(
        "<html><head><style>p{color:red}</style></head><body>"
        "<script>track()</script>"
        "<h1>The Ideal-X</h1><p>Sailed from Newark on 26 April 1956.</p>"
        "</body></html>"
    )
    monkeypatch.setattr(websearch.requests, "get", lambda *a, **k: page)

    text = websearch.read("https://example.org/ideal-x")

    assert "The Ideal-X" in text
    assert "26 April 1956" in text
    assert "track()" not in text
    assert "color:red" not in text
    assert "<" not in text


def test_a_pdf_is_not_read_as_text(monkeypatch):
    monkeypatch.setattr(
        websearch.requests, "get",
        lambda *a, **k: _Page("%PDF-1.4 binary", content_type="application/pdf"),
    )

    assert websearch.read("https://example.org/report.pdf") == ""


def test_a_page_that_will_not_load_is_simply_not_read(monkeypatch):
    def refuse(*args, **kwargs):
        raise TimeoutError("too slow")

    monkeypatch.setattr(websearch.requests, "get", refuse)

    assert websearch.read("https://example.org/slow") == ""


def test_a_long_page_is_cut_to_the_budget_it_was_given(monkeypatch):
    monkeypatch.setattr(
        websearch.requests, "get",
        lambda *a, **k: _Page("<p>" + ("word " * 5000) + "</p>"),
    )

    assert len(websearch.read("https://example.org/long", limit=500)) <= 500
