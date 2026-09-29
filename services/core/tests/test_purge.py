"""Removing a module is a clean deletion: nothing of it is left in the database, on disk, in the
sessions or in what the assistant is told, and nothing of any other module is touched."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.assistant.service import _SCHEMA as ASSISTANT_SCHEMA
from alpha.assistant.sessions import SessionService
from alpha.capabilities.errors import OperationFailed
from alpha.context.pack import ContextPacker
from alpha.context.profile import ProfileService
from alpha.context.projects import ProjectService
from alpha.solutions.creation import _SCHEMA as CREATION_SCHEMA
from alpha.solutions.purge import ModulePurge
from alpha.solutions.registry import _APP_COLUMNS, _RELEASE_COLUMNS
from alpha.solutions.registry import _SCHEMA as REGISTRY_SCHEMA
from alpha.storage.control_store import ControlStore
from alpha_contracts.runs import AppOwner, ExecutionSnapshot, RunLimits, RunOrigin, RunState

NOW = "2026-09-29T15:00:00Z"


class Registry:
    def __init__(self, store: ControlStore) -> None:
        self.store = store
        self.retired: list[str] = []

    def retire(self, app_id: str, expected: Any) -> None:
        self.retired.append(app_id)
        with self.store.transaction() as conn:
            conn.execute("UPDATE apps SET state = 'removed' WHERE app_id = ?", (app_id,))

    def list_apps(self) -> list[dict[str, Any]]:
        return [dict(r) for r in self.store.query("SELECT app_id, state FROM apps")]

    def current(self, app_id: str) -> Any:
        return SimpleNamespace(
            source=SimpleNamespace(name=app_id.title(), description="", collections=[])
        )


class Records:
    def __init__(self) -> None:
        self.dropped: list[str] = []

    def drop(self, app_id: str) -> None:
        self.dropped.append(app_id)

    def store(self, app_id: str) -> Any:
        return SimpleNamespace(counts=lambda: {})


class World:
    """Two modules with everything a module accumulates, in a data directory of their own."""

    def __init__(self, tmp_path: Path) -> None:
        self.data = tmp_path / "data"
        for name in ("apps", "versions", "builds", "artifacts"):
            (self.data / name).mkdir(parents=True)
        self.store = ControlStore(self.data / "control.sqlite")
        for script in (REGISTRY_SCHEMA, ASSISTANT_SCHEMA, CREATION_SCHEMA):
            self.store.execute_script(script)
        self.store.add_missing_columns("apps", _APP_COLUMNS)
        self.store.add_missing_columns("app_releases", _RELEASE_COLUMNS)
        self.store.add_missing_columns("conversations", {"change_of": "TEXT", "session_id": "TEXT"})
        self.store.add_missing_columns("creations", {"change_of": "TEXT", "result_json": "TEXT"})
        self.store.execute_script(
            """CREATE TABLE IF NOT EXISTS app_schedules (app_id TEXT, schedule_id TEXT);
               CREATE TABLE IF NOT EXISTS module_connections (app_id TEXT, source_app_id TEXT);
               CREATE TABLE IF NOT EXISTS nudges (nudge_id TEXT, text TEXT, module TEXT);
               CREATE TABLE IF NOT EXISTS repairs (repair_id TEXT, app_id TEXT, run_id TEXT);"""
        )
        self.profile = ProfileService(self.store)
        self.projects = ProjectService(self.store)
        self.sessions = SessionService(self.store)
        self.registry = Registry(self.store)
        self.records = Records()
        self.purge = ModulePurge(
            self.store,
            registry=self.registry,
            records=self.records,
            coordinator=SimpleNamespace(runs_in_flight=lambda: [], cancel=lambda _r: None),
            creations=None,
            data_dir=self.data,
            versions_root=self.data / "versions",
            builds_root=self.data / "builds",
            apps_root=self.data / "apps",
            artifacts_root=self.data / "artifacts",
        )

    def module(self, app_id: str, *, location: Path | None = None) -> None:
        version_dir = location or self.data / "versions" / f"ver_{app_id}"
        (version_dir / "src").mkdir(parents=True, exist_ok=True)
        sealed = version_dir / "src" / "handlers.py"
        sealed.write_text("def add(ctx):\n    return {}\n")
        sealed.chmod(0o444)
        (version_dir / "src").chmod(0o555)
        (self.data / "apps" / app_id).mkdir(exist_ok=True)
        (self.data / "apps" / app_id / "records.sqlite").write_text("records")
        (self.data / "builds" / f"build_{app_id}" / "attempt-1").mkdir(parents=True)
        with self.store.transaction() as conn:
            conn.execute(
                """INSERT INTO apps(app_id, name, description, created_at, updated_at,
                   current_version_id, current_release_id, origin, state)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    app_id,
                    app_id.title(),
                    "",
                    NOW,
                    NOW,
                    f"ver_{app_id}",
                    f"rel_{app_id}",
                    "created",
                    "active",
                ),
            )
            conn.execute(
                """INSERT INTO app_versions(version_id, app_id, package_sha256, source_json,
                   dependency_manifest_json, dependency_manifest_sha256, runtime_profile_id,
                   location_ref, validation_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"ver_{app_id}",
                    app_id,
                    "sha",
                    "{}",
                    "{}",
                    "sha",
                    "prof",
                    str(version_dir),
                    "{}",
                    NOW,
                ),
            )
            conn.execute(
                "INSERT INTO app_releases(release_id, app_id, version_id, kind, created_at)"
                " VALUES (?,?,?,?,?)",
                (f"rel_{app_id}", app_id, f"ver_{app_id}", "activated", NOW),
            )
            conn.execute(
                """INSERT INTO conversations(conversation_id, state, route_id, created_at,
                   updated_at) VALUES (?,?,?,?,?)""",
                (f"conv_{app_id}", "briefed", "fake", NOW, NOW),
            )
            conn.execute(
                """INSERT INTO conversation_turns(turn_id, conversation_id, sequence, role, kind,
                   content_json, created_at) VALUES (?,?,?,?,?,?,?)""",
                (f"ct_{app_id}", f"conv_{app_id}", 1, "user", "request", "{}", NOW),
            )
            for creation_id, conversation_id in (
                (f"create_{app_id}", f"conv_{app_id}"),
                (f"fix_{app_id}", "repair:run_x"),
            ):
                conn.execute(
                    """INSERT INTO creations(creation_id, conversation_id, brief_id,
                       brief_revision, app_id, state, build_id, history_json, created_at,
                       updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        creation_id,
                        conversation_id,
                        "b",
                        1,
                        app_id,
                        "active",
                        f"build_{app_id}",
                        "[]",
                        NOW,
                        NOW,
                    ),
                )
            conn.execute("INSERT INTO app_schedules VALUES (?, 'daily')", (app_id,))
            conn.execute(
                "INSERT INTO nudges VALUES (?, 'empty since made', ?)", (f"n_{app_id}", app_id)
            )
            conn.execute("INSERT INTO repairs VALUES (?, ?, 'run_x')", (f"r_{app_id}", app_id))
        run = self.store.create_run(
            workspace_id="ws",
            owner=AppOwner(app_id=app_id, release_id=f"rel_{app_id}", action_id="sync"),
            origin=RunOrigin.USER,
            snapshot=ExecutionSnapshot(
                worker_profile="app",
                input_digest="sha256:" + "0" * 64,
                limits=RunLimits(timeout_seconds=60),
            ),
            input_payload={},
        )
        self.store.transition(
            run.run_id,
            expected_states={RunState.QUEUED},
            new_state=RunState.RUNNING,
            event_kind="run.started",
            payload={},
        )
        self.store.transition(
            run.run_id,
            expected_states={RunState.RUNNING},
            new_state=RunState.SUCCEEDED,
            event_kind="run.succeeded",
            payload={},
            output={"ok": True},
        )

    def count(self, table: str, where: str = "1=1", params: tuple[Any, ...] = ()) -> int:
        return int(
            self.store.query(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params)[0]["n"]
        )


def card(world: World, session_id: str, said: str, reply: str, **detail: Any) -> None:
    world.sessions.append(session_id, "user", said)
    world.sessions.append(session_id, "alpha", reply, kind="work", detail=detail)


def test_everything_of_the_module_goes_and_nothing_of_another(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.module("jobs")
    world.module("diet")
    with world.store.transaction() as conn:
        conn.execute("INSERT INTO module_connections VALUES ('diet', 'jobs')")
    project = world.projects.create("Job hunt")
    world.projects.file_module("jobs", project.project_id)
    world.profile.claim(
        "target_roles", "backend", provenance="module", source="jobs", accepted=True
    )
    world.profile.claim("salary", "90k", provenance="module", source="jobs", accepted=False)

    result = world.purge.purge("jobs", "rel_jobs")

    assert result["state"] == "removed" and world.registry.retired == ["jobs"]
    assert world.records.dropped == ["jobs"]
    for table, column in (
        ("apps", "app_id"),
        ("app_versions", "app_id"),
        ("app_releases", "app_id"),
        ("app_schedules", "app_id"),
        ("repairs", "app_id"),
        ("creations", "app_id"),
        ("nudges", "module"),
    ):
        assert world.count(table, f"{column} = ?", ("jobs",)) == 0, table
        assert world.count(table, f"{column} = ?", ("diet",)) >= 1, table
    assert world.count("conversations", "conversation_id = 'conv_jobs'") == 0
    assert world.count("conversation_turns", "conversation_id = 'conv_jobs'") == 0
    assert world.count("conversations", "conversation_id = 'conv_diet'") == 1
    assert world.count("module_connections") == 0, "a link to a module that is gone is gone"
    assert world.count("runs") == 1 and world.count("run_events") == 3
    assert world.projects.get(project.project_id).modules == []
    # The person's own facts stay; what the module had only suggested is turned down.
    assert world.profile.get("target_roles").value == "backend"
    assert world.profile.suggestions() == []
    # On disk: the module's records, versions (sealed read-only) and builds are gone.
    assert not (world.data / "apps" / "jobs").exists()
    assert not (world.data / "versions" / "ver_jobs").exists()
    assert not (world.data / "builds" / "build_jobs").exists()
    assert (world.data / "apps" / "diet" / "records.sqlite").is_file()
    assert (world.data / "versions" / "ver_diet" / "src" / "handlers.py").is_file()
    assert result["deleted"]["files"] == 3


def test_sessions_lose_what_was_about_the_module_and_keep_the_rest(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.module("jobs")
    world.module("diet")
    own = world.sessions.create(focus_app_id="jobs")
    card(world, own.session_id, "the search is not working", "Fixed.", kind="fix", app_id="jobs")
    shared = world.sessions.create()
    card(
        world,
        shared.session_id,
        "make me a job tracker for backend roles",
        "I've started making that.",
        kind="build",
        conversation_id="conv_jobs",
    )
    card(world, shared.session_id, "log two eggs", "Logged.", kind="run", app_id="diet")
    card(
        world,
        shared.session_id,
        "open the job tracker",
        "Opening.",
        kind="open",
        open={"app_id": "jobs"},
    )
    world.sessions.append(shared.session_id, "user", "thanks")
    world.sessions.append(shared.session_id, "alpha", "Any time.")
    world.sessions.update(shared.session_id, summary="They made a job tracker and logged eggs.")
    only = world.sessions.create()
    card(world, only.session_id, "refresh my job tracker", "Done.", kind="run", app_id="jobs")

    world.purge.purge("jobs")

    with pytest.raises(OperationFailed):
        world.sessions.get(own.session_id)
    with pytest.raises(OperationFailed):
        world.sessions.get(only.session_id)  # nothing was left in it
    kept = world.sessions.get(shared.session_id)
    assert [t.text for t in kept.turns] == ["log two eggs", "Logged.", "thanks", "Any time."]
    assert kept.summary is None, "notes that may mention the module are not carried forward"
    assert kept.title == "log two eggs"
    assert world.sessions.search("job tracker backend") == []
    assert world.sessions.search("eggs")
    memory = world.sessions.memory_text(shared.session_id, "what do I have?")
    assert "job" not in memory.lower()


def test_the_assistant_is_told_nothing_about_a_module_that_is_gone(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.module("jobs")
    world.module("diet")
    packer = ContextPacker(world.profile, world.registry, world.records, world.store)
    before = packer.build("my linkedin connections")
    assert "sync in Jobs (ran)" in before and "sync in Diet (ran)" in before
    world.purge.purge("jobs")
    # The registry fake lists what is left; the pack names only modules the person has now.
    world.registry.list_apps = lambda: [{"app_id": "diet", "state": "active"}]  # type: ignore[method-assign]
    after = packer.build("my linkedin connections")
    assert "Jobs" not in after and "sync in Diet (ran)" in after


def test_only_alphas_own_data_directory_is_ever_deleted_from(tmp_path: Path) -> None:
    world = World(tmp_path)
    outside = tmp_path / "elsewhere" / "ver_jobs"
    world.module("jobs", location=outside)
    world.purge.purge("jobs")
    assert world.count("apps") == 0
    assert (outside / "src" / "handlers.py").is_file(), "a path outside the data directory stays"
    assert world.purge._rmtree(world.data) == 0 and world.data.is_dir()


def test_modules_taken_out_of_use_earlier_can_be_deleted_for_good(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.module("jobs")
    world.module("diet")
    world.registry.retire("jobs", None)
    assert [m["app_id"] for m in world.purge.leftovers()] == ["jobs"]
    deleted = world.purge.purge_leftovers()
    assert [d["app_id"] for d in deleted] == ["jobs"]
    assert world.purge.leftovers() == [] and world.count("apps") == 1
    with pytest.raises(OperationFailed):
        world.purge.purge("jobs")
    assert json.dumps(deleted)  # the report is plain data
