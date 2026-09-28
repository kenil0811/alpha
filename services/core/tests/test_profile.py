"""Profile facts: append-only claims with provenance, the person's say over each, and the
context pack every assistant turn is assembled from."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.capabilities.errors import OperationFailed
from alpha.context.pack import ContextPacker, keywords
from alpha.context.profile import ProfileService
from alpha.storage.control_store import ControlStore
from alpha_contracts.apps import AppSource
from alpha_contracts.records import FieldKind


def service(tmp_path: Path) -> ProfileService:
    return ProfileService(ControlStore(tmp_path / "control.sqlite"))


def test_a_correction_supersedes_and_the_history_stays_whole(tmp_path: Path) -> None:
    svc = service(tmp_path)
    first = svc.claim("degree", "BSc CS", provenance="person", source="person", accepted=True)
    second = svc.claim("degree", "MSc CS", provenance="person", source="person", accepted=True)
    assert second.supersedes == first.fact_id
    assert [f.value for f in svc.current()] == ["MSc CS"]
    assert [f.value for f in svc.history("degree")] == ["MSc CS", "BSc CS"]
    again = svc.claim("degree", "MSc CS", provenance="person", source="person", accepted=True)
    assert again.fact_id == second.fact_id, "saying the same thing twice records nothing new"


def test_a_suggestion_waits_for_the_person(tmp_path: Path) -> None:
    svc = service(tmp_path)
    hint = svc.claim(
        "skills",
        ["Python", "SQL"],
        provenance="inferred",
        source="academics",
        why="coursework",
        confidence=0.7,
        accepted=False,
    )
    assert svc.get("skills") is None and [s.fact_id for s in svc.suggestions()] == [hint.fact_id]
    duplicate = svc.claim(
        "skills", ["Python", "SQL"], provenance="inferred", source="academics", accepted=False
    )
    assert duplicate.fact_id == hint.fact_id
    accepted = svc.accept(hint.fact_id)
    assert accepted.state == "accepted" and svc.get("skills").value == ["Python", "SQL"]
    assert svc.suggestions() == []
    svc.forget(hint.fact_id)
    assert svc.get("skills") is None
    other = svc.claim("location", "London", provenance="module", source="jobs", accepted=False)
    svc.reject(other.fact_id)
    assert svc.suggestions() == [] and svc.get("location") is None


def test_facts_need_a_value_and_are_bounded(tmp_path: Path) -> None:
    svc = service(tmp_path)
    with pytest.raises(OperationFailed):
        svc.claim("degree", "", provenance="person", source="person", accepted=True)
    with pytest.raises(OperationFailed):
        svc.claim("notes", "x" * 5000, provenance="person", source="person", accepted=True)


def test_the_profile_reads_as_plain_lines_with_sources(tmp_path: Path) -> None:
    svc = service(tmp_path)
    svc.claim("degree", "MSc CS", provenance="person", source="person", accepted=True)
    svc.claim("target_roles", ["backend"], provenance="module", source="job-profile", accepted=True)
    text = svc.as_text()
    assert "- degree: MSc CS (they said so)" in text
    assert '- target roles: ["backend"] (from job-profile)' in text


def test_keywords_drop_filler() -> None:
    assert keywords("Can you refresh my resume with the coursework from this term?") == [
        "refresh",
        "resume",
        "coursework",
        "term",
    ]


class Store:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.queries: list[Any] = []

    def counts(self) -> dict[str, int]:
        return {"assignments": len(self.rows)}

    def query(self, query: Any) -> Any:
        self.queries.append(query)
        return SimpleNamespace(records=[SimpleNamespace(values=r) for r in self.rows])


def test_the_context_pack_carries_facts_modules_relevant_records_and_activity(
    tmp_path: Path,
) -> None:
    svc = service(tmp_path)
    svc.claim("degree", "MSc CS", provenance="person", source="person", accepted=True)
    source = AppSource.model_validate(
        {
            "contract_version": "0.2",
            "app_id": "academics",
            "name": "Academics",
            "description": "Coursework and assignments.",
            "runtime_profile": "p",
            "sdk_version": "1",
            "capabilities": ["records"],
            "collections": [
                {
                    "name": "assignments",
                    "fields": [
                        {"name": "title", "kind": "text"},
                        {"name": "grade", "kind": "number"},
                    ],
                }
            ],
            "actions": [
                {
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
            ],
        }
    )
    registry = SimpleNamespace(
        list_apps=lambda: [{"app_id": "academics", "state": "active"}],
        current=lambda app_id: SimpleNamespace(source=source),
    )
    store = Store([{"title": "Distributed systems coursework", "grade": 78}])
    records = SimpleNamespace(store=lambda app_id: store)
    runs = SimpleNamespace(list_runs=lambda n: [])
    pack = ContextPacker(svc, registry, records, runs).build("refresh my resume with my coursework")
    assert "- degree: MSc CS (they said so)" in pack
    assert "- Academics [academics]: Coursework and assignments. Keeps: assignments (1)." in pack
    assert "- Academics / assignments: title Distributed systems coursework; grade 78" in pack
    assert store.queries and store.queries[0].limit == 4
    assert source.collections[0].fields[0].kind is FieldKind.TEXT
