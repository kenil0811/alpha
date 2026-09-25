from datetime import UTC, datetime

import pytest
from alpha_contracts.builds import (
    BuildBudget,
    BuildRequest,
    BuildResult,
    BuildResultStatus,
    BuildUsage,
    CostBasis,
    FailureCategory,
)
from pydantic import ValidationError

NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def _request(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "build_id": "build_1",
        "attempt_id": "attempt_1",
        "attempt_number": 1,
        "brief_ref": "brief_1.r1",
        "context_snapshot_ref": "ctx_1",
        "template_profile": "pure-python-0.2",
        "sdk_profile": "none",
        "dependency_profile": "platform-runtime-3.13.9",
        "validation_plan_ref": "plan_1",
        "model_route_ref": "claude-code-cli",
        "budget": {
            "max_turns": 30,
            "max_attempt_seconds": 720,
            "max_total_seconds": 1800,
            "max_repair_attempts": 2,
            "cost_basis": "subscription_unmetered",
        },
        "workspace_lease_ref": "lease_1",
        "deadline": NOW,
    }
    base.update(overrides)
    return base


def test_request_round_trip() -> None:
    request = BuildRequest.model_validate(_request())
    assert request.budget.cost_basis is CostBasis.SUBSCRIPTION_UNMETERED
    assert BuildRequest.model_validate_json(request.model_dump_json()) == request


def test_request_rejects_unknown_authority_fields_and_bad_budget() -> None:
    with pytest.raises(ValidationError):
        BuildRequest.model_validate(_request(provider_api_key="sk-..."))
    with pytest.raises(ValidationError):
        BuildBudget(
            max_turns=0,
            max_attempt_seconds=1,
            max_total_seconds=1,
            max_repair_attempts=0,
            cost_basis=CostBasis.UNAVAILABLE,
        )


def test_result_candidate_requires_valid_digest_when_present() -> None:
    base = {
        "build_id": "build_1",
        "attempt_id": "attempt_1",
        "status": "candidate",
        "harness": "claude-code-cli",
        "model_route_ref": "claude-code-cli",
        "source_package_ref": "builds/build_1/attempt-1/package",
        "source_digest": "sha256:" + "a" * 64,
        "started_at": NOW,
        "finished_at": NOW,
    }
    result = BuildResult.model_validate(base)
    assert result.status is BuildResultStatus.CANDIDATE
    with pytest.raises(ValidationError):
        BuildResult.model_validate({**base, "source_digest": "abc"})
    with pytest.raises(ValidationError):
        BuildResult.model_validate({**base, "status": "ready"})


def test_failed_result_and_usage_cost_basis() -> None:
    usage = BuildUsage(cost_basis=CostBasis.UNAVAILABLE, turns=3)
    assert usage.cost_usd is None
    failed = BuildResult(
        build_id="b",
        attempt_id="a",
        status=BuildResultStatus.FAILED,
        harness="fake",
        model_route_ref="fake",
        failure_category=FailureCategory.HARNESS_ERROR,
        usage=usage,
        started_at=NOW,
        finished_at=NOW,
    )
    assert failed.failure_category is FailureCategory.HARNESS_ERROR
