"""Positive and meaningful negative fixtures for the 0.2 run/event contract."""

from datetime import UTC, datetime

import pytest
from alpha_contracts.runs import (
    TERMINAL_RUN_STATES,
    AppOwner,
    ExecutionSnapshot,
    Run,
    RunEvent,
    RunLimits,
    RunOrigin,
    RunState,
    TaskOwner,
)
from pydantic import ValidationError

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + "0" * 64


def _run(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "run_id": "run_1",
        "workspace_id": "ws_local",
        "owner": {
            "kind": "task",
            "task_id": "t1",
            "task_revision_id": "t1r1",
            "attempt_id": "a1",
            "plan_ref": "synthetic:echo",
        },
        "origin": "user",
        "state": "queued",
        "snapshot": {
            "worker_profile": "synthetic",
            "input_digest": DIGEST,
            "limits": {"timeout_seconds": 30},
        },
        "created_at": NOW,
        "updated_at": NOW,
    }
    base.update(overrides)
    return base


def test_task_owner_round_trip() -> None:
    run = Run.model_validate(_run())
    assert isinstance(run.owner, TaskOwner)
    assert run.contract_version == "0.2"
    assert Run.model_validate_json(run.model_dump_json()) == run


def test_app_owner_variant() -> None:
    run = Run.model_validate(
        _run(owner={"kind": "app", "app_id": "a", "release_id": "r", "action_id": "act"})
    )
    assert isinstance(run.owner, AppOwner)


def test_unknown_owner_variant_rejected() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(_run(owner={"kind": "synthetic", "id": "x"}))


def test_unknown_authority_bearing_field_rejected() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(_run(grants=["all"]))


def test_invalid_state_and_origin_rejected() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(_run(state="done"))
    with pytest.raises(ValidationError):
        Run.model_validate(_run(origin="worker"))


def test_wrong_contract_version_rejected() -> None:
    with pytest.raises(ValidationError):
        Run.model_validate(_run(contract_version="0.1"))


def test_snapshot_requires_real_digest_and_bounded_timeout() -> None:
    with pytest.raises(ValidationError):
        ExecutionSnapshot(
            worker_profile="synthetic", input_digest="abc", limits=RunLimits(timeout_seconds=1)
        )
    with pytest.raises(ValidationError):
        RunLimits(timeout_seconds=0)


def test_event_sequence_must_be_positive() -> None:
    RunEvent(event_id="e", run_id="r", sequence=1, kind="run.started", occurred_at=NOW, payload={})
    with pytest.raises(ValidationError):
        RunEvent(
            event_id="e", run_id="r", sequence=0, kind="run.started", occurred_at=NOW, payload={}
        )


def test_terminal_states() -> None:
    assert RunState.SUCCEEDED in TERMINAL_RUN_STATES
    assert RunState.RUNNING not in TERMINAL_RUN_STATES
    assert RunOrigin.USER.value == "user"
