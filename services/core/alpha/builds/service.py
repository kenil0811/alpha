"""BuildService: the build lifecycle (Current Release Specification §4, Blueprint §6).

State machine (only Core changes it):
    queued → building → validating → ready
                  ↑           ↓
                  └─ repairing ┘      (`max_repair_attempts` times, plus one while converging)
    and terminal failed / cancelled from any non-terminal state.

- One builder runs at a time (Blueprint §7): builds wait in `queued`, in submission order, and a
  single dispatcher starts them. Nothing about a waiting build survives a restart.
- Each attempt gets a fresh workspace (`workspace.py`). A harness claim is only a claim: every
  claimed candidate is sealed and verified independently (`verify.py`), against a plan the
  builder cannot change. A harness that reports failure stays failed even when some checks pass.
- Failed checks go back to the builder as a concrete repair request while repairs, time
  (12 minutes per attempt, 30 minutes in total) and money remain; every attempt is retained.
- Only a candidate whose report passed is `ready`. It stays a preview until `activate` installs
  its exact sealed bytes, after rechecking them and the profiles it was validated with.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from alpha_contracts.builds import (
    TERMINAL_BUILD_STATES,
    BuildBudget,
    BuildEvent,
    BuildRequest,
    BuildResultStatus,
    BuildState,
    BuildUsage,
    FailureCategory,
)
from alpha_contracts.runs import RunState
from alpha_contracts.verification import (
    CheckResult,
    CheckStatus,
    ValidationPlan,
    VerificationReport,
)

from alpha.builds.attempt import BuilderOutcome, BuilderProcess
from alpha.builds.awake import stay_awake
from alpha.builds.preview import PreviewDeps, PreviewPlatform
from alpha.builds.quick_edit import (
    QUICK_MAX_BYTES,
    QUICK_REPAIR_SYSTEM,
    apply_edits,
    quick_change_schema,
    quick_repair_prompt,
    read_package_files,
)
from alpha.builds.store import (
    BuildRecord,
    BuildStore,
)
from alpha.builds.toolchain import PlatformResources
from alpha.builds.verify import CandidateVerifier, VerificationOutcome, fast_eligible
from alpha.builds.workspace import (
    TargetProfiles,
    evidence_files,
    materialize,
    render_plan,
    render_repair,
)
from alpha.capabilities.errors import OperationFailed
from alpha.data.packages import SealedPackage, load_source, sealed_manifest, verify_sealed
from alpha.execution.profiles import ProfileInventory
from alpha.execution.supervisor import WorkerHandle, WorkerSupervisor, process_alive
from alpha.models.gateway import ModelGateway, ModelRoute
from alpha.solutions.registry import ANY_RELEASE, Activation, AnyRelease, AppRegistry
from alpha.storage.control_store import ConflictError, ControlStore, new_id, utc_now

log = logging.getLogger("alpha.builds")

# A repair attempt is not started with less than this much of the total budget left.
MIN_ATTEMPT_SECONDS = 60


class RepairPolicy:
    """How many more repairs a build may have. The fixed allowance is the floor; past it, a
    repair that left fewer failing checks than the one before earns one more, so a build that
    is converging is not stopped one edit from done (found live: 30 of 32 checks passed on the
    last allowed attempt). The total time and cost budgets still bound the whole build."""

    def __init__(self, max_repairs: int) -> None:
        self._allowed = 1 + max_repairs
        self._previous_failed: int | None = None

    def repairs_left(self, attempt_number: int, failed_now: int) -> int:
        """Repairs still available after `attempt_number`, which ended with `failed_now`
        required checks not passing. 0 means the build stops here."""
        converging = self._previous_failed is not None and 0 < failed_now < self._previous_failed
        self._previous_failed = failed_now
        left = self._allowed - attempt_number
        if left <= 0 and converging:
            return 1
        return max(left, 0)


class BuildNotReady(Exception):
    pass


class SeedUnavailable(Exception):
    pass


SEED_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class _Attempt:
    attempt_id: str
    number: int
    directory: Path
    request: BuildRequest
    seeded: bool


# Builder outcomes that end the build without verification or repair, and their reasons.
_HARNESS_FAILURES = {
    "timed_out": "attempt_deadline_exceeded",
    "no_result": "builder_returned_no_result",
    "launch_failed": "builder_launch_failed",
}


@dataclass(frozen=True)
class _QueuedBuild:
    build_id: str
    route: ModelRoute
    budget: BuildBudget


@dataclass(frozen=True)
class BuildPipeline:
    """What turns a builder's package into a verified, activatable candidate."""

    inventory: ProfileInventory
    registry: AppRegistry
    verifier: CandidateVerifier
    preview: PreviewDeps
    resources: PlatformResources
    fake_packages_dir: Path | None = None
    seed_packages_dir: Path | None = None
    # One structured call that edits files: repairs a failed attempt without a new builder
    # session. None in tests that only exercise the queue.
    inference: Any | None = None


class BuildService:
    def __init__(
        self,
        store: ControlStore,
        supervisor: WorkerSupervisor,
        gateway: ModelGateway,
        pipeline: BuildPipeline,
        *,
        builds_root: Path,
        builder_path: str,
        builder_home: str | None,
        instance_id: str,
        custom_ui: bool = False,
    ) -> None:
        self._custom_ui = custom_ui
        self._db = BuildStore(store)
        self._supervisor = supervisor
        self._gateway = gateway
        self._pipeline = pipeline
        self._root = builds_root
        self._builder = BuilderProcess(
            supervisor, builder_path=builder_path, builder_home=builder_home
        )
        self._instance_id = instance_id
        self._lock = threading.Lock()
        self._active: dict[str, WorkerHandle] = {}  # "build_id:attempt_id" -> handle
        self._cancel_requested: set[str] = set()  # build ids
        self._plan_ready: dict[str, threading.Event] = {}  # builds whose plan is still coming
        self._plan_failed: set[str] = set()
        self._stops: dict[str, threading.Event] = {}  # build id -> stop verification
        # The fast lane: builds allowed to switch a simple module on after its structural
        # checks, and the runs whose behaviour checks are still owed.
        self._fast_lane: set[str] = set()
        self._deferred: dict[str, Any] = {}
        # Builds verified on the brief's own examples because the full plan could not be
        # written; their full checks run later through `check_deferred(plan=...)`.
        self._preliminary: set[str] = set()
        # The one-builder queue. The condition shares self._lock.
        self._waiting: deque[_QueuedBuild] = deque()
        self._wakeup = threading.Condition(self._lock)
        self._current: str | None = None  # build id the dispatcher is working on
        self._closing = False
        self._dispatcher: threading.Thread | None = None
        self._root.mkdir(parents=True, exist_ok=True)

    # ----- public API -------------------------------------------------------------------

    def submit(
        self,
        *,
        goal: str,
        plan: ValidationPlan,
        instructions: str = "",
        route_id: str = "fake",
        max_cost_usd: float | None = None,
        seed_package: str | None = None,
        app_id: str | None = None,
        base_package: Path | None = None,
        plan_later: Callable[[float], ValidationPlan | None] | None = None,
        fast_lane: bool = False,
    ) -> BuildRecord:
        """Queue a build. `app_id`, when given, is the identity the platform assigned (the
        package must use it); otherwise the builder chooses one. `base_package` is the installed
        Version a change starts from: the first attempt's workspace begins as a writable copy
        of it, so the builder edits the App instead of writing it again. With `fast_lane`, a
        candidate Alpha draws itself is ready after its structural checks; its behaviour
        checks run through `check_deferred` once it is switched on."""
        route = self._gateway.route(
            route_id, stage="builder_change" if base_package is not None else "builder_new"
        )
        if base_package is not None and not (base_package / "app.yaml").is_file():
            raise SeedUnavailable(f"no installed package at {base_package}")
        budget = self._gateway.budget(route, max_cost_usd)
        if seed_package is not None:
            seeds = self._pipeline.seed_packages_dir
            if seeds is None or not SEED_NAME.match(seed_package):
                raise SeedUnavailable("seeded builds are not enabled on this host")
            if not (seeds / seed_package).is_dir():
                raise SeedUnavailable(f"no seed package {seed_package!r}")
        build_id = new_id("build")
        brief_ref = f"{build_id}.brief.r1"
        now = utc_now()
        build_dir = self._root / build_id
        build_dir.mkdir(parents=True, exist_ok=False)
        (build_dir / "brief.r1.json").write_text(
            json.dumps(
                {
                    "brief_ref": brief_ref,
                    "goal": goal,
                    "instructions": instructions,
                    "created_at": now.isoformat().replace("+00:00", "Z"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (build_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        with self._lock:
            ahead = len(self._waiting) + (1 if self._current else 0)
        self._db.insert_build(
            build_id=build_id,
            brief_ref=brief_ref,
            goal=goal,
            instructions=instructions,
            plan=plan,
            seed_package=seed_package,
            app_id=app_id,
            base_package=str(base_package) if base_package else None,
            route_id=route.route_id,
            harness=route.harness,
            budget=budget,
            created_at=now,
            queued_payload={"route_id": route.route_id, "ahead": ahead},
        )
        if fast_lane:
            self._fast_lane.add(build_id)
        if plan_later is not None:
            # The builder starts on a preliminary plan (the brief's own examples); the full
            # checks arrive in parallel and replace it before verification.
            self._plan_ready[build_id] = threading.Event()
            threading.Thread(
                target=self._watch_plan,
                args=(build_id, plan_later, budget.max_total_seconds),
                name=f"plan-{build_id}",
                daemon=True,
            ).start()
        with self._wakeup:
            self._waiting.append(_QueuedBuild(build_id, route, budget))
            if self._dispatcher is None:
                self._dispatcher = threading.Thread(
                    target=self._run_queue, name="alpha-builder-queue", daemon=True
                )
                self._dispatcher.start()
            self._wakeup.notify()
        return self.get(build_id)

    def get(self, build_id: str) -> BuildRecord:
        return self._db.get(build_id)

    def list_builds(self, limit: int = 50) -> list[BuildRecord]:
        return self._db.list_builds(limit)

    def events(self, build_id: str, after: int = 0, limit: int = 1000) -> list[BuildEvent]:
        return self._db.events(build_id, after, limit)

    def dependency_requests(self, build_id: str | None = None) -> list[dict[str, Any]]:
        return self._db.dependency_requests(build_id)

    def use_preliminary(self, build_id: str) -> None:
        """The plan about to be handed over is the brief's own examples, not the planner's full
        checks: a candidate that passes it is ready with its checks marked preliminary, and the
        full checks follow after it is switched on."""
        self._preliminary.add(build_id)

    def cancel(
        self, build_id: str, *, reason: str = "cancelled_by_user", cause: str | None = None
    ) -> BuildRecord:
        """Stop a build. `reason` says who stopped it: the person (the default) or Alpha itself
        ("stopped_by_platform", with the `cause`)."""
        record = self.get(build_id)
        if record.state in TERMINAL_BUILD_STATES:
            raise ConflictError(f"build {build_id} already {record.state.value}")
        with self._lock:
            self._cancel_requested.add(build_id)
            self._waiting = deque(q for q in self._waiting if q.build_id != build_id)
            handles = [h for aid, h in self._active.items() if aid.startswith(build_id + ":")]
            stop = self._stops.get(build_id)
        if stop is not None:
            stop.set()
        termination: list[dict[str, object]] = []
        for handle in handles:
            termination.append(self._supervisor.terminate(handle))
        self._db.transition(
            build_id,
            new_state=BuildState.CANCELLED,
            event_kind="build.cancelled",
            payload={"termination": termination, "cause": cause},
            terminal_reason=reason,
            failure_category=FailureCategory.CANCELLED,
        )
        return self.get(build_id)

    def activate(
        self,
        build_id: str,
        *,
        expected_release_id: str | None | AnyRelease = ANY_RELEASE,
        creation_id: str | None = None,
    ) -> dict[str, Any]:
        """Install a ready candidate's exact sealed bytes as the App's current Version, after
        rechecking the bytes, the profiles it was validated with and (when given) that the App's
        current release is still the expected one."""
        record = self.get(build_id)
        if record.state is not BuildState.READY or not record.candidate:
            raise BuildNotReady(f"build {build_id} is {record.state.value}, not ready")
        candidate = record.candidate
        version_dir = self._root / candidate["version_ref"]
        activation = Activation(
            kind="activated",
            origin="created" if creation_id else "build",
            expected_release_id=expected_release_id,
            build_id=build_id,
            verification_ref=candidate["report_ref"],
            creation_id=creation_id,
        )
        try:
            version = self._pipeline.registry.activate_sealed(
                version_dir, candidate["package_sha256"], activation
            )
        except OperationFailed as exc:
            self._db.append(build_id, None, "build.activation_refused", exc.as_error())
            raise
        result = {
            "app_id": version.app_id,
            "version_id": version.version_id,
            "release_id": version.release_id,
            "package_sha256": version.package_sha256,
            "dependency_manifest_sha256": version.dependency_manifest_sha256,
            "runtime_profile_id": version.runtime_profile_id,
        }
        self._db.append(build_id, None, "build.activated", result)
        return result

    def check_deferred(self, build_id: str, plan: ValidationPlan | None = None) -> dict[str, Any]:
        """Behaviour checks a candidate still owes, run now and recorded on the build. Without
        `plan`: a fast-lane candidate's, on the build's plan once it is here (the brief's
        examples when that plan is preliminary; the run is then kept for the full checks).
        With `plan`: the full checks for a candidate that was verified on a preliminary plan.
        Returns what the person is told: passed, failed (with what failed), preliminary, or
        not_run (with why)."""
        record = self.get(build_id)
        candidate = record.candidate or {}
        run = self._deferred.pop(build_id, None)
        event = self._plan_ready.pop(build_id, None)
        if run is None:
            checks: dict[str, Any] = candidate.get("checks") or {}
            if checks.get("status") == "pending":
                checks = {"status": "not_run", "reason": "lost"}
                self._db.set_candidate_checks(build_id, checks)
            elif checks.get("full") == "pending":
                checks = {**checks, "full": "unavailable"}
                self._db.set_candidate_checks(build_id, checks)
            return checks
        preliminary = False
        if plan is not None:
            self._preliminary.discard(build_id)
            self._db.update_plan(build_id, plan)
        else:
            plan_failed = False
            if event is not None:
                event.wait(float(record.budget.max_total_seconds))
                plan_failed = build_id in self._plan_failed or not event.is_set()
                self._plan_failed.discard(build_id)
                record = self.get(build_id)
            if plan_failed:
                checks = {"status": "not_run", "reason": "plan_unavailable"}
                self._db.set_candidate_checks(build_id, checks)
                self._db.append(build_id, run.attempt_id, "build.behaviour_checked", checks)
                return checks
            plan = record.plan
            preliminary = build_id in self._preliminary
        outcome = self._pipeline.verifier.verify_behaviour(run, plan)
        if outcome is None:  # cannot happen without a stop event; recorded honestly anyway
            checks = {"status": "not_run", "reason": "stopped"}
            self._db.set_candidate_checks(build_id, checks)
            return checks
        report = outcome.report
        (run.attempt_dir / "verification.report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        required = [c for c in report.checks if c.required]
        failed = [c.summary for c in required if c.status is not CheckStatus.PASSED]
        passed = sum(1 for c in required if c.status is CheckStatus.PASSED)
        if preliminary and report.passed:
            checks = {"status": "preliminary", "full": "pending", "checks_passed": passed}
            self._deferred[build_id] = run  # the full checks run on it once they are written
        else:
            self._preliminary.discard(build_id)
            checks = {
                "status": "passed" if report.passed else "failed",
                "checks_passed": passed,
                "failed_checks": failed[:5],
            }
        self._db.set_candidate_checks(build_id, checks, validation=report.model_dump(mode="json"))
        self._db.append(
            build_id,
            run.attempt_id,
            "build.behaviour_checked",
            {"status": checks["status"], "failed": _failed_ids(report)},
        )
        return checks

    def full_checks_unavailable(self, build_id: str) -> dict[str, Any]:
        """The full checks for a candidate verified on a preliminary plan could not be written
        (the planner's retry failed too): it stays switched on, checked on the examples only."""
        self._deferred.pop(build_id, None)
        self._preliminary.discard(build_id)
        checks = dict((self.get(build_id).candidate or {}).get("checks") or {})
        if checks.get("status") == "preliminary":
            checks["full"] = "unavailable"
            self._db.set_candidate_checks(build_id, checks)
            self._db.append(build_id, None, "build.behaviour_checked", checks)
        return checks

    def evidence_path(self, build_id: str, attempt: int, name: str) -> Path | None:
        """A render-check screenshot kept with an attempt, if it exists."""
        path = self._root / build_id / f"attempt-{attempt}" / "evidence" / "ui" / name
        root = (self._root / build_id).resolve()
        if path.is_file() and path.resolve().is_relative_to(root):
            return path
        return None

    def invoke(
        self, build_id: str, action_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Run a ready candidate's action in its preview (separate data, clearly a preview)."""
        record = self.get(build_id)
        if record.state is not BuildState.READY or not record.candidate:
            raise BuildNotReady(f"build {build_id} is {record.state.value}, not ready")
        candidate = record.candidate
        version_dir = self._root / candidate["version_ref"]
        try:
            index = verify_sealed(version_dir, candidate["package_sha256"])
        except OperationFailed as exc:
            raise BuildNotReady(f"candidate bytes changed since validation: {exc.message}") from exc
        sealed = SealedPackage(
            path=version_dir,
            version_id=version_dir.name,
            source=load_source(version_dir),
            index=index,
            dependency_manifest=sealed_manifest(version_dir),
            dependency_manifest_sha256=index.dependency_manifest_sha256,
            ui_build=None,
        )
        handlers = json.loads((self._root / candidate["handlers_ref"]).read_text("utf-8"))
        preview = PreviewPlatform(self._root / build_id / "preview-try", self._pipeline.preview)
        try:
            preview.install(sealed, handlers)
            run = preview.invoke_and_wait(action_id, input_payload)
            outcome = preview.outcome(run.run_id)
            if run.state is not RunState.SUCCEEDED:
                outcome["failure"] = preview.failure_detail(run)
        finally:
            preview.close()
        return {"preview": True, "version_id": sealed.version_id, **outcome}

    # ----- lifecycle ---------------------------------------------------------------------

    def reconcile_on_startup(self) -> list[dict[str, Any]]:
        report: list[dict[str, Any]] = []
        for row in self._db.running_attempts():
            entry: dict[str, Any] = {"attempt_id": row["attempt_id"], "build_id": row["build_id"]}
            pid, pgid = row["pid"], row["pgid"]
            if pid is not None and process_alive(int(pid)):
                entry["termination"] = self._supervisor.terminate_orphan(int(pgid))
                entry["reason"] = "core_restarted_builder_orphaned"
            else:
                entry["reason"] = "core_restarted_builder_lost"
            self._db.finish_attempt(
                row["attempt_id"], "interrupted", FailureCategory.INTERRUPTED, None, None
            )
            self._db.transition(
                row["build_id"],
                new_state=BuildState.FAILED,
                event_kind="build.interrupted",
                payload={"reason": entry["reason"], "reconciled_by": self._instance_id},
                terminal_reason=entry["reason"],
                failure_category=FailureCategory.INTERRUPTED,
                attempt_id=row["attempt_id"],
            )
            report.append(entry)
        # Behaviour checks a fast-lane module still owed do not survive either: the module
        # stays switched on and is told its checks did not run.
        for build_id, owed in self._db.builds_with_pending_checks().items():
            if owed.get("status") == "preliminary":
                checks = {**owed, "full": "unavailable"}
            else:
                checks = {"status": "not_run", "reason": "restarted"}
            self._db.set_candidate_checks(build_id, checks)
            self._db.append(build_id, None, "build.behaviour_checked", {"status": checks["status"]})
            report.append({"build_id": build_id, "reason": "core_restarted_checks_not_run"})
        # Nothing else survives a restart: a build that was waiting for the builder, or was
        # being verified or repaired, cannot continue and is not started again.
        for row in self._db.unfinished_builds():
            reason = (
                "core_restarted_while_queued"
                if row["state"] == BuildState.QUEUED.value
                else "core_restarted_build_lost"
            )
            self._db.transition(
                row["build_id"],
                new_state=BuildState.FAILED,
                event_kind="build.interrupted",
                payload={"reason": reason, "reconciled_by": self._instance_id},
                terminal_reason=reason,
                failure_category=FailureCategory.INTERRUPTED,
            )
            report.append({"build_id": row["build_id"], "reason": reason})
        return report

    def shutdown(self, reason: str = "runtime_quit") -> list[str]:
        with self._wakeup:
            self._closing = True
            waiting = [q.build_id for q in self._waiting]
            self._waiting.clear()
            self._wakeup.notify_all()
            handles = dict(self._active)
            stops = list(self._stops.values())
        for stop in stops:
            stop.set()
        interrupted: list[str] = []
        for build_id in waiting:
            self._db.transition(
                build_id,
                new_state=BuildState.FAILED,
                event_kind="build.interrupted",
                payload={"reason": reason, "while": "queued"},
                terminal_reason=reason,
                failure_category=FailureCategory.INTERRUPTED,
            )
            interrupted.append(build_id)
        for key, handle in handles.items():
            build_id, real_attempt = key.split(":", 1)
            with self._lock:
                self._cancel_requested.add(build_id)
            record = self._supervisor.terminate(handle)
            self._db.finish_attempt(
                real_attempt, "interrupted", FailureCategory.INTERRUPTED, None, None
            )
            self._db.transition(
                build_id,
                new_state=BuildState.FAILED,
                event_kind="build.interrupted",
                payload={"reason": reason, "termination": record},
                terminal_reason=reason,
                failure_category=FailureCategory.INTERRUPTED,
                attempt_id=real_attempt,
            )
            interrupted.append(build_id)
        return interrupted

    def active_attempt_ids(self) -> list[str]:
        with self._lock:
            return [a.split(":", 1)[1] for a in self._active]

    # ----- the one-builder queue ---------------------------------------------------------

    def _run_queue(self) -> None:
        """Start queued builds one at a time, in submission order, until Core shuts down."""
        while True:
            with self._wakeup:
                while not self._waiting and not self._closing:
                    self._wakeup.wait()
                if self._closing:
                    return
                item = self._waiting.popleft()
                if item.build_id in self._cancel_requested:
                    continue
                self._current = item.build_id
                self._stops[item.build_id] = threading.Event()
            try:
                with stay_awake():
                    self._run_build(item)
            except Exception as exc:
                # A platform fault in one build must not stall every build behind it.
                log.exception("build %s failed inside Core", item.build_id)
                self._fail_unexpected(item.build_id, exc)
            finally:
                with self._lock:
                    self._current = None
                    self._stops.pop(item.build_id, None)

    def _fail_unexpected(self, build_id: str, exc: Exception) -> None:
        with self._lock:
            handles = [
                (key, h) for key, h in self._active.items() if key.startswith(build_id + ":")
            ]
            for key, _ in handles:
                self._active.pop(key, None)
        for _, handle in handles:
            self._supervisor.terminate(handle)
        detail = {"error": f"{type(exc).__name__}: {exc}"[:500]}
        for row in self._db.running_attempts(build_id):
            self._db.finish_attempt(
                row["attempt_id"], "failed", FailureCategory.PLATFORM_ERROR, None, detail
            )
        self._db.transition(
            build_id,
            new_state=BuildState.FAILED,
            event_kind="build.failed",
            payload={"reason": "platform_error", **detail},
            terminal_reason="platform_error",
            failure_category=FailureCategory.PLATFORM_ERROR,
        )

    # ----- one build: attempts, verification, bounded repair -----------------------------

    def _targets(self, app_id: str | None) -> TargetProfiles | None:
        runtime = self._pipeline.inventory.default_app_profile()
        if runtime is None:
            return None
        # A compiled custom screen is offered only when the host allows it; otherwise the
        # module's screen is declared and drawn by the shell.
        ui = self._pipeline.inventory.default_ui_profile() if self._custom_ui else None
        return TargetProfiles(runtime=runtime, ui=ui, app_id=app_id)

    def _run_build(self, item: _QueuedBuild) -> None:
        build_id, route, budget = item.build_id, item.route, item.budget
        record = self.get(build_id)
        targets = self._targets(record.app_id)
        if targets is None:
            self._db.transition(
                build_id,
                new_state=BuildState.FAILED,
                event_kind="build.failed",
                payload={"reason": "runtime_profile_unavailable"},
                terminal_reason="runtime_profile_unavailable",
                failure_category=FailureCategory.PLATFORM_ERROR,
            )
            return
        started = time.monotonic()
        lineage: list[str] = []
        spent_usd = 0.0
        previous_package: Path | None = None
        repair: str | None = None
        feedback: list[Path] = []
        policy = RepairPolicy(budget.max_repair_attempts)
        last: VerificationReport | None = None
        number = 0
        while True:
            number += 1
            remaining = budget.max_total_seconds - (time.monotonic() - started)
            cost_left = None if budget.max_cost_usd is None else budget.max_cost_usd - spent_usd
            stop: tuple[str, dict[str, Any]] | None = None
            if number > 1 and remaining < MIN_ATTEMPT_SECONDS:
                stop = ("total_deadline_exceeded", {"max_total_seconds": budget.max_total_seconds})
            elif cost_left is not None and cost_left <= 0:
                stop = ("cost_limit_reached", {"max_cost_usd": budget.max_cost_usd})
            if stop is not None:
                # The reason says why no repair followed; the category is what was wrong.
                self._db.fail(
                    build_id,
                    lineage[-1] if lineage else "none",
                    stop[0],
                    self._category_of(last) if last else FailureCategory.BUDGET_EXHAUSTED,
                    {**stop[1], "attempts": len(lineage), "spent_usd": spent_usd},
                    validation=last.model_dump(mode="json") if last else None,
                )
                return
            attempt_budget = budget.model_copy(
                update={
                    "max_attempt_seconds": int(max(1, min(budget.max_attempt_seconds, remaining))),
                    "max_cost_usd": cost_left,
                }
            )
            step = self._attempt(
                record,
                number,
                route,
                attempt_budget,
                targets,
                lineage,
                previous_package,
                repair,
                feedback,
            )
            if step is None:
                return  # terminal: cancelled, a harness failure, or ready
            outcome, attempt_dir, usage, timed_out = step
            if usage is not None and usage.cost_usd is not None:
                spent_usd += usage.cost_usd
            report = outcome.report
            last = report
            left = policy.repairs_left(number, len(_failed_ids(report)))
            defects = [c.id for c in report.checks if c.detail.get("plan_defect")]
            if defects:
                # The plan itself cannot be satisfied; a repair would only waste the budget.
                self._db.fail(
                    build_id,
                    report.attempt_id,
                    "plan_defect",
                    FailureCategory.VALIDATION_FAILED,
                    {"attempts": len(lineage), "failed_checks": defects},
                    validation=report.model_dump(mode="json"),
                )
                return
            if left == 0:
                self._db.fail(
                    build_id,
                    report.attempt_id,
                    "attempt_deadline_exceeded" if timed_out else "repair_limit_reached",
                    FailureCategory.HARNESS_TIMEOUT if timed_out else self._category_of(report),
                    {"attempts": len(lineage), "failed_checks": _failed_ids(report)},
                    validation=report.model_dump(mode="json"),
                )
                return
            repair = render_repair(
                report,
                number,
                left - 1,
                timed_out_after=attempt_budget.max_attempt_seconds if timed_out else None,
            )
            feedback = evidence_files(report, attempt_dir)
            previous_package = attempt_dir / "package"
            self._db.transition(
                build_id,
                new_state=BuildState.REPAIRING,
                event_kind="build.repairing",
                payload={
                    "after_attempt": report.attempt_id,
                    "failed_checks": _failed_ids(report),
                    "repairs_left": left - 1,
                },
                attempt_id=report.attempt_id,
                expected={BuildState.VALIDATING},
                validation=report.model_dump(mode="json"),
            )

    def _attempt(
        self,
        record: BuildRecord,
        number: int,
        route: ModelRoute,
        budget: BuildBudget,
        targets: TargetProfiles,
        lineage: list[str],
        previous_package: Path | None,
        repair: str | None,
        feedback: list[Path],
    ) -> tuple[VerificationOutcome, Path, BuildUsage | None, bool] | None:
        """Run one attempt. Returns the failed verification (and whether the attempt ran out of
        time) when a repair may follow, or None once the build reached a terminal state."""
        attempt = self._start_attempt(
            record, number, route, budget, targets, previous_package, repair, feedback
        )
        lineage.append(attempt.attempt_id)
        built = self._build(record, attempt, route, budget, targets)
        return self._settle(record, attempt, lineage, built, budget)

    def _start_attempt(
        self,
        record: BuildRecord,
        number: int,
        route: ModelRoute,
        budget: BuildBudget,
        targets: TargetProfiles,
        previous_package: Path | None,
        repair: str | None,
        feedback: list[Path],
    ) -> _Attempt:
        """Materialize the workspace, record the attempt and move the build to building."""
        build_id = record.build_id
        attempt_id = new_id("attempt")
        attempt_dir = self._root / build_id / f"attempt-{number}"
        seeded = number == 1 and record.seed_package is not None
        if seeded:
            assert self._pipeline.seed_packages_dir is not None and record.seed_package
            previous_package = self._pipeline.seed_packages_dir / record.seed_package
        elif number == 1 and record.base_package:
            previous_package = Path(record.base_package)
        materialize(
            attempt_dir,
            resources=self._pipeline.resources,
            targets=targets,
            plan=record.plan,
            previous_package=previous_package,
            repair=repair,
            feedback_files=feedback,
        )
        now = utc_now()
        request = BuildRequest(
            build_id=build_id,
            attempt_id=attempt_id,
            attempt_number=number,
            brief_ref=record.brief_ref,
            context_snapshot_ref=f"{build_id}.context.r1",
            template_profile="app-template-0.2",
            sdk_profile=f"alpha-sdk@{targets.sdk_version}",
            ui_kit_profile=targets.ui.profile_id if targets.ui else None,
            dependency_profile=targets.runtime.profile_id,
            validation_plan_ref=f"{build_id}.plan",
            model_route_ref=route.route_id,
            budget=budget,
            workspace_lease_ref=str(attempt_dir.relative_to(self._root)),
            deadline=now + timedelta(seconds=budget.max_attempt_seconds),
        )
        self._db.insert_attempt(
            attempt_id=attempt_id,
            build_id=build_id,
            number=number,
            workspace_ref=request.workspace_lease_ref,
            core_instance_id=self._instance_id,
            started_at=now,
        )
        self._db.transition(
            build_id,
            new_state=BuildState.BUILDING,
            event_kind="build.attempt_started",
            payload={
                "attempt_id": attempt_id,
                "number": number,
                "harness": "seeded" if seeded else route.harness,
                "seed_package": record.seed_package if seeded else None,
                "repair": number > 1,
                "deadline_seconds": budget.max_attempt_seconds,
            },
            attempt_id=attempt_id,
            expected={BuildState.QUEUED, BuildState.REPAIRING},
        )
        return _Attempt(attempt_id, number, attempt_dir, request, seeded)

    def _build(
        self,
        record: BuildRecord,
        attempt: _Attempt,
        route: ModelRoute,
        budget: BuildBudget,
        targets: TargetProfiles,
    ) -> BuilderOutcome:
        """Run the builder worker (or take the seed) and record its usage."""
        build_id, attempt_id = record.build_id, attempt.attempt_id
        if attempt.seeded:
            # Qualification: the first candidate is a known package, verified like any claim.
            return BuilderOutcome("candidate", harness_exit={"seeded": record.seed_package})
        if attempt.number > 1 and route.route_id != "fake" and self._pipeline.inference is not None:
            # A repair is usually a few lines: one edit call (about a minute) instead of a new
            # builder session (ten). The session takes over only when the edit call declines.
            quick = self._quick_repair(record, attempt, route)
            if quick is not None:
                return quick
        key = f"{build_id}:{attempt_id}"

        def on_launch(handle: WorkerHandle) -> bool:
            with self._lock:
                self._active[key] = handle
                # cancel() collects handles under this lock: either it saw this one, or the
                # request is visible here. A build cancelled while it waited never builds.
                stop_now = build_id in self._cancel_requested or self._closing
                if stop_now:
                    self._cancel_requested.add(build_id)
            self._db.set_attempt_process(attempt_id, handle.pid, handle.pgid)
            return stop_now

        def on_exit() -> bool:
            with self._lock:
                self._active.pop(key, None)
                return build_id in self._cancel_requested

        fake_packages = self._pipeline.fake_packages_dir
        job = {
            "request": attempt.request.model_dump(mode="json"),
            "harness": route.harness,
            "workspace": str(attempt.directory),
            "goal": record.goal,
            "instructions": record.instructions,
            "model": route.model,
            "candidate_python": str(targets.runtime.python),
            "targets": targets.identities(),
            "fake_packages_dir": str(fake_packages)
            if route.harness == "fake" and fake_packages
            else None,
        }
        built = self._builder.run(
            attempt_id=attempt_id,
            job=job,
            deadline_seconds=budget.max_attempt_seconds,
            emit=lambda kind, payload: self._db.append(build_id, attempt_id, kind, payload),
            on_launch=on_launch,
            on_exit=on_exit,
        )
        if built.usage is not None:
            self._gateway.record_usage(route.route_id, "build_attempt", attempt_id, built.usage)
        return built

    def _watch_plan(
        self, build_id: str, plan_later: Callable[[float], ValidationPlan | None], timeout: int
    ) -> None:
        plan = None
        try:
            plan = plan_later(float(timeout))
        except Exception:
            log.exception("waiting for the plan of %s failed", build_id)
        if plan is not None:
            self._db.update_plan(build_id, plan)
            # The builder may still be working: give it the full checks where it reads them.
            for attempt_dir in sorted((self._root / build_id).glob("attempt-*")):
                try:
                    (attempt_dir / "PLAN.md").write_text(render_plan(plan), encoding="utf-8")
                    (attempt_dir / "plan.json").write_text(
                        plan.model_dump_json(indent=2), encoding="utf-8"
                    )
                except OSError:
                    pass
            self._db.append(build_id, None, "build.plan_ready", {"scenarios": len(plan.scenarios)})
        else:
            self._plan_failed.add(build_id)
        self._plan_ready[build_id].set()

    def _await_plan(self, record: BuildRecord, attempt: _Attempt) -> BuildRecord | None:
        """Before verification: the full plan, waited for when it is still being written. None
        when it never came (the build then fails as plan_unavailable)."""
        event = self._plan_ready.get(record.build_id)
        if event is None:
            return record
        event.wait(float(record.budget.max_total_seconds))
        if record.build_id in self._plan_failed or not event.is_set():
            self._db.fail(
                record.build_id,
                attempt.attempt_id,
                "plan_unavailable",
                FailureCategory.PLATFORM_ERROR,
                {"attempt": attempt.number},
            )
            return None
        return self.get(record.build_id)

    def _quick_repair(
        self, record: BuildRecord, attempt: _Attempt, route: ModelRoute
    ) -> BuilderOutcome | None:
        """Fix a failed attempt with one structured edit call on a copy of its package. Returns
        None when the call declines or fails, so the builder session runs as before."""
        build_id, attempt_id = record.build_id, attempt.attempt_id
        package = attempt.directory / "package"
        repair_md = attempt.directory / "REPAIR.md"
        if not repair_md.is_file() or not (package / "app.yaml").is_file():
            return None
        files = read_package_files(package)
        if sum(len(v) for v in files.values()) > QUICK_MAX_BYTES:
            return None
        references = ""
        for label, path in (
            ("APP CONTRACT", self._pipeline.resources.app_contract_reference),
            ("SDK REFERENCE", self._pipeline.resources.sdk_reference),
        ):
            if path.is_file():
                references += f"\n\n===== {label} =====\n{path.read_text(encoding='utf-8')}"
        repair_route = self._gateway.route(route.route_id, stage="builder_change")
        inference = self._pipeline.inference
        if inference is None:
            return None
        try:
            result = inference.call(
                repair_route,
                system=QUICK_REPAIR_SYSTEM,
                prompt=quick_repair_prompt(
                    repair_md.read_text(encoding="utf-8"), files, references
                ),
                schema=quick_change_schema(),
                scope_kind="quick_repair",
                scope_ref=attempt_id,
            )
        except Exception as exc:
            self._db.append(
                build_id, attempt_id, "build.quick_repair_declined", {"reason": str(exc)[:300]}
            )
            return None
        output = result.output if isinstance(result.output, dict) else {}
        edits = {
            str(f.get("path")): str(f.get("content"))
            for f in output.get("files") or []
            if isinstance(f, dict) and f.get("path")
        }
        if output.get("needs_full_build") or not edits:
            self._db.append(
                build_id,
                attempt_id,
                "build.quick_repair_declined",
                {"reason": str(output.get("reason") or "no files returned")[:300]},
            )
            return None
        try:
            source = load_source(package)
        except Exception as exc:
            self._db.append(
                build_id, attempt_id, "build.quick_repair_declined", {"reason": str(exc)[:300]}
            )
            return None
        problem = apply_edits(package, edits, source)
        if problem:
            self._db.append(
                build_id, attempt_id, "build.quick_repair_declined", {"reason": problem}
            )
            return None
        self._db.append(
            build_id,
            attempt_id,
            "build.quick_repair",
            {"changed_files": sorted(edits), "summary": str(output.get("summary") or "")[:300]},
        )
        return BuilderOutcome(
            "candidate",
            usage=result.usage,
            harness_exit={"quick_repair": True, "changed_files": sorted(edits)},
        )

    def _settle(
        self,
        record: BuildRecord,
        attempt: _Attempt,
        lineage: list[str],
        built: BuilderOutcome,
        budget: BuildBudget,
    ) -> tuple[VerificationOutcome, Path, BuildUsage | None, bool] | None:
        """Decide what the attempt means: terminal (cancelled, harness failure, ready) or a
        failed verification a repair may follow."""
        build_id, attempt_id = record.build_id, attempt.attempt_id

        def finish(status: str, category: FailureCategory | None) -> None:
            self._db.finish_attempt(attempt_id, status, category, built.usage, built.harness_exit)

        def with_plan() -> BuildRecord | None:
            # The full checks, waited for only when verification needs them.
            refreshed = self._await_plan(record, attempt)
            if refreshed is None:
                finish("failed", FailureCategory.PLATFORM_ERROR)
            return refreshed

        if built.status == "cancelled":
            finish("cancelled", FailureCategory.CANCELLED)
            return None  # cancel() already transitioned the build
        if built.status == "timed_out":
            # Out of time with work on disk (found in G1: a larger App used the whole attempt).
            # Check what exists, so the next attempt continues it within the same repair and
            # total limits instead of the build ending with budget unused. An unfinished
            # package can never become ready: it is verified as a failed builder result.
            self._db.append(
                build_id,
                attempt_id,
                "build.attempt_timed_out",
                {"max_attempt_seconds": budget.max_attempt_seconds},
            )
            planned = with_plan()
            if planned is None:
                return None
            timed = self._verify(
                planned, attempt_id, attempt.number, lineage, built, attempt.directory
            )
            if timed is None:
                finish("cancelled", FailureCategory.CANCELLED)
                return None
            ref = str((attempt.directory / "verification.report.json").relative_to(self._root))
            self._db.set_report_ref(attempt_id, ref)
            finish("failed", FailureCategory.HARNESS_TIMEOUT)
            return timed, attempt.directory, built.usage, True
        if built.status in _HARNESS_FAILURES:
            assert built.category is not None
            finish("failed", built.category)
            detail = {
                "max_attempt_seconds": budget.max_attempt_seconds,
                "error": built.error,
                "exit_code": built.harness_exit.get("exit_code"),
            }
            reason = _HARNESS_FAILURES[built.status]
            self._db.fail(build_id, attempt_id, reason, built.category, detail)
            return None
        # The harness claims a candidate, or reports failure. Either way the package is
        # verified, so a report exists; only a claimed candidate can become ready.
        outcome: VerificationOutcome | None
        pending: Any | None = None  # the verified run, kept when the plan was preliminary
        report_ref = str((attempt.directory / "verification.report.json").relative_to(self._root))
        if built.status == "candidate" and build_id in self._fast_lane:
            # The fast lane: the structural checks first, without waiting for the plan. A
            # module Alpha draws itself is ready on those alone; a custom screen carries on
            # with the full checks once the plan is here.
            outcome = self._verify(
                record, attempt_id, attempt.number, lineage, built, attempt.directory, first=True
            )
            if outcome is None:
                finish("cancelled", FailureCategory.CANCELLED)
                return None
            pending = outcome.pending
            if pending is not None:
                sealed = outcome.sealed
                if outcome.report.passed and sealed is not None and fast_eligible(sealed.source):
                    self._db.set_report_ref(attempt_id, report_ref)
                    finish("candidate", None)
                    self._deferred[build_id] = pending
                    self._ready(
                        record,
                        attempt_id,
                        attempt.number,
                        attempt.directory,
                        outcome,
                        report_ref,
                        checks={"status": "pending"},
                    )
                    return None
                planned = with_plan()
                if planned is None:
                    return None
                outcome = self._verify(
                    planned,
                    attempt_id,
                    attempt.number,
                    lineage,
                    built,
                    attempt.directory,
                    resume=pending,
                )
                if outcome is None:
                    finish("cancelled", FailureCategory.CANCELLED)
                    return None
        else:
            planned = with_plan()
            if planned is None:
                return None
            outcome = self._verify(
                planned, attempt_id, attempt.number, lineage, built, attempt.directory
            )
            if outcome is None:
                finish("cancelled", FailureCategory.CANCELLED)
                return None
            pending = outcome.pending
        report = outcome.report
        self._db.set_report_ref(attempt_id, report_ref)
        if built.status == "failed":
            category = built.category or FailureCategory.HARNESS_ERROR
            finish("failed", category)
            passed = sum(1 for c in report.checks if c.status is CheckStatus.PASSED)
            self._db.fail(
                build_id,
                attempt_id,
                f"harness_{(built.output or {}).get('status')}",
                category,
                {
                    "diagnostics": (built.output or {}).get("diagnostics"),
                    "checks_passed_anyway": passed,
                },
                validation=report.model_dump(mode="json"),
            )
            return None
        if report.passed and outcome.sealed is not None:
            finish("candidate", None)
            checks = None
            if build_id in self._preliminary and pending is not None:
                # Checked on the brief's examples only: ready, and the full checks follow.
                self._deferred[build_id] = pending
                passed = sum(
                    1 for c in report.checks if c.required and c.status is CheckStatus.PASSED
                )
                checks = {"status": "preliminary", "full": "pending", "checks_passed": passed}
            self._ready(
                record,
                attempt_id,
                attempt.number,
                attempt.directory,
                outcome,
                report_ref,
                checks=checks,
            )
            return None
        finish("failed", self._category_of(report))
        return outcome, attempt.directory, built.usage, False

    def _verify(
        self,
        record: BuildRecord,
        attempt_id: str,
        number: int,
        lineage: list[str],
        built: BuilderOutcome,
        attempt_dir: Path,
        *,
        first: bool = False,
        resume: Any | None = None,
    ) -> VerificationOutcome | None:
        """Verify the attempt's package. `first` runs the structural stages alone (the
        outcome's `pending` carries the run on); `resume` finishes such a run on the full plan."""
        build_id = record.build_id
        if resume is None:
            self._db.transition(
                build_id,
                new_state=BuildState.VALIDATING,
                event_kind="build.validating",
                payload={"attempt_id": attempt_id, "harness_status": built.status},
                attempt_id=attempt_id,
                expected={BuildState.BUILDING},
            )
        with self._lock:
            stop = self._stops.get(build_id)

        def on_check(check: CheckResult) -> None:
            self._db.append(
                build_id,
                attempt_id,
                "validation.check",
                {
                    "check": check.id,
                    "stage": check.stage,
                    "status": check.status.value,
                    "required": check.required,
                    "summary": check.summary,
                },
            )

        verifier = self._pipeline.verifier
        if resume is not None:
            resume.stop = stop
            outcome = verifier.verify_behaviour(resume, record.plan)
        else:
            outcome = (verifier.verify_structure if first else verifier.verify)(
                build_id=build_id,
                attempt_id=attempt_id,
                attempt_number=number,
                lineage=list(lineage),
                builder_status=BuildResultStatus.CANDIDATE
                if built.status == "candidate"
                else BuildResultStatus.FAILED,
                package_dir=attempt_dir / "package",
                attempt_dir=attempt_dir,
                plan=record.plan,
                expected_app_id=record.app_id,
                on_check=on_check,
                stop=stop,
            )
        if outcome is None or (stop is not None and stop.is_set()):
            return None
        report = outcome.report
        (attempt_dir / "verification.report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        if outcome.handler_report is not None:
            (attempt_dir / "handlers.report.json").write_text(
                json.dumps(outcome.handler_report, indent=2, default=str), encoding="utf-8"
            )
        for request in report.qualification_requests:
            self._db.record_dependency_request(build_id, attempt_id, request.model_dump())
        self._db.append(
            build_id,
            attempt_id,
            "validation.report",
            {
                "passed": report.passed,
                "package_sha256": report.package_sha256,
                "failed": _failed_ids(report),
                "skipped_required": [
                    c.id for c in report.checks if c.required and c.status is CheckStatus.SKIPPED
                ],
            },
        )
        return outcome

    def _ready(
        self,
        record: BuildRecord,
        attempt_id: str,
        number: int,
        attempt_dir: Path,
        outcome: VerificationOutcome,
        report_ref: str,
        checks: dict[str, Any] | None = None,
    ) -> None:
        sealed = outcome.sealed
        assert sealed is not None
        report = outcome.report
        candidate: dict[str, Any] = {
            "app_id": sealed.source.app_id,
            "name": sealed.source.name,
            "version_id": sealed.version_id,
            "package_sha256": sealed.package_sha256,
            "dependency_manifest_sha256": sealed.dependency_manifest_sha256,
            "runtime_profile_id": sealed.dependency_manifest.runtime_profile_id,
            "ui_build_profile_id": report.ui_build_profile_id,
            "actions": [a.id for a in sealed.source.actions],
            "has_ui": sealed.source.has_screen(),
            "has_screen": sealed.source.screen is not None,
            "version_ref": str(sealed.path.relative_to(self._root)),
            "report_ref": report_ref,
            "handlers_ref": str((attempt_dir / "handlers.report.json").relative_to(self._root)),
            "attempt_id": attempt_id,
            "attempt_number": number,
            "activated": False,
        }
        if checks is not None:
            candidate["checks"] = checks
        self._db.transition(
            record.build_id,
            new_state=BuildState.READY,
            event_kind="build.ready",
            payload={"candidate": candidate},
            attempt_id=attempt_id,
            expected={BuildState.VALIDATING},
            candidate=candidate,
            validation=report.model_dump(mode="json"),
        )

    @staticmethod
    def _category_of(report: VerificationReport) -> FailureCategory:
        if report.qualification_requests:
            return FailureCategory.DEPENDENCY_UNSUPPORTED
        failed = [c for c in report.checks if c.status is CheckStatus.FAILED]
        if failed and failed[0].id == "package.contract" and "no app.yaml" in failed[0].summary:
            return FailureCategory.NO_PACKAGE
        if failed and failed[0].stage in ("package", "deps", "seal"):
            return FailureCategory.INVALID_PACKAGE
        return FailureCategory.VALIDATION_FAILED


def _failed_ids(report: VerificationReport) -> list[str]:
    return [c.id for c in report.checks if c.status is CheckStatus.FAILED]
