"""Core's side of the worker protocol stays equal to the contract: every failure code has an
HTTP status, and every contract operation reaches a handler in the broker."""

from __future__ import annotations

from pathlib import Path
from typing import Any, get_args

from alpha.artifacts.service import ArtifactService
from alpha.capabilities.errors import HTTP_STATUS
from alpha.context.profile import ProfileService
from alpha.data.store import RecordService
from alpha.execution.broker import CapabilityBroker, RunGrant
from alpha.models.gateway import ModelGateway
from alpha.models.runtime import AppModelService
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from alpha_contracts.broker import OPERATIONS, CapabilityErrorCode
from alpha_contracts.runs import RunOrigin


def test_every_failure_code_has_an_http_status() -> None:
    assert set(HTTP_STATUS) == set(get_args(CapabilityErrorCode))


# Operations that legitimately take no arguments answer with data.
NO_ARGUMENT_OPERATIONS = frozenset({"profile.all"})


def test_the_broker_handles_every_contract_operation(tmp_path: Path) -> None:
    control = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(control, frozenset({"fake"}))
    broker = CapabilityBroker(
        control,
        RecordService(tmp_path / "apps"),
        ArtifactService(control, tmp_path / "artifacts"),
        AppModelService(control, gateway, StructuredInference(gateway), "fake"),
        profile=ProfileService(control),
    )
    families = frozenset(op.split(".", 1)[0] for op in OPERATIONS)
    token = broker.issue(
        RunGrant(
            run_id="run_sync",
            app_id="app-sync",
            action_id="act",
            version_id="ver_x",
            package_sha256="0" * 64,
            capabilities=families,
            origin=RunOrigin.USER,
            timezone="UTC",
        )
    )
    for operation in sorted(OPERATIONS):
        message: dict[str, Any] = {
            "kind": "call",
            "call_id": "c1",
            "token": token,
            "operation": operation,
            "args": {},
        }
        reply = broker.handle("run_sync", message)
        if operation in NO_ARGUMENT_OPERATIONS:
            assert reply["status"] == "completed", (operation, reply)
            continue
        # Empty arguments are refused by the operation's own parser, never as unknown.
        assert reply["status"] == "failed", (operation, reply)
        assert reply["error"]["code"] == "invalid_input", (operation, reply)
        assert "unknown operation" not in reply["error"]["message"], operation
