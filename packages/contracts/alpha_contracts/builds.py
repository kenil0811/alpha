"""Build contracts (Current Release Specification section 4).

BuildRequest is what Core hands a builder attempt; BuildResult is what the attempt returns. A
candidate is not a ready release: validation and sealing happen in Core afterwards. Only Core
changes authoritative build state.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from alpha_contracts.runs import ContractModel


class BuildState(StrEnum):
    QUEUED = "queued"
    BUILDING = "building"
    VALIDATING = "validating"
    REPAIRING = "repairing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_BUILD_STATES: frozenset[BuildState] = frozenset(
    {BuildState.READY, BuildState.FAILED, BuildState.CANCELLED}
)


class BuildResultStatus(StrEnum):
    CANDIDATE = "candidate"
    FAILED = "failed"
    CANCELLED = "cancelled"


class FailureCategory(StrEnum):
    HARNESS_UNAVAILABLE = "harness_unavailable"
    HARNESS_AUTH = "harness_auth"
    HARNESS_ERROR = "harness_error"
    HARNESS_TIMEOUT = "harness_timeout"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_PACKAGE = "no_package"
    INVALID_PACKAGE = "invalid_package"
    VALIDATION_FAILED = "validation_failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    PLATFORM_ERROR = "platform_error"
    DEPENDENCY_UNSUPPORTED = "dependency_unsupported"


class CostBasis(StrEnum):
    PROVIDER_REPORTED = "provider_reported"
    SUBSCRIPTION_UNMETERED = "subscription_unmetered"
    UNAVAILABLE = "unavailable"


class BuildBudget(ContractModel):
    max_turns: int = Field(gt=0, le=200)
    max_attempt_seconds: int = Field(gt=0, le=3600)
    max_total_seconds: int = Field(gt=0, le=7200)
    max_repair_attempts: int = Field(ge=0, le=5)
    max_cost_usd: float | None = Field(default=None, ge=0)
    cost_basis: CostBasis


class BuildRequest(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    build_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    brief_ref: str = Field(min_length=1)
    base_release_ref: str | None = None
    context_snapshot_ref: str = Field(min_length=1)
    template_profile: str = Field(min_length=1)
    sdk_profile: str = Field(min_length=1)
    ui_kit_profile: str | None = None
    dependency_profile: str = Field(min_length=1)
    validation_plan_ref: str = Field(min_length=1)
    model_route_ref: str = Field(min_length=1)
    budget: BuildBudget
    workspace_lease_ref: str = Field(min_length=1)
    deadline: datetime


class BuildUsage(ContractModel):
    input_tokens: int = Field(ge=0, default=0)
    output_tokens: int = Field(ge=0, default=0)
    cache_read_input_tokens: int = Field(ge=0, default=0)
    cache_creation_input_tokens: int = Field(ge=0, default=0)
    turns: int = Field(ge=0, default=0)
    duration_ms: int = Field(ge=0, default=0)
    cost_usd: float | None = Field(default=None, ge=0)
    cost_basis: CostBasis
    models: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BuildDiagnostic(ContractModel):
    level: Literal["info", "warning", "error"]
    code: str = Field(min_length=1)
    message: str


class BuildResult(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    build_id: str = Field(min_length=1)
    attempt_id: str = Field(min_length=1)
    status: BuildResultStatus
    harness: str = Field(min_length=1)
    model_route_ref: str = Field(min_length=1)
    source_package_ref: str | None = None
    source_digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    failure_category: FailureCategory | None = None
    diagnostics: list[BuildDiagnostic] = Field(default_factory=list)
    usage: BuildUsage | None = None
    started_at: datetime
    finished_at: datetime


class BuildEvent(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    event_id: str = Field(min_length=1)
    build_id: str = Field(min_length=1)
    attempt_id: str | None = None
    sequence: int = Field(ge=1)
    kind: str = Field(min_length=1)
    occurred_at: datetime
    payload: dict[str, Any]
