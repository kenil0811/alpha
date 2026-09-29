"""The third verb, do: a sentence runs or reads an existing module at once, or starts a build
or change when no module covers it, and the person hears what happened in plain words."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from alpha.assistant.acting import ActService, catalogue_text, outcome_line, summary_reply
from alpha.assistant.sessions import SessionService
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

    def start(
        self, text: str, *, change_of: str | None = None, session_id: str | None = None
    ) -> Any:
        self.started.append((text, change_of))
        self.session_id = session_id
        return SimpleNamespace(conversation_id="conv_9")

    def get(self, conversation_id: str) -> Any:
        return SimpleNamespace(state="answered")


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
        sessions=SessionService(store),
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


def test_a_sentence_runs_the_action_at_once_and_says_what_happened(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    turn = svc.act('fake:run notes add_note {"title": "Call the bank"}')
    assert turn.kind == "run" and turn.app_id == "notes" and turn.action_id == "add_note"
    assert runs.invoked == [("notes", "add_note", {"title": "Call the bank"}, RunOrigin.ASSISTANT)]
    assert turn.run_id == "run_1"
    assert turn.reply == "Done: 1 succeeded, 0 failed, 0 read.", "written after the outcome"
    assert turn.outcome == "ran add_note 1 time(s) in Notes (fixture): 1 succeeded, 0 failed"
    assert [t.turn_id for t in svc.recent()] == [turn.turn_id]
    assert turn.session_id is not None, "the avatar talks to the Quick asks session"


def test_several_entries_go_in_one_step(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    turn = svc.act('fake:runs notes add_note [{"title": "a"}, {"title": "b"}, {"title": "c"}]')
    assert [i[2]["title"] for i in runs.invoked] == ["a", "b", "c"]
    assert turn.reply == "Done: 3 succeeded, 0 failed, 0 read."


def test_a_failed_run_is_reported_not_hidden(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    runs.state = RunState.FAILED
    svc = service(tmp_path, runs, assistant)
    turn = svc.act('fake:run notes add_note {"title": "x"}')
    assert turn.kind == "run" and turn.reply == "Done: 0 succeeded, 1 failed, 0 read."
    assert "0 succeeded, 1 failed" in (turn.outcome or "")


def test_open_change_and_build_route_to_the_right_place(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    opened = svc.act("fake:open notes")
    assert opened.kind == "open" and opened.open == {"app_id": "notes", "tab_id": None}
    change = svc.act("fake:change notes make the notes bigger")
    assert change.kind == "change" and change.conversation_id == "conv_9"
    build = svc.act("fake:build a reading list")
    assert build.kind == "build"
    assert build.open == {"conversation_id": "conv_9", "session_id": build.session_id}
    assert assistant.session_id == build.session_id, "the conversation is a card in the session"
    assert assistant.started == [
        ("fake:change notes make the notes bigger", "notes"),
        ("fake:build a reading list", None),
    ]
    plain = svc.act("hello there")
    assert plain.kind == "answer" and runs.invoked == []
    assert plain.outcome == "nothing was done; Alpha only replied"


def test_the_facts_say_what_earlier_sentences_led_to(tmp_path: Path) -> None:
    """A later "are you still on it?" is answered from these, never from the story."""
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    turn = svc.act("fake:build fill ten days of data")
    facts = svc._facts({"notes": "Notes (fixture)"}, turn.session_id)
    assert facts == [
        "the request started earlier in this session is now: answered; nothing is being built"
    ]
    assert (
        turn.outcome
        == ("started a request to make something new; it is now: answered; nothing is being built")
        or turn.outcome == "started a request to make something new"
    )
    memory = svc._sessions.memory_text(turn.session_id, "still on it?")
    assert "person: fake:build fill ten days of data" in memory
    assert "outcome: started a request to make something new; it is now: answered" in memory


def test_an_unknown_module_or_action_is_answered_plainly(tmp_path: Path) -> None:
    runs, assistant = Runs(), Assistant()
    svc = service(tmp_path, runs, assistant)
    assert svc.act("fake:run nowhere add_note {}").kind == "answer"
    turn = svc.act("fake:run notes fly {}")
    assert turn.kind == "run" and "1 failed" in turn.reply and runs.invoked == []


def test_summaries_read_naturally() -> None:
    assert summary_reply([]) == "Nothing was done."
    assert summary_reply([{"results": [{"outcome": "succeeded"}, {"outcome": "failed: x"}]}]) == (
        "Finished: 1 done, 1 did not go through."
    )
    assert outcome_line("open", {}, "Notes") == "opened Notes in Alpha's window"
    assert outcome_line("query", {"observations": [{"rows": []}]}, "Notes") == (
        "read Notes; nothing was changed"
    )
