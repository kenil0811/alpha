"""Run, owner and event contracts (Current Release Specification section 6).

These models are the trust-boundary shapes. Unknown fields are rejected, enum values are
closed, and the owner variant is a closed discriminated union.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base for every serialized contract: closed fields, immutable instances."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class AppOwner(ContractModel):
    kind: Literal["app"] = "app"
    app_id: str = Field(min_length=1)
    release_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)


class TaskOwner(ContractModel):
    kind: Literal["task"] = "task"
    task_id: str = Field(min_length=1)
    task_revision_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    plan_ref: str = Field(min_length=1)


RunOwner = Annotated[AppOwner | TaskOwner, Field(discriminator="kind")]


class RunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_CONNECTION = "waiting_connection"
    NEEDS_RECONCILIATION = "needs_reconciliation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


TERMINAL_RUN_STATES: frozenset[RunState] = frozenset(
    {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED, RunState.INTERRUPTED}
)


class RunOrigin(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    UI = "ui"
    TRIGGER = "trigger"
    REPAIR_TEST = "repair_test"


class RunLimits(ContractModel):
    timeout_seconds: int = Field(gt=0, le=3600)


class ExecutionSnapshot(ContractModel):
    """The immutable facts a run was dispatched with. F01 records the narrow synthetic path;
    F05 adds the exact code/dependency identities of generated App computation (never
    re-resolved at invocation); later tickets add grants and provider routes."""

    worker_profile: str = Field(min_length=1)
    input_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    limits: RunLimits
    version_id: str | None = None
    package_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    runtime_profile_id: str | None = None
    dependency_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    capabilities: list[str] = Field(default_factory=list)
    timezone: str | None = None


class Run(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    run_id: str = Field(min_length=1)
    workspace_id: str = Field(min_length=1)
    owner: RunOwner
    origin: RunOrigin
    state: RunState
    snapshot: ExecutionSnapshot
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    output: dict[str, Any] | None = None
    terminal_reason: str | None = None
    retry_of: str | None = None
    latest_sequence: int = Field(ge=0, default=0)


class RunEvent(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    sequence: int = Field(ge=1)
    kind: str = Field(min_length=1)
    occurred_at: datetime
    payload_schema_version: Literal["0.2"] = "0.2"
    payload: dict[str, Any]
    step_key: str | None = None
