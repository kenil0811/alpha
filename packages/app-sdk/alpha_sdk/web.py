"""ctx.web: read public web pages and search, through the platform (the `http` capability).

    page = ctx.web.get("https://example.com/prices")
    page.text          # readable text (HTML reduced to text), page.title, page.status
    page.links         # [Link(text, url)] every link on the page, absolute, in page order
    page.blocked       # True when the site answered with a sign-in page instead
    ctx.web.get(url, rendered=True)   # let the page's scripts run first (a browser loads it)
    hits = ctx.web.search("best beginner kettlebell routine", count=5)
    hits[0].title, hits[0].url, hits[0].snippet

The platform fetches on the App's behalf: only public http(s) addresses, a size and time cap, and
at most 60 requests per action run. Pass `raw=True` to get a JSON API's body untouched. When a
page cannot be reached the call raises; say so plainly instead of inventing content.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from alpha_sdk._channel import Transport


@dataclass(frozen=True)
class Link:
    text: str
    url: str
    # The text of the card the link sits in (name, title, company) when a browser read the
    # page; empty for a plain fetch. Use it when a link's own text is empty or generic.
    near: str = ""


@dataclass(frozen=True)
class Page:
    url: str
    final_url: str
    status: int
    content_type: str
    title: str | None
    text: str
    truncated: bool
    links: tuple[Link, ...] = ()
    # "fetch" or "browser"; signed_in when the person's session for the site was used.
    via: str = "fetch"
    signed_in: bool = False
    # The site answered with a sign-in page instead of the content: say so, store nothing.
    blocked: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str


class Web:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def get(
        self, url: str, *, max_chars: int = 60_000, raw: bool = False, rendered: bool = False
    ) -> Page:
        """Read a page. Sites the person allowed this App to read through their signed-in
        browser are read that way on their own; `rendered=True` loads a public page in a browser
        so its scripts run first."""
        data: dict[str, Any] = self._t.call(
            "http.get", {"url": url, "max_chars": max_chars, "raw": raw, "rendered": rendered}
        )
        return Page(
            url=str(data["url"]),
            final_url=str(data["final_url"]),
            status=int(data["status"]),
            content_type=str(data["content_type"]),
            title=data.get("title"),
            text=str(data["text"]),
            truncated=bool(data.get("truncated", False)),
            links=tuple(
                Link(
                    text=str(item.get("text", "")),
                    url=str(item["url"]),
                    near=str(item.get("near", "")),
                )
                for item in data.get("links", [])
                if item.get("url")
            ),
            via=str(data.get("via", "fetch")),
            signed_in=bool(data.get("signed_in", False)),
            blocked=bool(data.get("blocked", False)),
        )

    def search(self, query: str, *, count: int = 5) -> list[SearchHit]:
        data: dict[str, Any] = self._t.call("http.search", {"query": query, "count": count})
        return [
            SearchHit(title=str(h["title"]), url=str(h["url"]), snippet=str(h.get("snippet", "")))
            for h in data.get("hits", [])
        ]
