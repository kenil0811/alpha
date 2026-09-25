"""Independent behaviour checks (Prototype_Scope_and_Acceptance F07).

Each scenario of the ValidationPlan runs in a fresh preview: actions go through the real
platform path, and persistence is judged by reading the preview's record store directly, never
by trusting what the candidate says it saved. A handler that returns `{"saved": true}` without
writing a record fails here.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from alpha_contracts.runs import RunState
from alpha_contracts.verification import (
    CheckResult,
    CheckStatus,
    InvokeStep,
    RecordsStep,
    Scenario,
)

from alpha.builds.preview import PreviewPlatform
from alpha.capabilities.errors import OperationFailed


class UnresolvedReference(Exception):
    pass


def today(timezone: str, offset_days: int = 0) -> str:
    local = datetime.now(ZoneInfo(timezone)).date()
    return (local + timedelta(days=offset_days)).isoformat()


def resolve_values(value: Any, outputs: dict[str, Any], timezone: str) -> Any:
    """Replace {"$ref": "step.output.key"} and {"$today": n} placeholders."""
    if isinstance(value, dict):
        if set(value) == {"$ref"} and isinstance(value["$ref"], str):
            step, _, path = value["$ref"].partition(".")
            if step not in outputs:
                raise UnresolvedReference(f"{value['$ref']}: step {step!r} has no output yet")
            current: Any = {"output": outputs[step]}
            for key in path.split("."):
                if not isinstance(current, dict) or key not in current:
                    raise UnresolvedReference(f"{value['$ref']}: no {key!r}")
                current = current[key]
            return current
        if set(value) == {"$today"} and isinstance(value["$today"], int):
            return today(timezone, value["$today"])
        return {k: resolve_values(v, outputs, timezone) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_values(v, outputs, timezone) for v in value]
    return value


def matches(expected: Any, observed: Any, *, exact: bool = False) -> bool:
    """Deep match. Objects match when every expected key matches (all keys, if exact); lists
    match element-wise with the same length; numbers compare by value."""
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return False
        if exact and set(expected) != set(observed):
            return False
        return all(
            k in observed and matches(v, observed[k], exact=exact) for k, v in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(observed, list)
            and len(expected) == len(observed)
            and all(matches(e, o, exact=exact) for e, o in zip(expected, observed, strict=True))
        )
    if isinstance(expected, bool) or isinstance(observed, bool):
        return expected is observed
    if isinstance(expected, int | float) and isinstance(observed, int | float):
        return math.isclose(float(expected), float(observed), rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(expected, date) and isinstance(observed, str):
        return expected.isoformat() == observed
    return bool(expected == observed)


def _check(
    check_id: str, status: CheckStatus, summary: str, detail: dict[str, Any] | None = None
) -> CheckResult:
    return CheckResult(
        id=check_id, stage="behavior", status=status, summary=summary[:1000], detail=detail or {}
    )


def run_invoke(
    preview: PreviewPlatform, step: InvokeStep, outputs: dict[str, Any], check_id: str
) -> CheckResult:
    try:
        payload = resolve_values(step.input, outputs, preview.timezone)
        expected = (
            resolve_values(step.output, outputs, preview.timezone)
            if step.output is not None
            else None
        )
    except UnresolvedReference as exc:
        return _check(check_id, CheckStatus.FAILED, f"the plan could not be applied: {exc}")
    try:
        run = preview.invoke_and_wait(step.action, payload)
    except OperationFailed as exc:
        # Refused before any worker started (unknown action, input rejected by the schema).
        observed = {"refused": exc.as_error()}
        ok = step.expect == "failed"
        return _check(
            check_id,
            CheckStatus.PASSED if ok else CheckStatus.FAILED,
            f"{step.action} was refused: {exc.message}",
            {"input": payload, "expected": step.expect, "observed": observed},
        )
    detail: dict[str, Any] = {
        "action": step.action,
        "input": payload,
        "expect": step.expect,
        "state": run.state.value,
        "run_id": run.run_id,
    }
    if run.state is RunState.SUCCEEDED:
        outputs[step.id] = run.output or {}
        detail["output"] = run.output
    else:
        detail["failure"] = preview.failure_detail(run)
    if step.expect == "failed":
        ok = run.state is RunState.FAILED
        summary = (
            f"{step.action} failed as expected"
            if ok
            else f"{step.action} should have failed but ended {run.state.value}"
        )
        return _check(check_id, CheckStatus.PASSED if ok else CheckStatus.FAILED, summary, detail)
    if run.state is not RunState.SUCCEEDED:
        message = (detail["failure"].get("error") or {}).get("message") or run.terminal_reason
        return _check(
            check_id, CheckStatus.FAILED, f"{step.action} did not succeed: {message}", detail
        )
    if expected is not None:
        detail["expected_output"] = expected
        if not matches(expected, run.output or {}, exact=step.exact):
            return _check(
                check_id,
                CheckStatus.FAILED,
                f"{step.action} returned {run.output!r}, expected "
                f"{'exactly ' if step.exact else ''}{expected!r}",
                detail,
            )
    return _check(check_id, CheckStatus.PASSED, f"{step.action} succeeded as expected", detail)


def run_records(
    preview: PreviewPlatform, step: RecordsStep, outputs: dict[str, Any], check_id: str
) -> CheckResult:
    try:
        records = preview.records_in(step.collection, step.where)
    except OperationFailed as exc:
        return _check(
            check_id,
            CheckStatus.FAILED,
            f"collection {step.collection} could not be read: {exc.message}",
        )
    values = [r.values for r in records]
    detail: dict[str, Any] = {
        "collection": step.collection,
        "count": len(records),
        "values": values[:10],
    }
    problems: list[str] = []
    if step.count is not None and len(records) != step.count:
        problems.append(f"{len(records)} saved, expected {step.count}")
    try:
        wanted = [resolve_values(v, outputs, preview.timezone) for v in step.includes]
    except UnresolvedReference as exc:
        return _check(check_id, CheckStatus.FAILED, f"the plan could not be applied: {exc}", detail)
    for item in wanted:
        if not any(matches(item, v) for v in values):
            problems.append(f"no saved {step.collection} record has {item!r}")
    if wanted:
        detail["includes"] = wanted
    if problems:
        return _check(check_id, CheckStatus.FAILED, "; ".join(problems), detail)
    return _check(
        check_id,
        CheckStatus.PASSED,
        f"{len(records)} {step.collection} record(s) saved as expected",
        detail,
    )


def run_scenario(
    make_preview: Callable[[str], PreviewPlatform],
    install: Callable[[PreviewPlatform], None],
    scenario: Scenario,
) -> list[CheckResult]:
    preview = make_preview(f"scenario-{scenario.id}")
    try:
        install(preview)
        outputs: dict[str, Any] = {}
        results: list[CheckResult] = []
        for step in scenario.steps:
            check_id = f"behavior.{scenario.id}.{step.id}"
            if isinstance(step, InvokeStep):
                result = run_invoke(preview, step, outputs, check_id)
            else:
                result = run_records(preview, step, outputs, check_id)
            results.append(result)
            if result.status is not CheckStatus.PASSED:
                # Later steps depend on earlier ones; report them as not run, not as passed.
                for rest in scenario.steps[scenario.steps.index(step) + 1 :]:
                    results.append(
                        _check(
                            f"behavior.{scenario.id}.{rest.id}",
                            CheckStatus.SKIPPED,
                            f"not run: {check_id} failed",
                        )
                    )
                break
        return results
    finally:
        preview.close()
