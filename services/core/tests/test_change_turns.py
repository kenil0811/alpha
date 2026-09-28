"""Changes need no approval and no essay: every plain-text turn on a module's thread is triaged,
small edits start at once, and a full change starts as soon as it is briefed."""

from __future__ import annotations

import time
from pathlib import Path

from alpha.assistant.service import AssistantService
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore


def settled(service: AssistantService, conversation_id: str, timeout: float = 10) -> object:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        record = service.get(conversation_id)
        if record.state != "thinking":
            return record
        time.sleep(0.02)
    raise AssertionError("the turn did not settle")


def test_every_text_turn_on_a_change_is_triaged_and_starts_on_its_own(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    started: list[str] = []
    service = AssistantService(
        store,
        gateway,
        StructuredInference(gateway),
        default_route="fake",
        describe_app=lambda _app_id: "Name: Notes list",
    )
    service.on_quick_change = lambda cid: started.append(cid)

    # A bigger change: triage says full, the usual turn briefs it, and it starts without a click.
    record = service.start("Keep a notes list for me", change_of="notes-list-1a2b3c")
    record = settled(service, record.conversation_id)
    assert record.state == "briefed" and record.quick_change is False
    assert started == [record.conversation_id], "a briefed change starts on its own"

    # A small follow-up typed into the same thread goes the quick way.
    service.reply(record.conversation_id, text="Remove the notes box from the top")
    record = settled(service, record.conversation_id)
    assert record.quick_change is True and record.state == "briefed"
    assert started == [record.conversation_id, record.conversation_id]
    assert len(record.reply or "") < 200, "no essay for a small change"


def test_a_declined_quick_change_continues_through_the_full_path(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    started: list[str] = []
    service = AssistantService(
        store,
        gateway,
        StructuredInference(gateway),
        default_route="fake",
        describe_app=lambda _app_id: "Name: Notes list",
    )
    service.on_quick_change = lambda cid: started.append(cid)
    record = service.start("Remove the notes list box from the top", change_of="notes-list-1a2b3c")
    record = settled(service, record.conversation_id)
    assert record.quick_change is True and started == [record.conversation_id]

    # The edit call declined: the same request is briefed the full way, no retyping, no click.
    service.escalate(record.conversation_id)
    record = settled(service, record.conversation_id)
    assert record.state == "briefed" and record.quick_change is False
    assert record.current_brief is not None, "the full path wrote a brief"
    assert started == [record.conversation_id, record.conversation_id]


def test_a_new_module_is_researched_and_proposed_before_it_is_briefed(tmp_path: Path) -> None:
    """Questions first, then a look around, then two or three shapes to choose from; the
    person's choice becomes the brief, and the research is not run twice."""
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    service = AssistantService(store, gateway, StructuredInference(gateway), default_route="fake")
    record = service.start("Keep a notes list for me")
    record = settled(service, record.conversation_id)
    assert record.state == "proposed", record.state
    assert record.proposal is not None
    assert [o["id"] for o in record.proposal["options"]] == ["lean", "full"]
    assert record.proposal["default"] == "full"
    assert record.proposal["evidence"][0]["kind"] == "search"
    assert record.current_brief is not None, "the brief is ready behind the options"

    service.reply(record.conversation_id, text="Go with 'List with tags and a done flag'.")
    record = settled(service, record.conversation_id)
    assert record.state == "briefed"
    assert record.proposal is not None, "the choice stays on record"
    usage = store.query("SELECT scope_kind FROM model_usage ORDER BY rowid")
    assert [r["scope_kind"] for r in usage].count("proposal") == 1


def test_changes_and_answers_are_not_researched(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    service = AssistantService(
        store,
        gateway,
        StructuredInference(gateway),
        default_route="fake",
        describe_app=lambda _app_id: "Name: Notes list",
    )
    record = settled(
        service, service.start("Keep a notes list for me", change_of="notes-x").conversation_id
    )
    assert record.state == "briefed" and record.proposal is None
    answer = settled(service, service.start("What is the capital of Australia?").conversation_id)
    assert answer.state == "answered" and answer.proposal is None
