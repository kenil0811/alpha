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

from alpha_contracts.records import Filter
from alpha_contracts.runs import Run, RunState
from alpha_contracts.verification import (
    CheckResult,
    CheckStatus,
    InvokeStep,
    RecordsStep,
    Scenario,
    ValidationPlan,
)
from pydantic import TypeAdapter

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


_FILTER: TypeAdapter[Filter] = TypeAdapter(Filter)


def resolve_filter(where: Filter | None, outputs: dict[str, Any], timezone: str) -> Filter | None:
    """A records step's filter with its placeholders resolved, like its expected values. Found in
    M1-R07: a plan filtering on {"$today": 0} reached the store unresolved, every read of the
    collection failed with "filter on date must be text", and no repair could pass."""
    if where is None:
        return None
    dumped = _FILTER.dump_python(where, mode="json", by_alias=True)
    return _FILTER.validate_python(resolve_values(dumped, outputs, timezone))


def is_any(value: Any) -> bool:
    """`{"$any": true}`: the key must be present with a non-null value; which value is free."""
    return isinstance(value, dict) and set(value) == {"$any"} and value["$any"] is True


def matches(expected: Any, observed: Any, *, exact: bool = False) -> bool:
    """Deep match. Objects match when every expected key matches (all keys, if exact); lists
    match element-wise with the same length; numbers compare by value; `{"$any": true}`
    matches any non-null value; an expected null matches an absent or empty value (unknown)."""
    if is_any(expected):
        return observed is not None
    if isinstance(expected, dict):
        if not isinstance(observed, dict):
            return False
        if exact and set(expected) != set(observed):
            return False
        # An expected null means "unknown": the value is absent or empty.
        return all(
            (observed.get(k) is None)
            if v is None
            else (k in observed and matches(v, observed[k], exact=exact))
            for k, v in expected.items()
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
    # An expected refusal must also leave stored data as it was (M1 review finding F05), even
    # when the plan does not read the collections back afterwards.
    kept = [c.name for c in preview.app.source.collections] if step.expect == "failed" else []
    before = _snapshot(preview, kept)
    preview.models.fault = step.model
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
    finally:
        preview.models.fault = "normal"
    detail: dict[str, Any] = {
        "action": step.action,
        "input": payload,
        "expect": step.expect,
        "state": run.state.value,
        "run_id": run.run_id,
    }
    if step.model != "normal":
        detail["model"] = step.model
    if run.state is RunState.SUCCEEDED:
        outputs[step.id] = run.output or {}
        detail["output"] = run.output
    else:
        detail["failure"] = preview.failure_detail(run)
    if step.expect == "failed":
        after = _snapshot(preview, kept)
        changed = [name for name in kept if before.get(name) != after.get(name)]
        ok = run.state is RunState.FAILED and not changed
        # With the model made unavailable, the point of the check is that nothing made up is
        # stored. A run that ends succeeded with a plain message and stores nothing is the other
        # honest outcome the planner is told to accept (found live: a plan wrote "failed", the
        # builder chose the message, and the module was rejected for the better behaviour).
        if step.model != "normal" and run.state is RunState.SUCCEEDED and not changed:
            ok = True
            summary = (
                f"{step.action} handled the unavailable model honestly: "
                "it ended succeeded and stored nothing"
            )
        elif run.state is not RunState.FAILED:
            summary = f"{step.action} should have failed but ended {run.state.value}"
        elif changed:
            detail["changed"] = changed
            summary = (
                f"{step.action} failed as expected but changed stored data in {', '.join(changed)}"
            )
        else:
            summary = f"{step.action} failed as expected"
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
        where = resolve_filter(step.where, outputs, preview.timezone)
    except UnresolvedReference as exc:
        return _check(
            check_id,
            CheckStatus.FAILED,
            f"the plan could not be applied: {exc}",
            {"plan_defect": True},
        )
    try:
        records = preview.records_in(step.collection, where)
    except OperationFailed as exc:
        # A filter the store cannot compile is the plan's fault, not the builder's: no repair
        # can fix it, so the build stops instead of spending every attempt on it.
        defect = exc.code == "invalid_input" and "no collection" not in exc.message
        return _check(
            check_id,
            CheckStatus.FAILED,
            f"collection {step.collection} could not be read: {exc.message}",
            {"plan_defect": True} if defect else None,
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


# ----- model failure (M1 review finding F04) -------------------------------------------------

MODEL_FAULTS = ("unavailable", "malformed", "timeout")
_Snapshot = dict[str, dict[str, tuple[int, dict[str, Any], dict[str, Any]]]]


def _snapshot(preview: PreviewPlatform, collections: list[str]) -> _Snapshot:
    found: _Snapshot = {}
    for name in collections:
        try:
            records = preview.records_in(name)
        except OperationFailed:
            records = []
        found[name] = {
            r.id: (r.revision, dict(r.values), {k: v.source for k, v in r.provenance.items()})
            for r in records
        }
    return found


def _changed(
    before: _Snapshot, after: _Snapshot
) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    """(collection, values, provenance sources) of every record the step created or changed."""
    out = []
    for name, records in after.items():
        for rid, (revision, values, sources) in records.items():
            if before.get(name, {}).get(rid, (0,))[0] != revision:
                out.append((name, values, sources))
    return out


def _run_until(
    preview: PreviewPlatform, scenario: Scenario, index: int, model: str
) -> tuple[Run | None, _Snapshot, _Snapshot, dict[str, Any]]:
    """Run a scenario's steps before `index` as written, then that invoke step with the model
    service behaving as `model`. Returns the step's run (None if an earlier step did not pass)
    and the stored records around it."""
    collections = [c.name for c in preview.app.source.collections]
    outputs: dict[str, Any] = {}
    for step in scenario.steps[:index]:
        if isinstance(step, InvokeStep):
            result = run_invoke(preview, step, outputs, "model.prefix")
        else:
            result = run_records(preview, step, outputs, "model.prefix")
        if result.status is not CheckStatus.PASSED:
            return None, {}, {}, outputs
    target = scenario.steps[index]
    assert isinstance(target, InvokeStep)
    before = _snapshot(preview, collections)
    try:
        payload = resolve_values(target.input, outputs, preview.timezone)
    except UnresolvedReference:
        return None, before, before, outputs
    preview.models.fault = model
    try:
        run = preview.invoke_and_wait(target.action, payload)
    except OperationFailed:
        return None, before, _snapshot(preview, collections), outputs
    finally:
        preview.models.fault = "normal"
    return run, before, _snapshot(preview, collections), outputs


def run_model_failures(
    make_preview: Callable[[str], PreviewPlatform],
    install: Callable[[PreviewPlatform], None],
    plan: ValidationPlan,
    actions: list[str],
) -> list[CheckResult]:
    """For every action that uses model estimates: find a planned step where it really calls the
    model, learn which stored fields hold the estimate (they carry model provenance), then run
    that step again with the model unavailable, malformed and timed out. The action must refuse
    and store nothing, or store the entry with those fields left unknown. An invented number
    fails, and so does a model result stored without being labelled an estimate."""
    results: list[CheckResult] = []
    for action in actions:
        check_id = f"model.failure.{action}"
        found: tuple[Scenario, int, list[tuple[str, dict[str, Any], dict[str, Any]]]] | None = None
        for scenario in plan.scenarios:
            for index, step in enumerate(scenario.steps):
                if not (
                    isinstance(step, InvokeStep)
                    and step.action == action
                    and step.expect == "succeeded"
                    and step.model == "normal"
                ):
                    continue
                preview = make_preview(f"model-{action}-normal")
                try:
                    install(preview)
                    run, before, after, _ = _run_until(preview, scenario, index, "normal")
                    calls = preview.models.calls_for_run(run.run_id) if run else []
                finally:
                    preview.close()
                if run is not None and run.state is RunState.SUCCEEDED and calls:
                    found = (scenario, index, _changed(before, after))
                    break
            if found:
                break
        if found is None:
            results.append(
                CheckResult(
                    id=check_id,
                    stage="behavior",
                    status=CheckStatus.SKIPPED,
                    required=False,
                    summary=f"no planned step makes {action} call the model, so its failure path "
                    "was not checked",
                )
            )
            continue
        scenario, index, stored = found
        estimate_fields = sorted(
            {
                (c, f)
                for c, _, sources in stored
                for f, src in sources.items()
                if src == "model_estimate"
            }
        )
        problems: list[str] = []
        detail: dict[str, Any] = {
            "scenario": scenario.id,
            "step": scenario.steps[index].id,
            "estimate_fields": [f"{c}.{f}" for c, f in estimate_fields],
            "faults": {},
        }
        if stored and not estimate_fields:
            problems.append(
                f"{action} stored a model result without labelling it an estimate "
                "(pass the model result in estimated= when saving)"
            )
        for fault in MODEL_FAULTS:
            preview = make_preview(f"model-{action}-{fault}")
            try:
                install(preview)
                run, before, after, _ = _run_until(preview, scenario, index, fault)
            finally:
                preview.close()
            changed = _changed(before, after)
            state = run.state.value if run else "refused"
            detail["faults"][fault] = {"state": state, "changed": [c for c, _, _ in changed]}
            if run is None or run.state is not RunState.SUCCEEDED:
                if changed:
                    problems.append(
                        f"model {fault}: {action} failed but still changed {changed[0][0]}"
                    )
                continue
            for collection, values, sources in changed:
                for c, f in estimate_fields:
                    if c != collection:
                        continue
                    if values.get(f) is not None:
                        problems.append(
                            f"model {fault}: {action} saved {f}={values[f]!r} in {collection} "
                            "although no estimate was available; leave it unknown or refuse"
                        )
                    elif sources.get(f) == "model_estimate":
                        problems.append(
                            f"model {fault}: {f} is labelled an estimate but none was made"
                        )
            if not stored and run.output:
                detail["faults"][fault]["output"] = run.output
        results.append(
            CheckResult(
                id=check_id,
                stage="behavior",
                status=CheckStatus.FAILED if problems else CheckStatus.PASSED,
                summary=("; ".join(dict.fromkeys(problems)))[:1000]
                if problems
                else f"{action} stays honest when the model is unavailable, malformed or too slow",
                detail=detail,
            )
        )
    return results
