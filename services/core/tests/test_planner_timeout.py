"""The acceptance planner timing out no longer throws a finished build away.

Found twice on 28 September with a job-search request: the planner's structured call ran past
300 s (Sonnet spent 20k of 24k output tokens thinking), the creation failed as plan_unavailable
and the already-built candidate was cancelled as if the person had pressed Stop. Now: the
planner thinks at low effort by default, a planner failure verifies the candidate against the
brief's own examples when they can run (the checks are marked preliminary and the full planner
is retried once, its checks running after the module is switched on), and a build Alpha stops
itself says so.
"""

from __future__ import annotations

import stat
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.assistant.service import AssistantService
from alpha.builds.attempt import BuilderOutcome
from alpha.builds.service import BuildService
from alpha.builds.verify import VerificationOutcome
from alpha.execution.supervisor import WorkerSupervisor
from alpha.models.gateway import ModelGateway
from alpha.models.preferences import FIELDS, InvalidSetting, Preferences, stage_effort
from alpha.models.structured import StructuredInference
from alpha.solutions.creation import PLAN_RETRY_SECONDS, CreationRoutes, CreationService
from alpha.solutions.planner import AcceptancePlan, AcceptancePlanner, PlanningFailed
from alpha.storage.control_store import ControlStore
from alpha_contracts.builds import BuildResultStatus, BuildState
from alpha_contracts.verification import (
    CheckResult,
    CheckStatus,
    ValidationPlan,
    VerificationReport,
)
from test_creation_cancel import BRIEF, Builds

EXAMPLE_BRIEF = type(BRIEF).model_validate(
    BRIEF.model_dump()
    | {
        "acceptance_examples": [
            {
                "description": "a note is saved",
                "action_id": "add_note",
                "input": {"title": "Buy milk"},
                "expected": None,
                "kind": "success",
            }
        ]
    }
)

# ----- 1. reasoning effort per stage ------------------------------------------------------------


def test_effort_is_a_validated_setting_beside_its_model(tmp_path: Path) -> None:
    prefs = Preferences(ControlStore(tmp_path / "control.sqlite"))
    ids = [f.id for f in FIELDS]
    assert ids.index("effort.planner") == ids.index("models.planner") + 1, "next to its model"
    assert ids.index("effort.triage") == ids.index("models.assistant") + 1
    planner = next(d for d in prefs.describe() if d["id"] == "effort.planner")
    assert planner["group"] == "Models" and planner["value"] == "low"
    assert [o["value"] for o in planner["options"]] == ["low", "medium", "high", "default"]
    assert stage_effort(prefs, "planner") == "low" and stage_effort(None, "triage") == "low"
    prefs.update({"effort.planner": "high"})
    assert stage_effort(prefs, "planner") == "high"
    with pytest.raises(InvalidSetting, match="not one of the choices"):
        prefs.update({"effort.planner": "max"})


FAKE_CLI = """#!/bin/sh
printf '%s\\n' "$@" > "$(dirname "$0")/argv"
echo '{"type":"result","is_error":false,"result":"","structured_output":{"ok":true}}'
"""


def _fake_cli(tmp_path: Path) -> tuple[StructuredInference, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text(FAKE_CLI, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    store = ControlStore(tmp_path / "control.sqlite")
    gateway = ModelGateway(store, frozenset({"fake", "claude-code-cli"}))
    inference = StructuredInference(gateway, tool_path=f"{bin_dir}:/usr/bin:/bin")
    return inference, bin_dir / "argv"


def test_a_structured_call_passes_the_effort_it_is_given(tmp_path: Path) -> None:
    inference, argv_file = _fake_cli(tmp_path)
    route = ModelGateway(ControlStore(tmp_path / "c2.sqlite"), frozenset({"claude-code-cli"}))
    cli = route.route("claude-code-cli")
    inference.call(cli, system="s", prompt="p", schema={}, scope_kind="t", scope_ref="r1")
    assert "--effort" not in argv_file.read_text().split("\n"), "no effort: the CLI's own"
    inference.call(
        cli, system="s", prompt="p", schema={}, scope_kind="t", scope_ref="r2", effort="low"
    )
    argv = argv_file.read_text().split("\n")
    assert argv[argv.index("--effort") + 1] == "low"
    inference.call(
        cli, system="s", prompt="p", schema={}, scope_kind="t", scope_ref="r3", effort="default"
    )
    assert "--effort" not in argv_file.read_text().split("\n")


class RecordingInference:
    def __init__(self, fail: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail = fail

    def call(self, route: Any, **kwargs: Any) -> Any:
        from alpha.models.structured import InferenceError

        self.calls.append(kwargs)
        if self.fail:
            raise InferenceError(self.fail, "model call exceeded 300s")
        return SimpleNamespace(output={"path": "full"})


def test_the_planner_asks_for_low_effort_and_passes_a_longer_timeout(tmp_path: Path) -> None:
    prefs = Preferences(ControlStore(tmp_path / "control.sqlite"))
    inference = RecordingInference(fail="timeout")
    planner = AcceptancePlanner(inference, preferences=prefs)  # type: ignore[arg-type]
    route = SimpleNamespace(route_id="claude-code-cli")
    with pytest.raises(PlanningFailed) as caught:
        planner.plan(BRIEF, route, "create_1", timeout_seconds=900)  # type: ignore[arg-type]
    assert caught.value.code == "timeout", "the cause travels with the failure"
    assert inference.calls[0]["effort"] == "low"
    assert inference.calls[0]["timeout_seconds"] == 900
    prefs.update({"effort.planner": "medium"})
    with pytest.raises(PlanningFailed):
        planner.plan(BRIEF, route, "create_2")  # type: ignore[arg-type]
    assert inference.calls[1]["effort"] == "medium"


def test_change_triage_asks_for_low_effort(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    inference = RecordingInference()
    gateway = SimpleNamespace(preferences=Preferences(store))
    service = AssistantService(
        store,
        gateway,  # type: ignore[arg-type]
        inference,  # type: ignore[arg-type]
        default_route="fake",
        describe_app=lambda _a: "Name: Notes list",
    )
    record = SimpleNamespace(change_of="notes-list-1a2b3c")
    route = SimpleNamespace(route_id="claude-code-cli")
    service._triage_change("conv_1", record, route, "remove the box")  # type: ignore[arg-type]
    assert inference.calls[0]["effort"] == "low"


# ----- 2. a planner failure keeps the finished build -----------------------------------------

FULL = ValidationPlan.model_validate(
    {
        "scenarios": [
            {
                "id": "full",
                "description": "full checks",
                "steps": [{"kind": "invoke", "id": "a", "action": "add_note"}],
            }
        ]
    }
)


class Planner:
    """First call times out; the retry answers (or fails too)."""

    def __init__(self, retry_ok: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.retry_ok = retry_ok
        self.retry_gate = threading.Event()

    def plan(self, brief: Any, route: Any, scope: str, **kwargs: Any) -> AcceptancePlan:
        self.calls.append(kwargs)
        if len(self.calls) > 1:
            self.retry_gate.wait(5)
        if len(self.calls) == 1 or not self.retry_ok:
            raise PlanningFailed(
                "the checks could not be written: model call exceeded 300s", code="timeout"
            )
        return AcceptancePlan("Notes list", FULL, "model", [])


class ParallelBuilds(Builds):
    """A build that verifies on whatever plan `plan_later` hands it, like the real one."""

    def __init__(self) -> None:
        super().__init__()
        self.plan_later: Any = None
        self.verified_on: ValidationPlan | None = None
        self.preliminary: list[str] = []
        self.cancels: list[dict[str, Any]] = []
        self.deferred: list[ValidationPlan | None] = []
        self.unavailable: list[str] = []
        self.checks: dict[str, Any] = {"status": "preliminary", "full": "pending"}
        self.settled = threading.Event()

    def submit(self, **kwargs: Any) -> Any:
        self.plan_later = kwargs["plan_later"]
        return SimpleNamespace(build_id="build_1")

    def use_preliminary(self, build_id: str) -> None:
        self.preliminary.append(build_id)

    def get(self, build_id: str) -> Any:
        if self.verified_on is None:
            self.verified_on = self.plan_later(5) or ValidationPlan()
        record = super().get(build_id)
        if not self.verified_on.scenarios:
            record.state = BuildState.CANCELLED if self.cancels else BuildState.FAILED
            record.terminal_reason = "plan_unavailable"
        record.candidate = {"name": "Notes list", "actions": ["add_note"], "checks": self.checks}
        record.validation = {"checks": []}
        return record

    def cancel(self, build_id: str, **kwargs: Any) -> None:
        self.cancels.append(kwargs)

    def check_deferred(self, build_id: str, plan: ValidationPlan | None = None) -> Any:
        self.deferred.append(plan)
        if plan is not None:
            self.checks = {"status": "passed", "checks_passed": 1}
            self.settled.set()
        return self.checks

    def full_checks_unavailable(self, build_id: str) -> None:
        self.unavailable.append(build_id)
        self.checks = {"status": "preliminary", "full": "unavailable"}
        self.settled.set()


def live_service(tmp_path: Path, builds: Builds, planner: Any, brief: Any) -> CreationService:
    assistant = SimpleNamespace(
        get=lambda _cid: SimpleNamespace(state="briefed", current_brief=brief, quick_change=False)
    )
    gateway = SimpleNamespace(route=lambda route_id, **_: SimpleNamespace(route_id=route_id))
    return CreationService(
        ControlStore(tmp_path / "control.sqlite"),
        assistant,  # type: ignore[arg-type]
        builds,  # type: ignore[arg-type]
        planner,
        gateway,  # type: ignore[arg-type]
        CreationRoutes(planner="claude-code-cli", builder="claude-code-cli"),
        poll_seconds=0.01,
    )


def run(svc: CreationService) -> str:
    creation = svc.start("conv_1")
    for thread in threading.enumerate():
        if thread.name == f"creation-{creation.creation_id}":
            thread.join(timeout=10)
    return creation.creation_id


def test_a_planner_timeout_keeps_the_build_on_the_briefs_examples(tmp_path: Path) -> None:
    builds, planner = ParallelBuilds(), Planner()
    svc = live_service(tmp_path, builds, planner, EXAMPLE_BRIEF)
    creation_id = run(svc)
    final = svc.get(creation_id)
    assert final.state == "active", final.failure
    assert builds.cancels == [], "nothing was cancelled"
    assert builds.preliminary == ["build_1"]
    assert builds.verified_on is not None
    assert [s.id for s in builds.verified_on.scenarios] == ["example_1"]
    assert final.result is not None and final.result["checks"]["status"] == "preliminary"
    assert final.plan_source == "preliminary"
    planner.retry_gate.set()
    assert builds.settled.wait(5), "the full checks ran after it was switched on"
    assert builds.deferred[-1] == FULL
    assert planner.calls[1]["timeout_seconds"] == PLAN_RETRY_SECONDS > 300
    after = svc.get(creation_id)
    assert after.plan_source == "model" and after.result is not None
    assert after.result["checks"]["status"] == "passed"


def test_when_the_retry_fails_too_the_checks_stay_preliminary(tmp_path: Path) -> None:
    builds, planner = ParallelBuilds(), Planner(retry_ok=False)
    planner.retry_gate.set()
    svc = live_service(tmp_path, builds, planner, EXAMPLE_BRIEF)
    creation_id = run(svc)
    assert builds.settled.wait(5)
    assert builds.unavailable == ["build_1"] and len(planner.calls) == 2
    final = svc.get(creation_id)
    assert final.state == "active" and final.plan_source == "preliminary"
    assert final.result is not None and final.result["checks"]["full"] == "unavailable"


def test_nothing_runnable_fails_honestly_and_the_platform_stops_the_build(
    tmp_path: Path,
) -> None:
    builds, planner = ParallelBuilds(), Planner()
    svc = live_service(tmp_path, builds, planner, BRIEF)  # no executable examples
    final = svc.get(run(svc))
    assert final.state == "failed" and final.failure is not None
    assert final.failure["reason"] == "plan_unavailable"
    assert "ran out of time" in final.failure["message"]
    assert "examples" in final.failure["message"]
    assert builds.cancels == [{"reason": "stopped_by_platform", "cause": "plan_unavailable"}]


# ----- 3. the build service: preliminary checks, then the full ones --------------------------


class Verifier:
    def __init__(self, sealed: Any) -> None:
        self.sealed = sealed
        self.plans: list[tuple[str, ValidationPlan]] = []

    def _outcome(self, build_id: str, attempt_id: str, check: str) -> VerificationOutcome:
        report = VerificationReport(
            build_id=build_id,
            attempt_id=attempt_id,
            attempt_number=1,
            lineage=[attempt_id],
            builder_status=BuildResultStatus.CANDIDATE,
            package_sha256="a" * 64,
            checks=[
                CheckResult(id=check, stage="behavior", status=CheckStatus.PASSED, summary="ok")
            ],
            passed=True,
        )
        return VerificationOutcome(report, self.sealed)

    def verify(self, *, build_id: str, attempt_id: str, plan: ValidationPlan, **_: Any) -> Any:
        self.plans.append(("verify", plan))
        outcome = self._outcome(build_id, attempt_id, "behavior.prelim")
        outcome.pending = SimpleNamespace(
            build_id=build_id, attempt_id=attempt_id, attempt_dir=self.sealed.path.parent, stop=None
        )
        return outcome

    def verify_structure(self, *, build_id: str, attempt_id: str, **_: Any) -> Any:
        outcome = self._outcome(build_id, attempt_id, "handlers.bind")
        outcome.pending = SimpleNamespace(
            build_id=build_id, attempt_id=attempt_id, attempt_dir=self.sealed.path.parent, stop=None
        )
        return outcome

    def verify_behaviour(self, run: Any, plan: ValidationPlan) -> Any:
        self.plans.append(("behaviour", plan))
        return self._outcome(run.build_id, run.attempt_id, f"behavior.{plan.scenarios[0].id}")


def build_service(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, fast: bool) -> Any:
    control = ControlStore(tmp_path / "control.sqlite")
    root = tmp_path / "builds"
    source = SimpleNamespace(
        app_id="notes",
        name="Notes",
        actions=[],
        capabilities=["records"],
        schedules=[],
        ui=None,
        screen=None,
        has_screen=lambda: True,
    )
    sealed = SimpleNamespace(
        source=source,
        version_id="ver_1",
        package_sha256="a" * 64,
        dependency_manifest_sha256="b" * 64,
        dependency_manifest=SimpleNamespace(runtime_profile_id="pyprof"),
        path=root / "sealed",
    )
    verifier = Verifier(sealed)
    pipeline = SimpleNamespace(verifier=verifier, resources=None, inference=None)
    service = BuildService(
        control,
        WorkerSupervisor(Path("/usr/bin/true"), tmp_path / "scratch", 1.0),
        ModelGateway(control, frozenset({"fake"})),
        pipeline,  # type: ignore[arg-type]
        builds_root=root,
        builder_path="/usr/bin:/bin",
        builder_home=None,
        instance_id="core_test",
    )
    targets = SimpleNamespace(sdk_version="1", ui=None, runtime=SimpleNamespace(profile_id="p"))
    monkeypatch.setattr(service, "_targets", lambda _app: targets)
    monkeypatch.setattr(
        "alpha.builds.service.materialize",
        lambda directory, **_: directory.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(service, "_build", lambda *_a: BuilderOutcome("candidate"))
    return service, verifier


def wait_state(service: BuildService, build_id: str) -> Any:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        record = service.get(build_id)
        if record.state in (BuildState.READY, BuildState.FAILED, BuildState.CANCELLED):
            return record
        time.sleep(0.02)
    raise AssertionError(f"build stuck in {service.get(build_id).state}")


PRELIM = ValidationPlan.model_validate(
    {
        "scenarios": [
            {
                "id": "example_1",
                "description": "d",
                "steps": [{"kind": "invoke", "id": "run", "action": "add_note"}],
            }
        ]
    }
)


@pytest.mark.parametrize("fast", [False, True])
def test_a_build_on_the_preliminary_plan_is_ready_and_later_checked_in_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fast: bool
) -> None:
    service, verifier = build_service(tmp_path, monkeypatch, fast=fast)
    holder: dict[str, str] = {}

    def plan_later(_timeout: float) -> ValidationPlan:
        while "id" not in holder:
            time.sleep(0.01)
        service.use_preliminary(holder["id"])
        return PRELIM

    build = service.submit(goal="notes", plan=PRELIM, plan_later=plan_later, fast_lane=fast)
    holder["id"] = build.build_id
    ready = wait_state(service, build.build_id)
    assert ready.state is BuildState.READY, ready.terminal_reason
    if fast:
        assert ready.candidate["checks"]["status"] == "pending"
        checks = service.check_deferred(build.build_id)  # after switching on, on the examples
    else:
        checks = ready.candidate["checks"]
    assert checks["status"] == "preliminary" and checks["full"] == "pending"
    assert ("verify" if not fast else "behaviour", PRELIM) in verifier.plans
    checks = service.check_deferred(build.build_id, plan=FULL)
    assert checks["status"] == "passed"
    assert verifier.plans[-1] == ("behaviour", FULL)
    after = service.get(build.build_id)
    assert after.candidate["checks"]["status"] == "passed" and after.plan == FULL
    service.shutdown()


def test_the_full_checks_can_be_given_up_honestly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = build_service(tmp_path, monkeypatch, fast=False)
    holder: dict[str, str] = {}

    def plan_later(_timeout: float) -> ValidationPlan:
        while "id" not in holder:
            time.sleep(0.01)
        service.use_preliminary(holder["id"])
        return PRELIM

    build = service.submit(goal="notes", plan=PRELIM, plan_later=plan_later)
    holder["id"] = build.build_id
    wait_state(service, build.build_id)
    service.full_checks_unavailable(build.build_id)
    checks = service.get(build.build_id).candidate["checks"]
    assert checks["status"] == "preliminary" and checks["full"] == "unavailable"
    service.shutdown()


def test_a_platform_stop_is_not_recorded_as_the_persons(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, _ = build_service(tmp_path, monkeypatch, fast=False)
    gate = threading.Event()
    monkeypatch.setattr(service, "_run_build", lambda _item: gate.wait(5))
    build = service.submit(goal="notes", plan=PRELIM)
    service.cancel(build.build_id, reason="stopped_by_platform", cause="plan_unavailable")
    gate.set()
    record = service.get(build.build_id)
    assert record.state is BuildState.CANCELLED
    assert record.terminal_reason == "stopped_by_platform"
    event = service.events(build.build_id)[-1]
    assert event.kind == "build.cancelled" and event.payload["cause"] == "plan_unavailable"
    failure = CreationService._build_failure(record)
    assert "Alpha stopped" in failure["message"] and "cancelled" not in failure["message"]
    service.shutdown()
