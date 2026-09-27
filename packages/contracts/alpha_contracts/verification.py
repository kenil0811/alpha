"""Candidate verification (Current Release Specification §4, Implementation Blueprint §6).

A ValidationPlan is written independently of the builder, before generation: behaviour scenarios
run the candidate's real actions against a disposable preview store, and an optional UI plan
drives the candidate's rendered screen. The builder may read the plan; nothing it writes can
change it.

A VerificationReport records every check against the exact sealed bytes. Its verdict is derived,
not asserted: a report whose `passed` disagrees with its own checks does not validate, so one
aggregate boolean can never override a failed or skipped required check.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from alpha_contracts.builds import BuildResultStatus
from alpha_contracts.profiles import Sha256Hex
from alpha_contracts.records import Filter
from alpha_contracts.runs import ContractModel

STEP_ID_PATTERN = r"^[a-z][a-z0-9_]{0,47}$"

# Values in plan steps may be literal JSON or one of two placeholders, resolved by the runner:
#   {"$ref": "<step id>.output.<key>[.<key>...]"}  a value an earlier invoke step returned
#   {"$today": <days offset>}                       an ISO date in the preview's timezone


class InvokeStep(ContractModel):
    """Run one declared action through the platform and check its outcome."""

    kind: Literal["invoke"] = "invoke"
    id: str = Field(pattern=STEP_ID_PATTERN)
    action: str = Field(min_length=1, max_length=64)
    input: dict[str, Any] = Field(default_factory=dict)
    expect: Literal["succeeded", "failed"] = "succeeded"
    output: dict[str, Any] | None = None
    exact: bool = False
    # How the platform's model service behaves during this step. Anything but "normal" makes every
    # model call in the step fail the way a real failure would, so a plan can require an honest
    # outcome (a refusal, or the estimated value left unknown) instead of an invented number.
    model: Literal["normal", "unavailable", "malformed", "timeout"] = "normal"


class RecordsStep(ContractModel):
    """Read the preview store directly (never through the candidate) and check what persisted."""

    kind: Literal["records"] = "records"
    id: str = Field(pattern=STEP_ID_PATTERN)
    collection: str = Field(min_length=1, max_length=48)
    where: Filter | None = None
    count: int | None = Field(default=None, ge=0)
    includes: list[dict[str, Any]] = Field(default_factory=list, max_length=20)


PlanStep = Annotated[InvokeStep | RecordsStep, Field(discriminator="kind")]


class Scenario(ContractModel):
    id: str = Field(pattern=STEP_ID_PATTERN)
    description: str = Field(min_length=1, max_length=500)
    steps: list[PlanStep] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _unique_steps(self) -> Scenario:
        ids = [s.id for s in self.steps]
        if len(set(ids)) != len(ids):
            raise ValueError(f"scenario {self.id} repeats a step id")
        return self


class UiStep(ContractModel):
    """One user action on the rendered screen, addressed the way a person would: by the visible
    label of a field or the name of a button."""

    kind: Literal["fill", "press", "click", "select", "check"]
    label: str | None = Field(default=None, max_length=120)
    text: str | None = Field(default=None, max_length=500)
    key: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _shape(self) -> UiStep:
        if self.kind in ("fill", "select") and (self.label is None or self.text is None):
            raise ValueError(f"a {self.kind} step needs a label and text")
        if self.kind in ("click", "check") and self.label is None:
            raise ValueError(f"a {self.kind} step needs a label")
        if self.kind == "press" and self.key is None:
            raise ValueError("a press step needs a key")
        return self


class UiPlan(ContractModel):
    """The screen's primary interaction and what it must visibly and durably do."""

    primary: list[UiStep] = Field(min_length=1, max_length=12)
    saved: RecordsStep | None = None
    shows: list[str] = Field(default_factory=list, max_length=10)
    seed: list[InvokeStep] = Field(default_factory=list, max_length=20)
    seed_shows: list[str] = Field(default_factory=list, max_length=10)


class ValidationPlan(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    # Empty only as a preliminary plan while the full checks are still being written; a
    # build is never verified against an empty plan.
    scenarios: list[Scenario] = Field(default_factory=list, max_length=20)
    ui: UiPlan | None = None

    @model_validator(mode="after")
    def _unique_scenarios(self) -> ValidationPlan:
        ids = [s.id for s in self.scenarios]
        if len(set(ids)) != len(ids):
            raise ValueError("scenario ids must be unique")
        return self


class CheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class CheckResult(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    stage: str = Field(min_length=1, max_length=32)
    required: bool = True
    status: CheckStatus
    summary: str = Field(max_length=1000)
    detail: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=20)


class DependencyQualificationRequest(ContractModel):
    """A bounded request to qualify a package outside the installed profile. Recording it never
    changes a shared environment; a new profile must be built and qualified first."""

    package: str = Field(min_length=1, max_length=100)
    version: str | None = Field(default=None, max_length=64)
    found_in: Literal["app.yaml modules", "import"]
    where: str = Field(max_length=300)
    runtime_profile_id: str
    reason: str = Field(max_length=300)


class VerificationReport(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    build_id: str
    attempt_id: str
    attempt_number: int = Field(ge=1)
    lineage: list[str] = Field(min_length=1)
    builder_status: BuildResultStatus
    package_sha256: Sha256Hex | None = None
    version_id: str | None = None
    dependency_manifest_sha256: Sha256Hex | None = None
    runtime_profile_id: str | None = None
    ui_build_profile_id: str | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    checks: list[CheckResult] = Field(default_factory=list)
    supplementary: list[CheckResult] = Field(default_factory=list)
    qualification_requests: list[DependencyQualificationRequest] = Field(default_factory=list)
    unresolved_limits: list[str] = Field(default_factory=list)
    passed: bool

    @staticmethod
    def verdict_of(
        builder_status: BuildResultStatus, package_sha256: str | None, checks: list[CheckResult]
    ) -> bool:
        """Ready only if the builder produced a candidate, the bytes were sealed, and every
        required check ran and passed. A skipped required check blocks readiness."""
        required = [c for c in checks if c.required]
        return (
            builder_status is BuildResultStatus.CANDIDATE
            and package_sha256 is not None
            and bool(required)
            and all(c.status is CheckStatus.PASSED for c in required)
        )

    @model_validator(mode="after")
    def _consistent(self) -> VerificationReport:
        if self.lineage[-1] != self.attempt_id:
            raise ValueError("lineage must end with this attempt")
        if self.passed != self.verdict_of(self.builder_status, self.package_sha256, self.checks):
            raise ValueError("passed contradicts the report's own checks")
        if any(c.required for c in self.supplementary):
            raise ValueError("candidate-authored checks are supplementary, never required")
        return self
