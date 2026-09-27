"""Web access for generated code (`http` capability family): fetch a public page or search.

Both go through Core, which applies the limits (public hosts only, size and time caps, a
per-run budget) and records every call on the run's activity. Generated code never opens a
socket itself.
"""

from __future__ import annotations

from pydantic import Field

from alpha_contracts.runs import ContractModel


class HttpGetRequest(ContractModel):
    url: str = Field(min_length=8, max_length=2000)
    # Characters of text kept from the response (after HTML is reduced to readable text).
    max_chars: int = Field(default=60_000, ge=1000, le=400_000)
    # When true the raw body is returned instead of readable text (for JSON APIs and feeds).
    raw: bool = False
    # When true the page is loaded in a browser so scripts run before it is read (pages that
    # draw their content with scripts). Sites the person allowed this App to read through their
    # signed-in browser always load that way.
    rendered: bool = False


class PageLink(ContractModel):
    """One link on a fetched page: its visible text and absolute address."""

    text: str
    url: str


class HttpPage(ContractModel):
    url: str
    final_url: str
    status: int
    content_type: str
    title: str | None = None
    text: str
    # Links found in the HTML (absolute http(s) addresses, in page order, deduplicated), so
    # listing pages can be followed without parsing markup. Empty for raw or non-HTML bodies.
    links: list[PageLink] = Field(default_factory=list)
    truncated: bool = False
    fetched_at: str
    # How it was read: a plain fetch, or a browser (with the person's session when signed_in).
    via: str = "fetch"
    signed_in: bool = False
    # The site sent the browser to a sign-in page instead of the content asked for.
    blocked: bool = False


class HttpSearchRequest(ContractModel):
    query: str = Field(min_length=1, max_length=400)
    count: int = Field(default=5, ge=1, le=10)


class SearchHit(ContractModel):
    title: str
    url: str
    snippet: str


class HttpSearchResult(ContractModel):
    query: str
    provider: str
    hits: list[SearchHit]
    searched_at: str
