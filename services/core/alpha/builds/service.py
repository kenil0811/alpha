"""BuildService: the build lifecycle (Current Release Specification §4, Blueprint §6).

State machine (only Core changes it):
    queued → building → validating → ready
                  ↑           ↓
                  └─ repairing ┘      (at most `max_repair_attempts` times)
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
from alpha.builds.store import (
    BuildRecord,
    BuildStore,
)
from alpha.builds.toolchain import PlatformResources
from alpha.builds.verify import CandidateVerifier, VerificationOutcome
from alpha.builds.workspace import (
    TargetProfiles,
    evidence_files,
    materialize,
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
    ) -> None:
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
        self._stops: dict[str, threading.Event] = {}  # build id -> stop verification
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
    ) -> BuildRecord:
        """Queue a build. `app_id`, when given, is the identity the platform assigned (the
        package must use it); otherwise the builder chooses one."""
        route = self._gateway.route(route_id)
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
            route_id=route.route_id,
            harness=route.harness,
            budget=budget,
            created_at=now,
            queued_payload={"route_id": route.route_id, "ahead": ahead},
        )
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

    def cancel(self, build_id: str) -> BuildRecord:
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
            payload={"termination": termination},
            terminal_reason="cancelled_by_user",
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
        return TargetProfiles(
            runtime=runtime, ui=self._pipeline.inventory.default_ui_profile(), app_id=app_id
        )

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
        max_attempts = 1 + budget.max_repair_attempts
        last: VerificationReport | None = None
        for number in range(1, max_attempts + 1):
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
            left = max_attempts - number
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
            timed = self._verify(
                record, attempt_id, attempt.number, lineage, built, attempt.directory
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
        outcome = self._verify(
            record, attempt_id, attempt.number, lineage, built, attempt.directory
        )
        if outcome is None:
            finish("cancelled", FailureCategory.CANCELLED)
            return None
        report = outcome.report
        report_ref = str((attempt.directory / "verification.report.json").relative_to(self._root))
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
            self._ready(record, attempt_id, attempt.number, attempt.directory, outcome, report_ref)
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
    ) -> VerificationOutcome | None:
        build_id = record.build_id
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

        outcome = self._pipeline.verifier.verify(
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
    ) -> None:
        sealed = outcome.sealed
        assert sealed is not None
        report = outcome.report
        candidate = {
            "app_id": sealed.source.app_id,
            "name": sealed.source.name,
            "version_id": sealed.version_id,
            "package_sha256": sealed.package_sha256,
            "dependency_manifest_sha256": sealed.dependency_manifest_sha256,
            "runtime_profile_id": sealed.dependency_manifest.runtime_profile_id,
            "ui_build_profile_id": report.ui_build_profile_id,
            "actions": [a.id for a in sealed.source.actions],
            "has_ui": sealed.source.ui is not None and sealed.source.ui.entry is not None,
            "version_ref": str(sealed.path.relative_to(self._root)),
            "report_ref": report_ref,
            "handlers_ref": str((attempt_dir / "handlers.report.json").relative_to(self._root)),
            "attempt_id": attempt_id,
            "attempt_number": number,
            "activated": False,
        }
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
