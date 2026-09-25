"""The VerificationReport's verdict is derived from its checks; it cannot be asserted."""

from __future__ import annotations

from typing import Any

import pytest
from alpha_contracts.verification import (
    CheckResult,
    UiStep,
    ValidationPlan,
    VerificationReport,
)
from pydantic import ValidationError

SHA = "0" * 64


def check(status: str, required: bool = True, check_id: str = "c") -> CheckResult:
    return CheckResult(id=check_id, stage="behavior", status=status, required=required, summary="s")


def report(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "build_id": "b",
        "attempt_id": "a2",
        "attempt_number": 2,
        "lineage": ["a1", "a2"],
        "builder_status": "candidate",
        "package_sha256": SHA,
        "checks": [check("passed")],
        "passed": True,
    }
    return body | overrides


def test_a_consistent_passing_report_validates() -> None:
    assert VerificationReport.model_validate(report()).passed is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"checks": [check("passed"), check("failed", check_id="d")]},
        {"checks": [check("passed"), check("skipped", check_id="d")]},
        {"checks": []},
        {"builder_status": "failed"},
        {"package_sha256": None},
    ],
    ids=["failed-check", "skipped-required", "no-checks", "builder-failed", "not-sealed"],
)
def test_passed_cannot_contradict_the_checks(overrides: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="contradicts"):
        VerificationReport.model_validate(report(**overrides))
    assert VerificationReport.model_validate(report(passed=False, **overrides)).passed is False


def test_advisory_checks_do_not_block_but_supplementary_checks_cannot_be_required() -> None:
    advisory = report(checks=[check("passed"), check("failed", required=False, check_id="d")])
    assert VerificationReport.model_validate(advisory).passed is True
    with pytest.raises(ValidationError, match="supplementary"):
        VerificationReport.model_validate(report(supplementary=[check("passed")]))


def test_lineage_ends_with_the_reported_attempt() -> None:
    with pytest.raises(ValidationError, match="lineage"):
        VerificationReport.model_validate(report(lineage=["a2", "a1"]))


def test_plans_reject_ambiguous_steps() -> None:
    with pytest.raises(ValidationError, match="label and text"):
        UiStep(kind="fill", label="Title")
    with pytest.raises(ValidationError, match="key"):
        UiStep(kind="press")
    step = {"kind": "invoke", "id": "a", "action": "x"}
    scenario = {"id": "s", "description": "d", "steps": [step]}
    with pytest.raises(ValidationError, match="unique"):
        ValidationPlan.model_validate({"scenarios": [scenario, scenario]})
    with pytest.raises(ValidationError, match="repeats"):
        ValidationPlan.model_validate(
            {"scenarios": [{"id": "s", "description": "d", "steps": [step, step]}]}
        )
