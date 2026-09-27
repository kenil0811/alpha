"""Changing a module after it was made: the conversation carries the App it changes, the
creation rebuilds that App in place from its current version, and its records survive because
only additive schema changes are accepted."""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.assistant.prompts import turn_prompt
from alpha.assistant.service import AssistantService, UnknownApp
from alpha.capabilities.errors import OperationFailed
from alpha.data.store import RecordService, WriteContext, schema_change_problems
from alpha.solutions.creation import CHANGE_NOTE, CreationRoutes, CreationService
from alpha.solutions.describe import module_summary
from alpha.solutions.planner import AcceptancePlan
from alpha.storage.control_store import ControlStore
from alpha_contracts.apps import AppSource
from alpha_contracts.briefs import SolutionBrief
from alpha_contracts.builds import BuildState
from alpha_contracts.records import CollectionSchema, CreateRecord
from alpha_contracts.verification import ValidationPlan

# ----- the record store keeps data across a change -------------------------------------------


def schema(*fields: dict[str, Any], unique: list[list[str]] | None = None) -> CollectionSchema:
    return CollectionSchema.model_validate(
        {"name": "notes", "fields": list(fields), "unique": unique or []}
    )


TITLE = {"name": "title", "kind": "text", "required": True}
CALS = {"name": "calories", "kind": "number"}


def test_additive_changes_are_accepted_and_saved_records_stay(tmp_path: Path) -> None:
    store = RecordService(tmp_path / "apps").store("notes-x")
    assert store.register_collections([schema(TITLE)]) == [
        {"collection": "notes", "status": "registered"}
    ]
    saved = store.apply(
        [CreateRecord(collection="notes", values={"title": "Buy milk"})],
        WriteContext(run_id="run_1", allow_correction=False, resolve_estimate=None),
    )[0]
    assert saved is not None
    widened = schema(TITLE, CALS, {"name": "mood", "kind": "choice", "choices": ["ok", "great"]})
    assert store.register_collections([widened]) == [{"collection": "notes", "status": "migrated"}]
    assert [f.name for f in store.schema("notes").fields] == ["title", "calories", "mood"]
    again = store.get("notes", saved.id)
    assert again.values["title"] == "Buy milk"
    # The migrated shape is what a fresh store sees too.
    reopened = RecordService(tmp_path / "apps").store("notes-x")
    assert [f.name for f in reopened.schema("notes").fields] == ["title", "calories", "mood"]


@pytest.mark.parametrize(
    ("after", "problem"),
    [
        (schema(CALS), "was removed"),
        (schema({**TITLE, "kind": "number"}), "changed from text to number"),
        (schema(TITLE, {**CALS, "required": True}), "is required"),
        (schema(TITLE, unique=[["title"]]), "uniqueness"),
        (schema({**TITLE, "max_length": 5}), "tightened"),
    ],
)
def test_lossy_changes_are_refused_with_the_reason(
    tmp_path: Path, after: CollectionSchema, problem: str
) -> None:
    store = RecordService(tmp_path / "apps").store("notes-y")
    store.register_collections([schema(TITLE)])
    assert any(problem in p for p in schema_change_problems(schema(TITLE), after))
    with pytest.raises(OperationFailed) as failed:
        store.register_collections([after])
    assert failed.value.code == "conflict"
    assert problem in failed.value.message
    assert [f.name for f in store.schema("notes").fields] == ["title"], "nothing changed"


def test_narrowing_choices_is_refused_but_widening_is_not() -> None:
    mood = {"name": "mood", "kind": "choice", "choices": ["ok", "great"]}
    assert schema_change_problems(schema(TITLE, mood), schema(TITLE, {**mood, "choices": ["ok"]}))
    assert not schema_change_problems(
        schema(TITLE, mood), schema(TITLE, {**mood, "choices": ["ok", "great", "bad"]})
    )


# ----- the assistant knows which App it is changing ------------------------------------------

SOURCE = AppSource.model_validate(
    {
        "contract_version": "0.2",
        "app_id": "notes-list-1a2b3c",
        "name": "Notes list",
        "description": "Short notes you keep.",
        "runtime_profile": "pyprof-x",
        "sdk_version": "0.1.0",
        "capabilities": ["records"],
        "primary_action": "add_note",
        "collections": [{"name": "notes", "fields": [TITLE]}],
        "actions": [
            {
                "id": "add_note",
                "title": "Add a note",
                "description": "Save one note.",
                "handler": "notes_app.handlers:add_note",
                "invocable_from": ["ui", "manual"],
                "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
                "output_schema": {"type": "object"},
            }
        ],
    }
)


def test_the_summary_is_plain_and_complete() -> None:
    text = module_summary(SOURCE)
    assert "Name: Notes list" in text
    assert "- notes: title (text, required)" in text
    assert "- add_note: Add a note. Save one note. Inputs: title." in text


def test_the_turn_prompt_carries_the_existing_app_first() -> None:
    prompt = turn_prompt([], None, {"text": "add a mood"}, existing="Name: Notes list")
    assert prompt.startswith("EXISTING APP (this conversation changes it")
    assert "Name: Notes list" in prompt
    assert "CONVERSATION SO FAR" in prompt
    assert "EXISTING APP" not in turn_prompt([], None, {"text": "hi"})


def test_starting_a_change_of_an_unknown_module_is_refused(tmp_path: Path) -> None:
    gateway = SimpleNamespace(route=lambda route_id, **_: SimpleNamespace(route_id=route_id))
    service = AssistantService(
        ControlStore(tmp_path / "control.sqlite"),
        gateway,  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        default_route="fake",
        describe_app=lambda app_id: "Name: Notes list" if app_id == "notes-list-1a2b3c" else None,
    )
    with pytest.raises(UnknownApp):
        service.start("add a mood", change_of="nope")
    assert service.list_conversations(10) == []


# ----- the creation rebuilds the App in place ------------------------------------------------

BRIEF = SolutionBrief.model_validate(
    {
        "id": "brief_1",
        "revision": 2,
        "conversation_id": "conv_1",
        "created_at": datetime.now(UTC).isoformat(),
        "goal": "Notes list with a mood on each note",
        "success_summary": "Notes keep a mood",
        "delivery": "app",
        "surfaces": ["custom_ui"],
        "inputs": [],
        "primary_journey": [],
        "data_needs": [],
        "actions": [],
        "recurrence": None,
        "constraints": [],
        "acceptance_examples": [],
        "assumptions": [],
        "open_questions": [],
        "unavailable_capabilities": [],
        "selected_context_snapshot_id": "conv_1.context.r1",
    }
)
PLAN = ValidationPlan.model_validate(
    {
        "scenarios": [
            {"id": "s", "description": "d", "steps": [{"kind": "invoke", "id": "a", "action": "x"}]}
        ]
    }
)


class Builds:
    def __init__(self) -> None:
        self.submitted: dict[str, Any] = {}
        self.activations: list[dict[str, Any]] = []

    def submit(self, **kwargs: Any) -> Any:
        self.submitted = kwargs
        return SimpleNamespace(build_id="build_1")

    def get(self, build_id: str) -> Any:
        return SimpleNamespace(
            build_id=build_id,
            state=BuildState.READY,
            attempts=[],
            candidate=None,
            validation=None,
            terminal_reason=None,
            failure_category=None,
            budget=SimpleNamespace(max_repair_attempts=2),
        )

    def events(self, build_id: str) -> list[Any]:
        return []

    def activate(self, build_id: str, **kwargs: Any) -> dict[str, Any]:
        self.activations.append(kwargs)
        return {"release_id": "rel_2", "version_id": "ver_2", "app_id": "notes-list-1a2b3c"}


def creation_service(
    tmp_path: Path, builds: Builds, change_of: str | None, registry: Any
) -> CreationService:
    assistant = SimpleNamespace(
        get=lambda _cid: SimpleNamespace(state="briefed", current_brief=BRIEF, change_of=change_of)
    )
    planner = SimpleNamespace(
        plan=lambda *_a, **_k: AcceptancePlan("Notes with moods", PLAN, "model", [])
    )
    gateway = SimpleNamespace(route=lambda route_id, **_: SimpleNamespace(route_id=route_id))
    return CreationService(
        ControlStore(tmp_path / "control.sqlite"),
        assistant,  # type: ignore[arg-type]
        builds,  # type: ignore[arg-type]
        planner,  # type: ignore[arg-type]
        gateway,  # type: ignore[arg-type]
        CreationRoutes(planner="fake", builder="fake"),
        poll_seconds=0.01,
        registry=registry,
    )


def run(svc: CreationService) -> Any:
    creation = svc.start("conv_1")
    for thread in threading.enumerate():
        if thread.name == f"creation-{creation.creation_id}":
            thread.join(timeout=10)
    return svc.get(creation.creation_id)


def test_a_change_keeps_the_identity_starts_from_the_current_version_and_guards_the_release(
    tmp_path: Path,
) -> None:
    version_dir = tmp_path / "versions" / "ver_1"
    version_dir.mkdir(parents=True)
    (version_dir / "app.yaml").write_text("app_id: notes-list-1a2b3c\n")
    current = SimpleNamespace(
        app_id="notes-list-1a2b3c", release_id="rel_1", location=version_dir, source=SOURCE
    )

    def lookup(app_id: str) -> Any:
        if app_id != "notes-list-1a2b3c":
            raise OperationFailed("not_found", "no such App")
        return current

    builds = Builds()
    final = run(
        creation_service(tmp_path, builds, "notes-list-1a2b3c", SimpleNamespace(current=lookup))
    )
    assert final.state == "active", final.failure
    assert final.change_of == "notes-list-1a2b3c"
    assert final.app_id == "notes-list-1a2b3c" and final.app_name == "Notes list"
    assert builds.submitted["app_id"] == "notes-list-1a2b3c"
    assert builds.submitted["base_package"] == version_dir
    assert builds.submitted["instructions"].startswith(CHANGE_NOTE)
    assert "App name for the person: Notes list" in builds.submitted["instructions"]
    assert builds.activations == [
        {"expected_release_id": "rel_1", "creation_id": final.creation_id}
    ]


def test_a_new_module_is_untouched_by_the_change_path(tmp_path: Path) -> None:
    builds = Builds()
    final = run(creation_service(tmp_path, builds, None, None))
    assert final.state == "active" and final.change_of is None
    assert final.app_id.startswith("notes-with-moods-")
    assert builds.submitted["base_package"] is None
    assert not builds.submitted["instructions"].startswith(CHANGE_NOTE)
    assert builds.activations[0]["expected_release_id"] is None


def test_a_change_of_a_module_that_is_gone_is_refused_before_anything_starts(
    tmp_path: Path,
) -> None:
    def lookup(app_id: str) -> Any:
        raise OperationFailed("not_found", "no such App")

    svc = creation_service(tmp_path, Builds(), "notes-list-1a2b3c", SimpleNamespace(current=lookup))
    with pytest.raises(Exception, match="not installed"):
        svc.start("conv_1")
    assert svc.list_for_conversation("conv_1") == []


def test_a_module_thread_lists_its_creation_and_every_change_newest_first(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = SimpleNamespace(route=lambda route_id, **_: SimpleNamespace(route_id=route_id))
    assistant = AssistantService(
        store,
        gateway,  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        default_route="fake",
        describe_app=lambda _app_id: "Name: Notes list",
    )
    # Conversations exist without the model: rows written straight into the same store.
    with store.transaction() as conn:
        for cid, change_of, at in (
            ("conv_made", None, "2026-09-27T10:00:00Z"),
            ("conv_change1", "notes-list-1a2b3c", "2026-09-27T11:00:00Z"),
            ("conv_other", "other-app-000000", "2026-09-27T11:30:00Z"),
            ("conv_change2", "notes-list-1a2b3c", "2026-09-27T12:00:00Z"),
        ):
            conn.execute(
                """INSERT INTO conversations(conversation_id, state, route_id, created_at,
                   updated_at, latest_sequence, change_of) VALUES (?,?,?,?,?,0,?)""",
                (cid, "briefed", "fake", at, at, change_of),
            )
    svc = creation_service(tmp_path, Builds(), None, None)
    svc._assistant = assistant  # type: ignore[assignment]  # the real one, for get()
    with store.transaction() as conn:
        conn.execute(
            """INSERT INTO creations(creation_id, conversation_id, brief_id, brief_revision,
               app_id, state, history_json, created_at, updated_at)
               VALUES ('create_1','conv_made','brief_1',1,'notes-list-1a2b3c','active','[]',
                       '2026-09-27T10:05:00Z','2026-09-27T10:05:00Z')"""
        )
    thread = svc.conversations_for_app("notes-list-1a2b3c")
    assert [c.conversation_id for c in thread] == ["conv_change2", "conv_change1", "conv_made"]
    assert svc.conversations_for_app("nope") == []
