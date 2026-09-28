"""Worker ⇄ Core capability calls (Current Release Specification §7, Capability Protocol).

An App worker has no network path to Core and no credentials of its own. It writes one JSON
line per call on its stdout and reads the reply on its stdin; the channel is the supervised
process pipe and every call also carries the per-run workload token Core issued at launch.
Core supplies the acting owner; nothing in a call can name one.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from alpha_contracts.records import FieldSpec
from alpha_contracts.runs import ContractModel

# Version of the worker ⇄ Core message format. The SDK carries its own copy (it is standard
# library only), held equal by packages/app-sdk/tests/test_contract_sync.py.
WORKER_PROTOCOL_VERSION = 1

OPERATIONS: frozenset[str] = frozenset(
    {
        "records.get",
        "records.query",
        "records.aggregate",
        "records.create",
        "records.update",
        "records.correct",
        "records.delete",
        "records.batch",
        "artifacts.create",
        "artifacts.read",
        "artifacts.get",
        "models.structured",
        "http.get",
        "http.search",
        "profile.get",
        "profile.all",
        "profile.set",
        "profile.suggest",
        "modules.list",
        "modules.query",
        "modules.get",
    }
)


class CapabilityCall(ContractModel):
    kind: Literal["call"] = "call"
    call_id: str = Field(min_length=1, max_length=32)
    token: str = Field(min_length=16, max_length=128)
    operation: str = Field(min_length=1, max_length=64)
    version: Literal[1] = 1
    args: dict[str, Any] = Field(default_factory=dict)


# The capability protocol's failure classes (Current Release Specification §7). Core raises
# them; the SDK keeps its own standard-library copy, held equal by a sync test.
CapabilityErrorCode = Literal[
    "invalid_input",
    "not_found",
    "conflict",
    "forbidden",
    "unauthenticated",
    "limit_exceeded",
    "unavailable",
    "timed_out",
    "internal_error",
]


class CapabilityError(ContractModel):
    code: CapabilityErrorCode
    message: str = Field(max_length=2000)
    details: dict[str, Any] = Field(default_factory=dict)


class CapabilityReply(ContractModel):
    kind: Literal["reply"] = "reply"
    call_id: str
    status: Literal["completed", "failed"]
    result: Any = None
    error: CapabilityError | None = None


class StructuredModelCall(ContractModel):
    """A bounded structured model call. The output shape is declared with record field specs so
    every value is range/choice checked; the result is labelled an estimate."""

    instruction: str = Field(min_length=1, max_length=4000)
    input: dict[str, Any] = Field(default_factory=dict)
    fields: list[FieldSpec] = Field(min_length=1, max_length=16)


class ModelEstimate(ContractModel):
    call_id: str
    output: dict[str, Any]
    label: Literal["estimate"] = "estimate"
    route: str
    model: str
    created_at: datetime
