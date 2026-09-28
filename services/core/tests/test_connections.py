"""Connections: a module reads another module's declared views, the person can switch each
use off, and relation fields point at another module's records."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.capabilities.errors import OperationFailed
from alpha.context.connections import ConnectionService
from alpha.data.store import RecordService
from alpha.data.views import ViewQueryRequest
from alpha.storage.control_store import ControlStore
from alpha_contracts.apps import AppSource
from pydantic import ValidationError

ACTION = {
    "id": "add",
    "title": "Add",
    "description": "Add one.",
    "handler": "m:add",
    "invocable_from": ["manual"],
    "effect_class": "local_write",
    "capability_requirements": ["records"],
    "input_schema": {"type": "object", "properties": {}},
    "output_schema": {"type": "object"},
}


def source(app_id: str, **extra: Any) -> AppSource:
    data = {
        "contract_version": "0.2",
        "app_id": app_id,
        "name": app_id.title(),
        "description": f"The {app_id} module.",
        "runtime_profile": "p",
        "sdk_version": "1",
        "capabilities": ["records"],
        "collections": [
            {
                "name": "courses",
                "title_field": "title",
                "fields": [{"name": "title", "kind": "text"}, {"name": "grade", "kind": "number"}],
            }
        ],
        "views": [{"id": "courses.all", "collection": "courses", "filterable": ["title"]}],
        "actions": [ACTION],
    }
    data.update(extra)
    return AppSource.model_validate(data)


def test_uses_and_relations_are_declared_together() -> None:
    reader = source(
        "resume",
        capabilities=["records", "connections"],
        uses=[
            {
                "module": "academics",
                "views": ["courses.all"],
                "purpose": "The resume lists courses.",
            }
        ],
        collections=[
            {
                "name": "entries",
                "fields": [
                    {"name": "title", "kind": "text"},
                    {
                        "name": "course",
                        "kind": "relation",
                        "module": "academics",
                        "collection": "courses",
                    },
                ],
            }
        ],
        views=[],
    )
    assert reader.uses[0].module == "academics"
    with pytest.raises(ValidationError, match="connections capability"):
        source("resume", uses=[{"module": "academics", "views": ["courses.all"], "purpose": "x"}])
    with pytest.raises(ValidationError, match="must be listed under uses"):
        source(
            "resume",
            collections=[
                {
                    "name": "e",
                    "fields": [
                        {
                            "name": "c",
                            "kind": "relation",
                            "module": "academics",
                            "collection": "courses",
                        }
                    ],
                }
            ],
            views=[],
        )
    with pytest.raises(ValidationError, match="does not list itself"):
        source(
            "resume",
            capabilities=["records", "connections"],
            uses=[{"module": "resume", "views": ["courses.all"], "purpose": "x"}],
        )


class Registry:
    def __init__(self, sources: dict[str, AppSource]) -> None:
        self.sources = sources

    def list_apps(self) -> list[dict[str, Any]]:
        return [{"app_id": a, "state": "active"} for a in self.sources]

    def current(self, app_id: str) -> Any:
        if app_id not in self.sources:
            raise OperationFailed("not_found", f"no App {app_id!r}", {})
        return SimpleNamespace(source=self.sources[app_id])


def setup(tmp_path: Path) -> tuple[ConnectionService, RecordService]:
    academics = source("academics")
    resume = source(
        "resume",
        capabilities=["records", "connections"],
        uses=[
            {
                "module": "academics",
                "views": ["courses.all"],
                "purpose": "The resume lists courses.",
            }
        ],
    )
    registry = Registry({"academics": academics, "resume": resume})
    records = RecordService(tmp_path / "apps")
    store = records.store("academics")
    store.register_collections(list(academics.collections))
    from alpha.data.store import WriteContext
    from alpha_contracts.records import CreateRecord

    store.apply(
        [CreateRecord(collection="courses", values={"title": "Distributed systems", "grade": 78})],
        WriteContext(run_id="run_seed", allow_correction=True, resolve_estimate=None),
    )
    connections = ConnectionService(
        ControlStore(tmp_path / "control.sqlite"), registry, records, "UTC"
    )
    connections.sync_all()
    return connections, records


def test_a_declared_use_reads_through_the_view_until_switched_off(tmp_path: Path) -> None:
    connections, _ = setup(tmp_path)
    declared = connections.declared("resume")
    assert declared == [
        {
            "module": "academics",
            "name": "Academics",
            "purpose": "The resume lists courses.",
            "views": [{"id": "courses.all", "collection": "courses", "kind": "records"}],
            "enabled": True,
            "installed": True,
        }
    ]
    page = connections.read("resume", "academics", "courses.all", ViewQueryRequest(limit=10))
    assert [r.values["title"] for r in page.records] == ["Distributed systems"]
    assert connections.available("resume")[0]["views"][0]["fields"] == ["title", "grade"]
    picks = connections.pick("resume", "academics", "courses", "distrib")
    assert picks and picks[0]["title"] == "Distributed systems"
    record = connections.get("resume", "academics", "courses", picks[0]["id"])
    assert record.values["grade"] == 78

    connections.set_enabled("resume", "academics", False)
    with pytest.raises(OperationFailed, match="switched off"):
        connections.read("resume", "academics", "courses.all", ViewQueryRequest(limit=10))
    assert connections.available("resume") == []
    with pytest.raises(OperationFailed, match="does not declare"):
        connections.read("academics", "resume", "courses.all", ViewQueryRequest(limit=10))
    with pytest.raises(OperationFailed, match="did not declare view"):
        connections.set_enabled("resume", "academics", True)
        connections.read("resume", "academics", "nope", ViewQueryRequest(limit=10))
