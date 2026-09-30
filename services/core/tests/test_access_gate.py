"""The + menu's Access group (AP-182 audit, TASK: "+ Advanced for model and access"):

- "ask" gates every internet/egress run and anything unsafe-shaped, every time.
- "approve_for_me" gates only the unsafe-shaped ones (deletes, sends, payments); a plain read
  never waits.
- "full" never gates here (a secret leak or an irreversible delete of the person's own data is a
  separate, pre-existing concern this task does not touch).

Nothing in Core asked for approval before this existed (`RunState.WAITING_APPROVAL` is declared
in alpha_contracts.runs but nothing ever transitions a run into it) - these are the gate's first
tests, not a regression suite for an old one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alpha.assistant.acting import ActService, needs_approval
from alpha.assistant.sessions import SessionService
from alpha.capabilities.errors import OperationFailed
from alpha.models.gateway import ModelGateway, RouteUnavailable
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from alpha_contracts.runs import RunOrigin
from test_acting import Assistant, Records, Registry, Runs, notes_source

# ----- needs_approval: pure classification, no I/O -----------------------------------------


def test_ask_gates_every_egress_run_even_a_plain_read() -> None:
    assert needs_approval("ask", egress=True, runs=[{"action_id": "read_page", "input": {}}])


def test_ask_gates_an_unsafe_action_even_without_egress() -> None:
    assert needs_approval("ask", egress=False, runs=[{"action_id": "delete_note", "input": {}}])


def test_ask_does_not_gate_a_plain_local_write() -> None:
    assert not needs_approval("ask", egress=False, runs=[{"action_id": "add_note", "input": {}}])


def test_approve_for_me_does_not_gate_a_plain_egress_read() -> None:
    assert not needs_approval(
        "approve_for_me", egress=True, runs=[{"action_id": "read_page", "input": {}}]
    )


def test_approve_for_me_gates_deletes_sends_and_payments() -> None:
    for action_id in ("delete_note", "send_email", "make_payment", "charge_card"):
        run = {"action_id": action_id, "input": {}}
        assert needs_approval("approve_for_me", egress=False, runs=[run])


def test_full_never_gates() -> None:
    assert not needs_approval("full", egress=True, runs=[{"action_id": "delete_note", "input": {}}])


# ----- ActService: the gate actually stops the run, and an approval resumes it -------------


def egress_source():
    return notes_source().model_copy(update={"capabilities": ["records", "http"]})


class EgressRegistry(Registry):
    def __init__(self) -> None:
        self.source = egress_source()


def service(tmp_path: Path, runs: Runs, assistant: Assistant, registry=None) -> ActService:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    return ActService(
        store,
        gateway,
        StructuredInference(gateway),
        registry=registry or Registry(),
        runs=runs,
        records=Records(),
        assistant=assistant,
        sessions=SessionService(store),
        default_route="fake",
        run_lookup=runs.lookup,
        today=lambda: "2026-09-28",
    )


def test_ask_blocks_an_egress_run_and_offers_approval(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant, registry=EgressRegistry())
    turn = svc.act('fake:run notes add_note {"title": "x"}', access_mode="ask")
    assert turn.kind == "run" and runs.invoked == [], "nothing ran: it needed the person's OK first"
    assert "OK first" in turn.reply


def test_approve_for_me_lets_a_read_through_but_blocks_a_delete(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant, registry=EgressRegistry())
    svc.act('fake:run notes add_note {"title": "x"}', access_mode="approve_for_me")
    assert runs.invoked, "a plain local write is not unsafe under approve_for_me"

    runs2, assistant2 = Runs(), Assistant()
    svc2 = service(tmp_path, runs2, assistant2)
    blocked = svc2.act('fake:run notes delete_note {}', access_mode="approve_for_me")
    assert runs2.invoked == [], "delete_note matches the unsafe pattern"
    assert blocked.kind == "run"


def test_full_access_runs_at_once(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant, registry=EgressRegistry())
    turn = svc.act('fake:run notes add_note {"title": "x"}', access_mode="full")
    assert runs.invoked, "full access has no approval prompts, even for an egress-capable module"
    assert turn.model_error is None


def test_an_invalid_access_mode_is_refused(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    with pytest.raises(OperationFailed):
        svc.act("hello", access_mode="whenever")


def test_approving_a_gated_run_carries_out_exactly_that_run(tmp_path: Path) -> None:
    """The offer's "Approve and run" sends the person's plain yes; Core runs the stored run
    unchanged, with no new model call re-deciding it."""
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant, registry=EgressRegistry())
    gated = svc.act('fake:run notes add_note {"title": "x"}', access_mode="ask")
    assert runs.invoked == []
    session_id = gated.session_id
    approved = svc.send(session_id, "Yes, go ahead and let Notes (fixture) do that.", wait=True)
    assert approved is not None
    assert runs.invoked == [("notes", "add_note", {"title": "x"}, RunOrigin.ASSISTANT)]


# ----- ModelGateway: a per-request model override ------------------------------------------


def test_route_honours_a_connected_account_override(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake", "openrouter"}))
    route = gateway.route("fake", stage="assistant", account_override="openrouter")
    assert route.route_id == "openrouter"


def test_route_rejects_an_override_to_a_not_connected_provider(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))  # grok never enabled on this host
    with pytest.raises(RouteUnavailable):
        gateway.route("fake", stage="assistant", account_override="grok")


def test_route_rejects_an_unknown_account(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    with pytest.raises(RouteUnavailable):
        gateway.route("fake", stage="assistant", account_override="groq")


def test_an_unavailable_model_override_surfaces_as_a_not_connected_reply(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    svc = ActService(
        store,
        gateway,
        StructuredInference(gateway),
        registry=Registry(),
        runs=runs,
        records=Records(),
        assistant=assistant,
        sessions=SessionService(store),
        default_route="fake",
        run_lookup=runs.lookup,
        today=lambda: "2026-09-28",
    )
    turn = svc.act("hello", model={"provider": "grok"})
    assert turn.model_error == {"kind": "generic", "provider": "grok"}
    assert "grok" in turn.reply.lower() or "model" in turn.reply.lower()
