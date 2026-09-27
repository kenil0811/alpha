"""The `http` capability: fetch public web pages and search, on behalf of a run.

Limits, all enforced here rather than in generated code:
- only http(s) URLs to public hosts (no loopback, link-local or private ranges, no Core itself);
- a time cap per request and a size cap on the body;
- HTML reduced to readable text unless the caller asks for the raw body;
- a per-run budget of calls.

Search uses DuckDuckGo's HTML endpoint, which needs no account. It is a best-effort provider:
when its markup changes, search reports no hits with a plain reason rather than inventing any.
"""

from __future__ import annotations

import gzip
import html
import ipaddress
import re
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from html.parser import HTMLParser

from alpha_contracts.web import (
    HttpGetRequest,
    HttpPage,
    HttpSearchRequest,
    HttpSearchResult,
    PageLink,
    SearchHit,
)

from alpha.capabilities.errors import OperationFailed, invalid, limit

USER_AGENT = "Alpha/0.1 (personal automation; +local)"
MAX_BODY_BYTES = 2_000_000
TIMEOUT_SECONDS = 20
MAX_LINKS = 400  # links kept from one page
CALLS_PER_RUN = 60
SEARCH_URL = "https://html.duckduckgo.com/html/?q="

# (url, headers) -> (status, final_url, headers, body). Injected by tests.
Opener = Callable[[str, dict[str, str]], tuple[int, str, dict[str, str], bytes]]


def check_url(url: str) -> urllib.parse.ParseResult:
    """A public http(s) URL; refuses anything that could reach this Mac or a private network."""
    parsed = urllib.parse.urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise invalid(f"only http and https addresses can be fetched, not {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise invalid("the address has no host")
    if parsed.username or parsed.password:
        raise invalid("addresses with a user name or password are not fetched")
    lowered = host.lower()
    if lowered in ("localhost",) or lowered.endswith(".localhost") or lowered.endswith(".local"):
        raise invalid("addresses on this Mac or the local network are not fetched")
    try:
        candidates = [ipaddress.ip_address(lowered)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except OSError as exc:
            raise OperationFailed("unavailable", f"{host} could not be found") from exc
        candidates = [ipaddress.ip_address(info[4][0]) for info in infos]
    for address in candidates:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise invalid("addresses on this Mac or the local network are not fetched")
    return parsed


class _Text(HTMLParser):
    """Readable text from HTML: scripts, styles and tags dropped; block boundaries kept."""

    BLOCK = {
        "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "td", "th",
        "table", "section", "article", "header", "footer", "nav", "blockquote", "pre", "hr",
    }  # fmt: skip

    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: str | None = None
        self.links: list[tuple[str, str]] = []
        self._base = base_url
        self._skip = 0
        self._in_title = False
        self._href: str | None = None
        self._anchor: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            href = dict(attrs).get("href")
            self._href = href.strip() if href else None
            self._anchor = []
        elif tag == "base" and self._base is not None:
            href = dict(attrs).get("href")
            if href:
                self._base = urllib.parse.urljoin(self._base, href)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "template", "svg"):
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag == "a":
            self._finish_anchor()
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def _finish_anchor(self) -> None:
        href, words = self._href, " ".join("".join(self._anchor).split())
        self._href, self._anchor = None, []
        if not href or self._skip or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return
        absolute = urllib.parse.urljoin(self._base, href) if self._base else href
        if absolute.startswith(("http://", "https://")) and len(self.links) < MAX_LINKS:
            self.links.append((words[:200], absolute.split("#")[0]))

    def handle_data(self, data: str) -> None:
        if self._in_title:
            if self.title is None:
                self.title = " ".join(data.split()) or None
            return
        if self._skip == 0:
            self.parts.append(data)
            if self._href is not None:
                self._anchor.append(data)


def html_to_text(body: str, base_url: str | None = None) -> tuple[str | None, str]:
    title, text, _links = html_to_parts(body, base_url)
    return title, text


def html_to_parts(body: str, base_url: str | None = None) -> tuple[str | None, str, list[PageLink]]:
    """Title, readable text and the page's links (absolute, in order, deduplicated)."""
    parser = _Text(base_url)
    try:
        parser.feed(body)
        parser.close()
    except Exception:  # malformed markup still yields what was parsed
        pass
    text = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    seen: set[str] = set()
    links: list[PageLink] = []
    for words, url in parser.links:
        if url in seen:
            continue
        seen.add(url)
        links.append(PageLink(text=words, url=url))
    return parser.title, "\n".join(line for line in lines if line).strip(), links


def _default_opener(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            body = response.read(MAX_BODY_BYTES + 1)
            info = {k.lower(): v for k, v in response.headers.items()}
            return response.status, response.geturl(), info, body
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_BODY_BYTES + 1) if exc.fp else b""
        return exc.code, exc.geturl() or url, {k.lower(): v for k, v in exc.headers.items()}, body
    except urllib.error.URLError as exc:
        raise OperationFailed("unavailable", f"could not reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise OperationFailed(
            "unavailable", f"{url} did not answer within {TIMEOUT_SECONDS} s"
        ) from exc


def _now() -> str:
    return datetime.now(tz=UTC).isoformat().replace("+00:00", "Z")


class WebService:
    def __init__(self, opener: Opener | None = None, calls_per_run: int = CALLS_PER_RUN) -> None:
        self._open = opener or _default_opener
        self._per_run = calls_per_run
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def _charge(self, run_id: str) -> None:
        with self._lock:
            used = self._counts.get(run_id, 0)
            if used >= self._per_run:
                raise limit(f"this run has used its {self._per_run} web requests")
            self._counts[run_id] = used + 1

    def forget(self, run_id: str) -> None:
        with self._lock:
            self._counts.pop(run_id, None)

    def get(self, run_id: str, request: HttpGetRequest) -> HttpPage:
        parsed = check_url(request.url)
        self._charge(run_id)
        status, final_url, headers, body = self._open(
            parsed.geturl(),
            {
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.5",
                "Accept-Encoding": "gzip",
            },
        )
        if final_url != parsed.geturl():
            check_url(final_url)  # a redirect may not lead somewhere private
        if headers.get("content-encoding", "").lower() == "gzip":
            try:
                body = gzip.decompress(body)
            except OSError:
                pass
        truncated = len(body) > MAX_BODY_BYTES
        body = body[:MAX_BODY_BYTES]
        content_type = (
            headers.get("content-type", "application/octet-stream").split(";")[0].strip().lower()
        )
        charset = "utf-8"
        match = re.search(r"charset=([\w-]+)", headers.get("content-type", ""), re.I)
        if match:
            charset = match.group(1)
        try:
            decoded = body.decode(charset, errors="replace")
        except LookupError:
            decoded = body.decode("utf-8", errors="replace")
        title: str | None = None
        text = decoded
        links: list[PageLink] = []
        if not request.raw and (
            "html" in content_type
            or decoded.lstrip()[:15].lower().startswith(("<!doctype html", "<html"))
        ):
            title, text, links = html_to_parts(decoded, final_url)
        if len(text) > request.max_chars:
            text = text[: request.max_chars]
            truncated = True
        return HttpPage(
            url=request.url,
            final_url=final_url,
            status=status,
            content_type=content_type,
            title=title,
            text=text,
            links=links,
            truncated=truncated,
            fetched_at=_now(),
        )

    def search(self, run_id: str, request: HttpSearchRequest) -> HttpSearchResult:
        self._charge(run_id)
        url = SEARCH_URL + urllib.parse.quote_plus(request.query)
        status, _final, headers, body = self._open(
            url, {"User-Agent": USER_AGENT, "Accept": "text/html", "Accept-Encoding": "gzip"}
        )
        if headers.get("content-encoding", "").lower() == "gzip":
            try:
                body = gzip.decompress(body)
            except OSError:
                pass
        hits: list[SearchHit] = []
        if status == 200:
            hits = parse_duckduckgo(body.decode("utf-8", errors="replace"))[: request.count]
        return HttpSearchResult(
            query=request.query, provider="duckduckgo", hits=hits, searched_at=_now()
        )


_ANCHOR = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>', re.S
)
_SNIPPET = re.compile(r'class="result__snippet"[^>]*>(?P<snippet>.*?)</a>', re.S)
_TAGS = re.compile(r"<[^>]+>")


def parse_duckduckgo(page: str) -> list[SearchHit]:
    """Result links from DuckDuckGo's HTML page; redirect wrappers are unwrapped to the target."""
    hits: list[SearchHit] = []
    anchors = list(_ANCHOR.finditer(page))
    for index, match in enumerate(anchors):
        href = html.unescape(match.group("href"))
        if href.startswith("//"):
            href = "https:" + href
        parsed = urllib.parse.urlparse(href)
        if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
            target = urllib.parse.parse_qs(parsed.query).get("uddg", [""])[0]
            if target:
                href = target
        if not href.startswith("http"):
            continue
        title = html.unescape(_TAGS.sub("", match.group("title") or "")).strip()
        block_end = anchors[index + 1].start() if index + 1 < len(anchors) else len(page)
        found = _SNIPPET.search(page, match.end(), block_end)
        snippet = html.unescape(_TAGS.sub("", found.group("snippet"))).strip() if found else ""
        if title:
            hits.append(SearchHit(title=title, url=href, snippet=snippet))
    return hits
