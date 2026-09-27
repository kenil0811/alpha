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
