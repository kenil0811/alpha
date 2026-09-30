"""Why a page came back as a sign-in wall, and the way out: Alpha knows whether the person is
signed in and whether the module may use that sign-in, says so, and allows it on their yes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from alpha.assistant.acting import ActService, access_facts
from alpha.assistant.sessions import SessionService
from alpha.capabilities.browser import BrowserService
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from test_acting import Records, Registry, Runs  # noqa: I001

URL = "https://www.linkedin.com/mynetwork/invite-connect/connections/"


def browser(store: ControlStore, tmp_path: Path) -> BrowserService:
    return BrowserService(
        store, node=None, script=None, root=tmp_path / "browser", runner=lambda _job: {}
    )


def signed_in(store: ControlStore, site: str = "linkedin.com") -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO browser_sites(site, state, connected_at, updated_at)"
            " VALUES (?, 'connected', '2026-09-29T15:51:10Z', '2026-09-29T15:51:10Z')",
            (site,),
        )


def visit(store: ControlStore, app_id: str, at: str, *, blocked: int, signed: int = 0) -> None:
    with store.transaction() as conn:
        conn.execute(
            """INSERT INTO browser_visits(visit_id, app_id, run_id, site, url, final_url, status,
               blocked, signed_in, at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (f"v_{at}", app_id, "run_1", "linkedin.com", URL, URL, 200, blocked, signed, at),
        )


def test_alpha_knows_why_the_sign_in_page_came_back(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    svc = browser(store, tmp_path)
    visit(store, "notes", "2026-09-29T15:49:09Z", blocked=1)
    visit(store, "notes", "2026-09-29T15:52:03Z", blocked=1)
    # Not signed in at all: the way in is Connections, in Alpha's own window.
    (entry,) = svc.access("notes", "Connections list")
    assert entry["connected"] is False and entry["walled"] == 2 and entry["reads"] == 2
    (line,) = access_facts([entry])
    assert (
        "is not signed in in Alpha's browser" in line and "Safari or Chrome does not count" in line
    )
    # Signed in, but this module was never allowed: that is the whole cause.
    signed_in(store)
    (entry,) = svc.access("notes", "Connections list")
    assert entry["connected"] is True and entry["allowed"] is False
    (line,) = access_facts([entry])
    assert "The person IS signed in to linkedin.com" in line
    assert "Do not tell them to sign in again" in line
    # Allowed and still walled: the sign-in lapsed.
    assert svc.allow("notes", "linkedin.com") == ["linkedin.com"]
    (entry,) = svc.access("notes", "Connections list")
    assert entry["allowed"] is True
    assert "has probably lapsed" in access_facts([entry])[0]
    # Once a read goes through, there is nothing to say.
    visit(store, "notes", "2026-09-29T16:10:00Z", blocked=0, signed=1)
    (entry,) = svc.access("notes", "Connections list")
    assert entry["last_walled"] is False and access_facts([entry]) == []


def loop(tmp_path: Path) -> tuple[ActService, BrowserService, ControlStore, Runs]:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    registry = Registry()
    registry.source = registry.source.model_copy(
        update={"capabilities": [*registry.source.capabilities, "browser"]}
    )
    runs = Runs()
    svc = browser(store, tmp_path)
    acting = ActService(
        store,
        gateway,
        StructuredInference(gateway),
        registry=registry,
        runs=runs,
        records=Records(),
        assistant=None,
        sessions=SessionService(store),
        default_route="fake",
        run_lookup=runs.lookup,
        browser=svc,
        today=lambda: "2026-09-29",
    )
    return acting, svc, store, runs


def detail_of(acting: ActService, turn: Any) -> dict[str, Any]:
    session = acting._sessions.get(turn.session_id)
    return session.turns[-1].detail or {}


def test_the_reply_offers_the_yes_and_the_yes_allows_it(tmp_path: Path) -> None:
    acting, svc, store, runs = loop(tmp_path)
    signed_in(store)
    visit(store, "notes", "2026-09-29T15:52:03Z", blocked=1)
    asked = acting.act("I did log in, so why is it still not working")
    offer = detail_of(acting, asked)["offer"]
    assert offer["kind"] == "allow_site" and offer["site"] == "linkedin.com"
    assert offer["label"] == "Allow linkedin.com and try again"
    assert svc.grants("notes") == [], "nothing is allowed before the person says yes"

    agreed = acting.act("fake:allow notes linkedin.com")
    assert agreed.kind == "allow"
    assert agreed.reply == "Notes (fixture) may now read linkedin.com through your sign-in."
    assert agreed.outcome == ("allowed Notes (fixture) to read linkedin.com through the sign-in")
    assert svc.grants("notes") == ["linkedin.com"]
    assert "offer" not in detail_of(acting, agreed)


def test_allow_does_nothing_without_a_sign_in_or_a_need(tmp_path: Path) -> None:
    acting, svc, store, _ = loop(tmp_path)
    nothing = acting.act("fake:allow notes linkedin.com")
    assert nothing.reply == "Notes (fixture) is not waiting on access to a site."
    visit(store, "notes", "2026-09-29T15:52:03Z", blocked=1)
    walled = acting.act("fake:allow notes linkedin.com")
    assert walled.reply.startswith("You are not signed in to linkedin.com in Alpha's browser")
    assert svc.grants("notes") == []
    assert "offer" not in detail_of(acting, walled), "no yes to offer before they are signed in"
