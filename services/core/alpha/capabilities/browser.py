"""The `browser` capability: pages read through a browser Alpha keeps on this Mac.

Two uses. A public page drawn by scripts is loaded headless so the scripts run before it is
read. A site the person has signed into (in a window Alpha opens, with a profile Alpha keeps
under the data directory) is read through that session when the person has allowed a module to
use it for that site. Reading only: the worker never clicks, types or submits.

Guards: access is per module and per site, switched on by the person; pages are paced per site
(a gap between pages and a cap per hour, both in Settings) so it reads like a person; every page
opened through a session is recorded and shown in the module's Activity; the profile directory
is removed when the person disconnects the site.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from alpha_contracts.web import HttpGetRequest, HttpPage, PageLink

from alpha.capabilities.errors import OperationFailed, invalid, limit, unavailable
from alpha.capabilities.web import check_url
from alpha.storage.control_store import ControlStore, new_id, utc_now

log = logging.getLogger("alpha.browser")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS browser_sites (
    site TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    connected_at TEXT,
    updated_at TEXT NOT NULL,
    last_error TEXT
);
CREATE TABLE IF NOT EXISTS browser_grants (
    app_id TEXT NOT NULL,
    site TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    PRIMARY KEY (app_id, site)
);
CREATE TABLE IF NOT EXISTS browser_visits (
    visit_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    run_id TEXT,
    site TEXT NOT NULL,
    url TEXT NOT NULL,
    final_url TEXT,
    status INTEGER,
    blocked INTEGER NOT NULL DEFAULT 0,
    signed_in INTEGER NOT NULL DEFAULT 0,
    at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS browser_visits_site_at ON browser_visits(site, at);
CREATE INDEX IF NOT EXISTS browser_visits_app_at ON browser_visits(app_id, at);
"""

# Two-part public suffixes where the registrable site is three labels long.
_TWO_PART = {
    "co.uk",
    "org.uk",
    "ac.uk",
    "gov.uk",
    "com.au",
    "net.au",
    "co.in",
    "com.br",
    "co.jp",
    "co.nz",
    "com.sg",
}
_SITE = re.compile(r"^[a-z0-9.-]+$")
WORKER_TIMEOUT_SECONDS = 75
Runner = Callable[[dict[str, Any]], dict[str, Any]]


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def site_key(value: str) -> str:
    """The site a URL or a typed name belongs to: lowercase, no scheme or path, no www, the
    registrable part (linkedin.com, bbc.co.uk)."""
    text = value.strip().lower()
    if "://" in text:
        text = urlparse(text).hostname or ""
    else:
        text = text.split("/")[0].split("?")[0]
    text = text.strip(".")
    if text.startswith("www."):
        text = text[4:]
    if not text or not _SITE.match(text) or "." not in text:
        raise invalid(f"{value!r} is not a website name like linkedin.com")
    labels = text.split(".")
    keep = 3 if ".".join(labels[-2:]) in _TWO_PART else 2
    return ".".join(labels[-keep:])


class BrowserService:
    def __init__(
        self,
        store: ControlStore,
        *,
        node: Path | None,
        script: Path | None,
        root: Path,
        preferences: Any | None = None,
        browser: Path | None = None,
        runner: Runner | None = None,
    ) -> None:
        self._store = store
        self._node = node
        self._script = script
        self._root = root
        self._preferences = preferences
        self._browser = browser
        # The person's installed Chrome, when present, reads most like a person; otherwise the
        # pinned Playwright Chromium.
        self._channel = "chrome" if Path("/Applications/Google Chrome.app").exists() else None
        self._runner = runner or self._run_worker
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)

    # ----- availability ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        if self._runner is not self._run_worker:
            return True
        return bool(self._node and self._node.is_file() and self._script and self._script.is_file())

    def _profile(self, site: str) -> Path:
        return self._root / site

    # ----- sites the person connected ----------------------------------------------------

    def list_sites(self) -> list[dict[str, Any]]:
        rows = self._store.query("SELECT * FROM browser_sites ORDER BY site")
        grants = self._store.query("SELECT app_id, site FROM browser_grants")
        by_site: dict[str, list[str]] = {}
        for g in grants:
            by_site.setdefault(g["site"], []).append(g["app_id"])
        return [
            {
                "site": r["site"],
                "state": r["state"],
                "connected_at": r["connected_at"],
                "last_error": r["last_error"],
                "apps": sorted(by_site.get(r["site"], [])),
            }
            for r in rows
        ]

    def start_signin(self, value: str) -> dict[str, Any]:
        """Open a visible window on the site's own pages so the person signs in. Returns at
        once; the site is marked connected when they close the window with a session."""
        if not self.available:
            raise unavailable("the browser worker is not set up on this Mac")
        site = site_key(value)
        now = _now()
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO browser_sites(site, state, updated_at) VALUES (?,?,?)
                   ON CONFLICT(site) DO UPDATE SET state = 'signing_in',
                   updated_at = excluded.updated_at, last_error = NULL""",
                (site, "signing_in", now),
            )
        threading.Thread(
            target=self._signin, args=(site,), name=f"signin-{site}", daemon=True
        ).start()
        return {"site": site, "state": "signing_in"}

    def _signin(self, site: str) -> None:
        profile = self._profile(site)
        profile.mkdir(parents=True, exist_ok=True)
        profile.chmod(0o700)
        try:
            result = self._runner(
                {
                    "op": "signin",
                    "site": site,
                    "url": f"https://www.{site}/" if site.count(".") == 1 else f"https://{site}/",
                    "profile": str(profile),
                    "browser": str(self._browser) if self._browser else None,
                    "channel": self._channel,
                }
            )
            signed_in = bool(result.get("signed_in"))
            error = None if signed_in else "The window was closed without a signed-in session."
        except Exception as exc:  # the worker failed to run at all
            log.exception("sign-in for %s failed", site)
            signed_in, error = False, f"The browser could not be opened: {exc}"[:300]
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE browser_sites SET state = ?, connected_at = COALESCE(?, connected_at),
                   updated_at = ?, last_error = ? WHERE site = ?""",
                (
                    "connected" if signed_in else "not_connected",
                    _now() if signed_in else None,
                    _now(),
                    error,
                    site,
                ),
            )

    def remove_site(self, value: str) -> None:
        site = site_key(value)
        with self._store.transaction() as conn:
            conn.execute("DELETE FROM browser_grants WHERE site = ?", (site,))
            conn.execute("DELETE FROM browser_sites WHERE site = ?", (site,))
        shutil.rmtree(self._profile(site), ignore_errors=True)

    def connected_sites(self) -> set[str]:
        return {
            r["site"]
            for r in self._store.query("SELECT site FROM browser_sites WHERE state = 'connected'")
        }

    # ----- what each module may use ------------------------------------------------------

    def grants(self, app_id: str) -> list[str]:
        return [
            r["site"]
            for r in self._store.query(
                "SELECT site FROM browser_grants WHERE app_id = ? ORDER BY site", (app_id,)
            )
        ]

    def set_grants(self, app_id: str, sites: list[str]) -> list[str]:
        wanted = {site_key(s) for s in sites}
        connected = self.connected_sites()
        unknown = sorted(wanted - connected)
        if unknown:
            raise invalid(f"not signed in to {', '.join(unknown)}; connect the site first")
        now = _now()
        with self._store.transaction() as conn:
            conn.execute("DELETE FROM browser_grants WHERE app_id = ?", (app_id,))
            for site in sorted(wanted):
                conn.execute(
                    "INSERT INTO browser_grants(app_id, site, granted_at) VALUES (?,?,?)",
                    (app_id, site, now),
                )
        return sorted(wanted)

    def allow(self, app_id: str, site: str) -> list[str]:
        """Let one more connected site be read by this module through the person's sign-in."""
        return self.set_grants(app_id, [*self.grants(app_id), site])

    def access(self, app_id: str, name: str) -> list[dict[str, Any]]:
        """Where this module stands with each site it lately tried to read: whether the person
        is signed in there, whether the module may use that sign-in, and how its reads went.
        This is what lets Alpha say why a page came back as a sign-in wall."""
        connected = self.connected_sites()
        allowed = set(self.grants(app_id))
        by_site: dict[str, dict[str, Any]] = {}
        for visit in self.visits(app_id, limit_rows=12):
            entry = by_site.setdefault(
                visit["site"],
                {
                    "app_id": app_id,
                    "name": name,
                    "site": visit["site"],
                    "connected": visit["site"] in connected,
                    "allowed": visit["site"] in allowed,
                    "reads": 0,
                    "walled": 0,
                    "last_walled": bool(visit["blocked"]),  # the newest read, seen first
                    "last_at": visit["at"],
                },
            )
            entry["reads"] += 1
            entry["walled"] += 1 if visit["blocked"] else 0
        return [e for e in by_site.values() if e["walled"]]

    def allowed_site(self, app_id: str, url: str) -> str | None:
        """The connected site this module may read `url` through, or None."""
        try:
            site = site_key(url)
        except OperationFailed:
            return None
        rows = self._store.query(
            """SELECT g.site FROM browser_grants g JOIN browser_sites s USING(site)
               WHERE g.app_id = ? AND g.site = ? AND s.state = 'connected'""",
            (app_id, site),
        )
        return site if rows else None

    # ----- reading -----------------------------------------------------------------------

    def read(self, run_id: str, app_id: str, request: HttpGetRequest, site: str | None) -> HttpPage:
        """Load the page in the browser (through the site's session when `site` is given) and
        return it in the same shape as a plain fetch."""
        if not self.available:
            raise unavailable("the browser worker is not set up on this Mac")
        parsed = check_url(request.url)
        if site is not None:
            self._pace(site)
        try:
            result = self._runner(
                {
                    "op": "read",
                    "url": parsed.geturl(),
                    "profile": str(self._profile(site)) if site else None,
                    "max_chars": request.max_chars,
                    "scroll": 2,
                    "browser": str(self._browser) if self._browser else None,
                    "channel": self._channel,
                }
            )
        except OperationFailed:
            raise
        except Exception as exc:
            raise unavailable(f"the browser could not read {request.url}: {exc}") from exc
        if result.get("error"):
            raise unavailable(f"the browser could not read {request.url}: {result['error']}")
        page = HttpPage(
            url=request.url,
            final_url=str(result.get("final_url") or request.url),
            status=int(result.get("status") or 0),
            content_type=str(result.get("content_type") or "text/html"),
            title=result.get("title"),
            text=str(result.get("text") or ""),
            links=[
                PageLink(
                    text=str(item.get("text", ""))[:200],
                    url=str(item["url"]),
                    near=str(item.get("near", ""))[:240],
                )
                for item in result.get("links") or []
                if isinstance(item, dict) and item.get("url")
            ][:400],
            truncated=bool(result.get("truncated")),
            fetched_at=_now(),
            via="browser",
            signed_in=site is not None,
            blocked=bool(result.get("blocked")),
        )
        self._record_visit(app_id, run_id, site or site_key(request.url), page)
        return page

    def _pace(self, site: str) -> None:
        per_hour = int(self._pref("browser.pages_per_hour", 30))
        gap = int(self._pref("browser.min_seconds_between_pages", 15))
        now = datetime.now(tz=UTC)
        hour_ago = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        with self._lock:
            rows = self._store.query(
                "SELECT at FROM browser_visits WHERE site = ? AND signed_in = 1 AND at > ? "
                "ORDER BY at DESC",
                (site, hour_ago),
            )
            if len(rows) >= per_hour:
                raise limit(
                    f"{site} has been read {per_hour} times this hour, the limit in Settings; "
                    "the next check will continue"
                )
            if rows:
                last = datetime.fromisoformat(rows[0]["at"].replace("Z", "+00:00"))
                wait = gap - (now - last).total_seconds()
                if wait > 0:
                    raise limit(
                        f"too soon after the last page on {site}; wait {int(wait) + 1} s "
                        "(the gap between pages is set in Settings)"
                    )

    def _pref(self, key: str, default: int) -> int:
        if self._preferences is None:
            return default
        try:
            return int(self._preferences.get(key))
        except Exception:
            return default

    def _record_visit(self, app_id: str, run_id: str, site: str, page: HttpPage) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO browser_visits(visit_id, app_id, run_id, site, url, final_url,
                   status, blocked, signed_in, at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("visit"),
                    app_id,
                    run_id,
                    site,
                    page.url,
                    page.final_url,
                    page.status,
                    int(page.blocked),
                    int(page.signed_in),
                    _now(),
                ),
            )

    def visits(self, app_id: str, limit_rows: int = 50) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._store.query(
                "SELECT * FROM browser_visits WHERE app_id = ? ORDER BY at DESC LIMIT ?",
                (app_id, limit_rows),
            )
        ]

    # ----- the worker --------------------------------------------------------------------

    def _run_worker(self, job: dict[str, Any]) -> dict[str, Any]:
        assert self._node is not None and self._script is not None
        timeout = None if job.get("op") == "signin" else WORKER_TIMEOUT_SECONDS
        proc = subprocess.run(
            [str(self._node), str(self._script)],
            input=json.dumps(job) + "\n",
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(self._script.parent),
        )
        line = next((ln for ln in proc.stdout.splitlines() if ln.startswith("{")), None)
        if line is None:
            raise RuntimeError((proc.stderr or proc.stdout)[-300:] or "no answer from the browser")
        return dict(json.loads(line))
