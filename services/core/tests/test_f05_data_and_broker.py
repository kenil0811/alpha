"""In-process tests of the F05 trusted services on real SQLite: value normalization, query
compilation, and broker authentication across two concurrently granted runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alpha.artifacts.service import ArtifactService
from alpha.capabilities.errors import OperationFailed
from alpha.data.query import bucket_value, compile_filter
from alpha.data.store import RecordService, WriteContext
from alpha.data.values import normalize
from alpha.execution.broker import CapabilityBroker, RunGrant
from alpha.models.gateway import ModelGateway
from alpha.models.runtime import AppModelService
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from alpha_contracts.records import CollectionSchema, CreateRecord, FieldSpec, RecordQuery
from alpha_contracts.runs import RunOrigin

SCHEMA = CollectionSchema.model_validate(
    {
        "name": "items",
        "fields": [
            {"name": "title", "kind": "text", "required": True},
            {"name": "at", "kind": "datetime"},
            {"name": "n", "kind": "integer", "minimum": 0},
        ],
    }
)


def test_datetime_normalization_is_fixed_width_utc() -> None:
    spec = FieldSpec(name="at", kind="datetime")  # type: ignore[arg-type]
    assert normalize(spec, "2026-09-25T04:00:00+05:30", where="") == "2026-09-24T22:30:00.000000Z"
    assert normalize(spec, "2026-09-25T04:00:00.5Z", where="") == "2026-09-25T04:00:00.500000Z"
    with pytest.raises(OperationFailed):
        normalize(spec, "2026-09-25T04:00:00", where="")


def test_integer_rules() -> None:
    spec = FieldSpec(name="n", kind="integer", minimum=0)  # type: ignore[arg-type]
    assert normalize(spec, 3.0, where="") == 3
    for bad in (True, 2.5, -1, "3", float("inf")):
        with pytest.raises(OperationFailed):
            normalize(spec, bad, where="")


def test_filters_compile_to_bound_parameters_only() -> None:
    query = RecordQuery.model_validate(
        {
            "collection": "items",
            "where": {
                "any": [
                    {"field": "title", "op": "contains", "value": "'; DROP TABLE records; --"},
                    {"field": "n", "op": "in", "value": [1, 2]},
                ]
            },
        }
    )
    sql, params = compile_filter(SCHEMA, query.where)
    assert "DROP" not in sql and "'; DROP TABLE records; --" in params
    assert sql.count("?") == len(params) == 3


def test_bucket_uses_the_named_timezone() -> None:
    assert (
        bucket_value("2026-09-25T20:00:00.000000Z", "day", "Asia/Kolkata", "datetime")
        == "2026-09-26"
    )
    assert (
        bucket_value("2026-09-25T20:00:00.000000Z", "day", "America/New_York", "datetime")
        == "2026-09-25"
    )
    assert bucket_value("2026-09-24", "week", "UTC", "date") == "2026-09-21"
    assert bucket_value("2026-09-24", "month", "UTC", "date") == "2026-09"


def test_batch_rolls_back_on_a_late_failure(tmp_path: Path) -> None:
    store = RecordService(tmp_path / "apps").store("demo-app")
    store.register_collections([SCHEMA])
    ctx = WriteContext(run_id="run_1", allow_correction=False, resolve_estimate=None)
    with pytest.raises(OperationFailed) as excinfo:
        store.apply(
            [
                CreateRecord(collection="items", values={"title": "a"}),
                CreateRecord(collection="items", values={"title": "b"}),
                CreateRecord(collection="items", values={"title": "c", "n": -5}),
            ],
            ctx,
        )
    assert excinfo.value.details["operation_index"] == 2
    assert store.counts() == {}


@pytest.fixture
def broker(tmp_path: Path) -> tuple[CapabilityBroker, ControlStore]:
    control = ControlStore(tmp_path / "control.sqlite")
    records = RecordService(tmp_path / "apps")
    for app in ("app-a", "app-b"):
        records.store(app).register_collections([SCHEMA])
    gateway = ModelGateway(control, frozenset({"fake"}))
    models = AppModelService(control, gateway, StructuredInference(gateway), "fake")
    artifacts = ArtifactService(control, tmp_path / "artifacts")
    return CapabilityBroker(control, records, artifacts, models), control


def grant(run_id: str, app_id: str, capabilities: set[str]) -> RunGrant:
    return RunGrant(
        run_id=run_id,
        app_id=app_id,
        action_id="act",
        version_id="ver_x",
        package_sha256="0" * 64,
        capabilities=frozenset(capabilities),
        origin=RunOrigin.USER,
        timezone="UTC",
    )


def call(token: str, operation: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "call", "call_id": "c1", "token": token, "operation": operation, "args": args}


def test_a_live_token_only_works_on_its_own_runs_pipe(
    broker: tuple[CapabilityBroker, ControlStore],
) -> None:
    service, _ = broker
    token_a = service.issue(grant("run_a", "app-a", {"records"}))
    token_b = service.issue(grant("run_b", "app-b", {"records"}))
    assert token_a != token_b
    created = service.handle(
        "run_a", call(token_a, "records.create", {"collection": "items", "values": {"title": "a"}})
    )
    assert created["status"] == "completed"
    record_id = created["result"]["id"]
    # B's live token on A's pipe, and A's token on B's pipe, are both refused.
    for channel, token in (("run_a", token_b), ("run_b", token_a)):
        reply = service.handle(
            channel, call(token, "records.get", {"collection": "items", "id": record_id})
        )
        assert reply["error"]["code"] == "unauthenticated"
        assert "different run" in reply["error"]["message"]
    # B, with its own valid token, cannot see A's record.
    reply = service.handle(
        "run_b", call(token_b, "records.get", {"collection": "items", "id": record_id})
    )
    assert reply["error"]["code"] == "not_found"
    service.revoke("run_a")
    reply = service.handle("run_a", call(token_a, "records.query", {"collection": "items"}))
    assert reply["error"]["code"] == "unauthenticated"


def test_undeclared_families_and_malformed_calls(
    broker: tuple[CapabilityBroker, ControlStore],
) -> None:
    service, _ = broker
    token = service.issue(grant("run_c", "app-a", {"records"}))
    reply = service.handle(
        "run_c", call(token, "models.structured", {"instruction": "x", "fields": []})
    )
    assert reply["error"]["code"] == "forbidden"
    reply = service.handle("run_c", {"kind": "call", "call_id": "c2", "operation": "records.get"})
    assert reply["error"]["code"] == "invalid_input"
    reply = service.handle(
        "run_c", call(token, "records.get", {"collection": "items", "id": "x", "app_id": "app-b"})
    )
    assert reply["error"]["code"] == "invalid_input"


def test_tokens_from_a_previous_core_are_revoked(
    broker: tuple[CapabilityBroker, ControlStore],
) -> None:
    service, control = broker
    token = service.issue(grant("run_d", "app-a", {"records"}))
    assert service.revoke_all_on_startup() == 1
    reply = service.handle("run_d", call(token, "records.query", {"collection": "items"}))
    assert reply["error"]["code"] == "unauthenticated"
    rows = control.query("SELECT token_sha256 FROM broker_tokens")
    assert rows and all(token not in row["token_sha256"] for row in rows)
