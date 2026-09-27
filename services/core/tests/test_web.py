"""The http capability: public addresses only, readable text from HTML, a per-run budget, and
search results parsed from DuckDuckGo's HTML page."""

# ruff: noqa: E501
from __future__ import annotations

import pytest
from alpha.capabilities.errors import OperationFailed
from alpha.capabilities.web import WebService, check_url, html_to_text, parse_duckduckgo
from alpha_contracts.web import HttpGetRequest, HttpSearchRequest

PAGE = b"""<!doctype html><html><head><title> Prices  today </title>
<style>.x{color:red}</style><script>alert(1)</script></head>
<body><h1>Prices</h1><p>Apples &amp; pears: <b>3</b> each.</p>
<ul><li>one</li><li>two</li></ul><noscript>ignored</noscript></body></html>"""

DDG = """\
<div class="result"><h2 class="result__title">
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&amp;rut=1">First <b>hit</b></a>
</h2><a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">A snippet &amp; more</a></div>
<div class="result"><h2 class="result__title"><a class="result__a" href="https://example.org/b">Second</a></h2></div>"""


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/x",
        "http://localhost:8000/",
        "http://127.0.0.1:59574/api/health",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://user:pw@example.com/",
        "http://printer.local/",
    ],
)
def test_private_and_odd_addresses_are_refused(url: str) -> None:
    with pytest.raises(OperationFailed) as info:
        check_url(url)
    assert info.value.code == "invalid_input"


def test_html_becomes_readable_text_with_a_title() -> None:
    title, text = html_to_text(PAGE.decode())
    assert title == "Prices today"
    assert "alert(1)" not in text and "color:red" not in text and "ignored" not in text
    assert "Prices\nApples & pears: 3 each.\none\ntwo" == text


def test_get_reduces_html_and_charges_the_budget() -> None:
    calls: list[str] = []

    def opener(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str], bytes]:
        calls.append(url)
        return 200, url, {"content-type": "text/html; charset=utf-8"}, PAGE

    web = WebService(opener=opener, calls_per_run=2)
    page = web.get("run_1", HttpGetRequest(url="https://example.com/prices"))
    assert page.status == 200 and page.title == "Prices today" and page.text.startswith("Prices")
    raw = web.get("run_1", HttpGetRequest(url="https://example.com/prices", raw=True))
    assert raw.text.startswith("<!doctype html>")
    with pytest.raises(OperationFailed) as info:
        web.get("run_1", HttpGetRequest(url="https://example.com/again"))
    assert info.value.code == "limit_exceeded"
    web.forget("run_1")
    web.get("run_1", HttpGetRequest(url="https://example.com/again"))
    assert len(calls) == 3
    # Another run has its own budget.
    web.get("run_2", HttpGetRequest(url="https://example.com/other"))


def test_a_redirect_to_a_private_address_is_refused() -> None:
    def opener(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str], bytes]:
        return 200, "http://127.0.0.1:1/secret", {"content-type": "text/plain"}, b"x"

    with pytest.raises(OperationFailed):
        WebService(opener=opener).get("run", HttpGetRequest(url="https://example.com/"))


def test_search_parses_results_and_unwraps_redirects() -> None:
    hits = parse_duckduckgo(DDG)
    assert [(h.title, h.url) for h in hits] == [
        ("First hit", "https://example.com/a"),
        ("Second", "https://example.org/b"),
    ]
    assert hits[0].snippet == "A snippet & more"

    def opener(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str], bytes]:
        assert url.startswith("https://html.duckduckgo.com/html/?q=best+kettlebell")
        return 200, url, {}, DDG.encode()

    result = WebService(opener=opener).search(
        "run", HttpSearchRequest(query="best kettlebell", count=1)
    )
    assert result.provider == "duckduckgo" and [h.title for h in result.hits] == ["First hit"]


def test_search_that_cannot_be_read_reports_no_hits() -> None:
    def opener(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str], bytes]:
        return 503, url, {}, b"busy"

    result = WebService(opener=opener).search("run", HttpSearchRequest(query="x"))
    assert result.hits == []


LISTING = b"""<html><head><title>Jobs</title><base href="https://example.com/"></head><body>
<nav><a href="/">Home</a><a href="#top">Top</a><a href="mailto:x@y">Mail</a></nav>
<ul><li><a href="/remote-jobs/123-python-dev">Python developer</a> at Acme</li>
<li><a href="https://example.org/job/9?utm=1#apply">Data <b>engineer</b></a></li>
<li><a href="/remote-jobs/123-python-dev">Python developer (again)</a></li></ul>
<script><a href="/hidden">no</a></script></body></html>"""


def test_a_page_lists_its_links_absolute_and_in_order() -> None:
    def opener(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str], bytes]:
        return 200, url, {"content-type": "text/html"}, LISTING

    page = WebService(opener=opener).get("run_9", HttpGetRequest(url="https://example.com/s"))
    assert [(link.text, link.url) for link in page.links] == [
        ("Home", "https://example.com/"),
        ("Python developer", "https://example.com/remote-jobs/123-python-dev"),
        ("Data engineer", "https://example.org/job/9?utm=1"),
    ]
    assert "Python developer" in page.text
    raw = WebService(opener=opener).get(
        "run_9", HttpGetRequest(url="https://example.com/s", raw=True)
    )
    assert raw.links == []
