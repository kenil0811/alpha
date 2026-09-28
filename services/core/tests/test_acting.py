"""The third verb, do: a sentence runs or reads an existing module at once, or starts a build
or change when no module covers it, and the person hears what happened in plain words."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from alpha.assistant.acting import ActService, catalogue_text, template_reply
from alpha.capabilities.errors import OperationFailed
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from alpha_contracts.apps import AppSource
from alpha_contracts.runs import RunOrigin, RunState

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "builds" / "notes_ok"


def notes_source() -> AppSource:
    text = re.sub(r"\{\{[A-Z_]+\}\}", "x", (FIXTURE / "app.yaml.template").read_text())
    data = yaml.safe_load(text)
    data.pop("ui")
    data["views"] = [{"id": "notes.recent", "collection": "notes", "description": "Latest notes"}]
    data["actions"][0]["invocable_from"] = ["ui", "manual", "assistant"]
    return AppSource.model_validate(data)


class Registry:
    def __init__(self) -> None:
        self.source = notes_source()

    def list_apps(self) -> list[dict[str, Any]]:
        return [{"app_id": "notes", "state": "active"}, {"app_id": "gone", "state": "removed"}]

    def current(self, app_id: str) -> Any:
        if app_id != "notes":
            raise OperationFailed("not_found", "no such app", {})
        return SimpleNamespace(source=self.source)


class Runs:
    def __init__(self) -> None:
        self.invoked: list[tuple[str, str, dict[str, Any], RunOrigin]] = []
        self.output: dict[str, Any] = {"id": "rec_1", "revision": 1}
        self.state = RunState.SUCCEEDED

    def invoke(self, app_id: str, action_id: str, payload: dict[str, Any], *, origin: Any) -> Any:
        self.invoked.append((app_id, action_id, payload, origin))
        return SimpleNamespace(run_id="run_1")

    def lookup(self, run_id: str) -> Any:
        return SimpleNamespace(state=self.state, output=self.output, terminal_reason=None)


class Records:
    def store(self, app_id: str) -> Any:
        raise OperationFailed("not_found", "no records here", {})


class Assistant:
    def __init__(self) -> None:
        self.started: list[tuple[str, str | None]] = []

    def start(self, text: str, *, change_of: str | None = None) -> Any:
        self.started.append((text, change_of))
        return SimpleNamespace(conversation_id="conv_9")


def service(tmp_path: Path, runs: Runs, assistant: Assistant) -> ActService:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake"}))
    return ActService(
        store,
        gateway,
        StructuredInference(gateway),
        registry=Registry(),
        runs=runs,
        records=Records(),
        assistant=assistant,
        default_route="fake",
        run_lookup=runs.lookup,
        today=lambda: "2026-09-28",
    )


def test_the_catalogue_names_only_what_the_assistant_may_run() -> None:
    text = catalogue_text([("notes", notes_source())])
    assert "MODULE notes: Notes (fixture)" in text
    assert "action add_note" in text and "title (string, required)" in text
    assert "action count_notes" in text, "count_notes is invocable from the assistant"
    assert "view notes.recent: Latest notes" in text


def test_a_sentence_runs_the_action_at_once_and_says_so(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    turn = svc.act('fake:run notes add_note {"title": "Call the bank"}')
    assert turn.kind == "run" and turn.app_id == "notes" and turn.action_id == "add_note"
    assert runs.invoked == [("notes", "add_note", {"title": "Call the bank"}, RunOrigin.ASSISTANT)]
    assert turn.run_id == "run_1"
    assert turn.reply == "Done: add a note in Notes (fixture)."
    assert [t.turn_id for t in svc.recent()] == [turn.turn_id]


def test_a_result_with_numbers_is_phrased(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    runs.output = {"count": 3}
    svc = service(tmp_path, runs, assistant)
    turn = svc.act("fake:run notes count_notes")
    assert turn.reply.startswith("Done.") and '"count": 3' in turn.reply


def test_a_failed_run_is_reported_not_hidden(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    runs.state = RunState.FAILED
    svc = service(tmp_path, runs, assistant)
    turn = svc.act('fake:run notes add_note {"title": "x"}')
    assert turn.kind == "run" and "didn't finish" in turn.reply


def test_open_change_and_build_route_to_the_right_place(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    opened = svc.act("fake:open notes")
    assert opened.kind == "open" and opened.open == {"app_id": "notes", "tab_id": None}
    change = svc.act("fake:change notes make the notes bigger")
    assert change.kind == "change" and change.conversation_id == "conv_9"
    build = svc.act("fake:build a reading list")
    assert build.kind == "build" and build.open == {"conversation_id": "conv_9"}
    assert assistant.started == [
        ("fake:change notes make the notes bigger", "notes"),
        ("fake:build a reading list", None),
    ]
    plain = svc.act("hello there")
    assert plain.kind == "answer" and runs.invoked == []


def test_an_unknown_module_or_action_is_answered_plainly(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    assert svc.act("fake:run nowhere add_note {}").kind == "answer"
    turn = svc.act("fake:run notes fly {}")
    assert turn.kind == "run" and "nothing that does that" in turn.reply and runs.invoked == []


def test_template_replies_read_naturally() -> None:
    assert template_reply("count notes", {"count": 3}) == "Done: count notes. count 3."
    assert template_reply("save", {"id": "r", "revision": 2}) == "Done: save."
    assert template_reply("latest notes", [1, 2]) == "latest notes: 2 item(s)."
