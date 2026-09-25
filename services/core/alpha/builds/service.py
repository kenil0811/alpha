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
from datetime import datetime, timedelta
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
    InvokeStep,
    Scenario,
    ValidationPlan,
    VerificationReport,
)
from pydantic import BaseModel, ConfigDict, Field

from alpha.builds.attempt import BuilderOutcome, BuilderProcess
from alpha.builds.preview import PreviewDeps, PreviewPlatform
from alpha.builds.toolchain import PlatformResources
from alpha.builds.verify import CandidateVerifier, VerificationOutcome
from alpha.builds.workspace import (
    TargetProfiles,
    evidence_files,
    materialize,
    render_repair,
)
from alpha.capabilities.errors import OperationFailed
from alpha.data.apps import AppRegistry
from alpha.data.packages import SealedPackage, load_source, sealed_manifest, verify_sealed
from alpha.execution.profiles import ProfileInventory
from alpha.execution.supervisor import WorkerHandle, WorkerSupervisor, process_alive
from alpha.models.gateway import ModelGateway, ModelRoute
from alpha.storage.control_store import ConflictError, ControlStore, NotFoundError, new_id, utc_now

log = logging.getLogger("alpha.builds")

# A repair attempt is not started with less than this much of the total budget left.
MIN_ATTEMPT_SECONDS = 60


def _dt(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class AcceptanceExample(BaseModel):
    """F02 input form: one action, one input, the exact expected output. Converted into a
    ValidationPlan scenario; kept so existing callers and the F02 qualification still work."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=64)
    input: dict[str, Any]
    expected: dict[str, Any]


def plan_from_examples(examples: list[AcceptanceExample]) -> ValidationPlan:
    return ValidationPlan(
        scenarios=[
            Scenario(
                id=f"example_{i + 1}",
                description=f"{e.action_id} returns exactly the expected output",
                steps=[
                    InvokeStep(
                        id="run", action=e.action_id, input=e.input, output=e.expected, exact=True
                    )
                ],
            )
            for i, e in enumerate(examples)
        ]
    )


class AttemptRecord(BaseModel):
    attempt_id: str
    number: int
    status: str
    failure_category: str | None = None
    workspace_ref: str
    started_at: str
    finished_at: str | None = None
    usage: dict[str, Any] | None = None
    harness_exit: dict[str, Any] | None = None
    report_ref: str | None = None


class BuildRecord(BaseModel):
    build_id: str
    state: BuildState
    goal: str
    instructions: str
    plan: ValidationPlan
    route_id: str
    harness: str
    budget: BuildBudget
    brief_ref: str
    created_at: str
    updated_at: str
    finished_at: str | None = None
    terminal_reason: str | None = None
    failure_category: str | None = None
    attempts: list[AttemptRecord]
    candidate: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    seed_package: str | None = None
    latest_sequence: int


class BuildNotReady(Exception):
    pass


class SeedUnavailable(Exception):
    pass


SEED_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


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


_SCHEMA = """
CREATE TABLE IF NOT EXISTS builds (
    build_id TEXT PRIMARY KEY,
    brief_ref TEXT NOT NULL,
    goal TEXT NOT NULL,
    instructions TEXT NOT NULL,
    acceptance_json TEXT NOT NULL,
    route_id TEXT NOT NULL,
    harness TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    terminal_reason TEXT,
    failure_category TEXT,
    candidate_json TEXT,
    validation_json TEXT,
    latest_sequence INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS build_attempts (
    attempt_id TEXT PRIMARY KEY,
    build_id TEXT NOT NULL REFERENCES builds(build_id),
    number INTEGER NOT NULL,
    status TEXT NOT NULL,
    failure_category TEXT,
    workspace_ref TEXT NOT NULL,
    pid INTEGER,
    pgid INTEGER,
    core_instance_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    usage_json TEXT,
    harness_exit_json TEXT,
    UNIQUE(build_id, number)
);
CREATE TABLE IF NOT EXISTS build_events (
    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    build_id TEXT NOT NULL REFERENCES builds(build_id),
    attempt_id TEXT,
    sequence INTEGER NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(build_id, sequence)
);
CREATE TABLE IF NOT EXISTS dependency_requests (
    request_id TEXT PRIMARY KEY,
    build_id TEXT NOT NULL REFERENCES builds(build_id),
    attempt_id TEXT NOT NULL,
    package TEXT NOT NULL,
    version TEXT,
    found_in TEXT NOT NULL,
    location TEXT NOT NULL,
    runtime_profile_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# Columns added after F02; an existing control store gains them on startup.
_MIGRATIONS = (
    ("builds", "plan_json", "TEXT"),
    ("builds", "seed_package", "TEXT"),
    ("build_attempts", "report_ref", "TEXT"),
)


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
        self._store = store
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
        store.execute_script(_SCHEMA)
        self._migrate()
        self._root.mkdir(parents=True, exist_ok=True)

    def _migrate(self) -> None:
        for table, column, kind in _MIGRATIONS:
            names = {r["name"] for r in self._store.query(f"PRAGMA table_info({table})")}
            if column not in names:
                self._store.execute_script(f"ALTER TABLE {table} ADD COLUMN {column} {kind};")

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
    ) -> BuildRecord:
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
                    "created_at": _dt(now),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (build_dir / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        with self._lock:
            ahead = len(self._waiting) + (1 if self._current else 0)
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO builds(build_id, brief_ref, goal, instructions, acceptance_json,
                   plan_json, seed_package, route_id, harness, budget_json, state, created_at,
                   updated_at, latest_sequence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                (
                    build_id,
                    brief_ref,
                    goal,
                    instructions,
                    "[]",
                    plan.model_dump_json(),
                    seed_package,
                    route.route_id,
                    route.harness,
                    budget.model_dump_json(),
                    BuildState.QUEUED.value,
                    _dt(now),
                    _dt(now),
                ),
            )
            self._append_locked(
                conn, build_id, None, "build.queued", {"route_id": route.route_id, "ahead": ahead}
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
        rows = self._store.query("SELECT * FROM builds WHERE build_id = ?", (build_id,))
        if not rows:
            raise NotFoundError(build_id)
        return self._row_to_record(rows[0])

    def list_builds(self, limit: int = 50) -> list[BuildRecord]:
        rows = self._store.query(
            "SELECT * FROM builds ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        )
        return [self._row_to_record(r) for r in rows]

    def events(self, build_id: str, after: int = 0, limit: int = 1000) -> list[BuildEvent]:
        self.get(build_id)
        rows = self._store.query(
            "SELECT * FROM build_events WHERE build_id = ? AND sequence > ?"
            " ORDER BY sequence LIMIT ?",
            (build_id, after, limit),
        )
        return [
            BuildEvent(
                event_id=r["event_id"],
                build_id=r["build_id"],
                attempt_id=r["attempt_id"],
                sequence=int(r["sequence"]),
                kind=r["kind"],
                occurred_at=datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00")),
                payload=json.loads(r["payload_json"]),
            )
            for r in rows
        ]

    def dependency_requests(self, build_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM dependency_requests"
        params: tuple[Any, ...] = ()
        if build_id is not None:
            sql += " WHERE build_id = ?"
            params = (build_id,)
        return [dict(r) for r in self._store.query(sql + " ORDER BY created_at", params)]

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
        self._transition(
            build_id,
            new_state=BuildState.CANCELLED,
            event_kind="build.cancelled",
            payload={"termination": termination},
            terminal_reason="cancelled_by_user",
            failure_category=FailureCategory.CANCELLED,
        )
        return self.get(build_id)

    def activate(self, build_id: str) -> dict[str, Any]:
        """Install a ready candidate's exact sealed bytes as the App's current Version, after
        rechecking the bytes and the profiles it was validated with (F08 builds the user-facing
        flow on this)."""
        record = self.get(build_id)
        if record.state is not BuildState.READY or not record.candidate:
            raise BuildNotReady(f"build {build_id} is {record.state.value}, not ready")
        candidate = record.candidate
        version_dir = self._root / candidate["version_ref"]
        try:
            version = self._pipeline.registry.activate_sealed(
                version_dir, candidate["package_sha256"]
            )
        except OperationFailed as exc:
            self._append(build_id, None, "build.activation_refused", exc.as_error())
            raise
        result = {
            "app_id": version.app_id,
            "version_id": version.version_id,
            "release_id": version.release_id,
            "package_sha256": version.package_sha256,
            "dependency_manifest_sha256": version.dependency_manifest_sha256,
            "runtime_profile_id": version.runtime_profile_id,
        }
        self._append(build_id, None, "build.activated", result)
        return result

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
        rows = self._store.query("SELECT * FROM build_attempts WHERE status = 'running'")
        for row in rows:
            entry: dict[str, Any] = {"attempt_id": row["attempt_id"], "build_id": row["build_id"]}
            pid, pgid = row["pid"], row["pgid"]
            if pid is not None and process_alive(int(pid)):
                entry["termination"] = self._supervisor.terminate_orphan(int(pgid))
                entry["reason"] = "core_restarted_builder_orphaned"
            else:
                entry["reason"] = "core_restarted_builder_lost"
            self._finish_attempt(
                row["attempt_id"], "interrupted", FailureCategory.INTERRUPTED, None, None
            )
            self._transition(
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
        placeholders = ",".join("?" for _ in TERMINAL_BUILD_STATES)
        stranded = self._store.query(
            f"SELECT build_id, state FROM builds WHERE state NOT IN ({placeholders})",
            tuple(s.value for s in TERMINAL_BUILD_STATES),
        )
        for row in stranded:
            reason = (
                "core_restarted_while_queued"
                if row["state"] == BuildState.QUEUED.value
                else "core_restarted_build_lost"
            )
            self._transition(
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
            self._transition(
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
            self._finish_attempt(
                real_attempt, "interrupted", FailureCategory.INTERRUPTED, None, None
            )
            self._transition(
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
        running = self._store.query(
            "SELECT attempt_id FROM build_attempts WHERE build_id = ? AND status = 'running'",
            (build_id,),
        )
        for row in running:
            self._finish_attempt(
                row["attempt_id"], "failed", FailureCategory.PLATFORM_ERROR, None, detail
            )
        self._transition(
            build_id,
            new_state=BuildState.FAILED,
            event_kind="build.failed",
            payload={"reason": "platform_error", **detail},
            terminal_reason="platform_error",
            failure_category=FailureCategory.PLATFORM_ERROR,
        )

    # ----- one build: attempts, verification, bounded repair -----------------------------

    def _targets(self) -> TargetProfiles | None:
        runtime = self._pipeline.inventory.default_app_profile()
        if runtime is None:
            return None
        return TargetProfiles(runtime=runtime, ui=self._pipeline.inventory.default_ui_profile())

    def _run_build(self, item: _QueuedBuild) -> None:
        build_id, route, budget = item.build_id, item.route, item.budget
        record = self.get(build_id)
        targets = self._targets()
        if targets is None:
            self._transition(
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
                self._fail(
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
            outcome, attempt_dir, usage = step
            if usage is not None and usage.cost_usd is not None:
                spent_usd += usage.cost_usd
            report = outcome.report
            last = report
            left = max_attempts - number
            if left == 0:
                self._fail(
                    build_id,
                    report.attempt_id,
                    "repair_limit_reached",
                    self._category_of(report),
                    {"attempts": len(lineage), "failed_checks": _failed_ids(report)},
                    validation=report.model_dump(mode="json"),
                )
                return
            repair = render_repair(report, number, left - 1)
            feedback = evidence_files(report, attempt_dir)
            previous_package = attempt_dir / "package"
            self._transition(
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
    ) -> tuple[VerificationOutcome, Path, BuildUsage | None] | None:
        """Run one attempt. Returns the failed verification when a repair may follow, or None
        once the build reached a terminal state."""
        build_id = record.build_id
        attempt_id = new_id("attempt")
        lineage.append(attempt_id)
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
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO build_attempts(attempt_id, build_id, number, status, workspace_ref,
                   core_instance_id, started_at) VALUES (?,?,?,?,?,?,?)""",
                (
                    attempt_id,
                    build_id,
                    number,
                    "running",
                    request.workspace_lease_ref,
                    self._instance_id,
                    _dt(now),
                ),
            )
        self._transition(
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
        key = f"{build_id}:{attempt_id}"

        def on_launch(handle: WorkerHandle) -> bool:
            with self._lock:
                self._active[key] = handle
                # cancel() collects handles under this lock: either it saw this one, or the
                # request is visible here. A build cancelled while it waited never builds.
                stop_now = build_id in self._cancel_requested or self._closing
                if stop_now:
                    self._cancel_requested.add(build_id)
            with self._store.transaction() as conn:
                conn.execute(
                    "UPDATE build_attempts SET pid = ?, pgid = ? WHERE attempt_id = ?",
                    (handle.pid, handle.pgid, attempt_id),
                )
            return stop_now

        def on_exit() -> bool:
            with self._lock:
                self._active.pop(key, None)
                return build_id in self._cancel_requested

        job = {
            "request": request.model_dump(mode="json"),
            "harness": route.harness,
            "workspace": str(attempt_dir),
            "goal": record.goal,
            "instructions": record.instructions,
            "model": route.model,
            "candidate_python": str(targets.runtime.python),
            "targets": targets.identities(),
            "fake_packages_dir": str(self._pipeline.fake_packages_dir)
            if route.harness == "fake" and self._pipeline.fake_packages_dir
            else None,
        }
        if seeded:
            # Qualification: the first candidate is a known package, verified like any claim.
            built = BuilderOutcome("candidate", harness_exit={"seeded": record.seed_package})
        else:
            built = self._builder.run(
                attempt_id=attempt_id,
                job=job,
                deadline_seconds=budget.max_attempt_seconds,
                emit=lambda kind, payload: self._append(build_id, attempt_id, kind, payload),
                on_launch=on_launch,
                on_exit=on_exit,
            )
        if built.usage is not None:
            self._gateway.record_usage(route.route_id, "build_attempt", attempt_id, built.usage)
        if built.status == "cancelled":
            self._finish_attempt(
                attempt_id, "cancelled", FailureCategory.CANCELLED, built.usage, built.harness_exit
            )
            return None  # cancel() already transitioned the build
        if built.status in ("timed_out", "no_result", "launch_failed"):
            self._finish_attempt(
                attempt_id, "failed", built.category, built.usage, built.harness_exit
            )
            reason = {
                "timed_out": "attempt_deadline_exceeded",
                "no_result": "builder_returned_no_result",
                "launch_failed": "builder_launch_failed",
            }[built.status]
            assert built.category is not None
            self._fail(
                build_id,
                attempt_id,
                reason,
                built.category,
                {
                    "max_attempt_seconds": budget.max_attempt_seconds,
                    "error": built.error,
                    "exit_code": built.harness_exit.get("exit_code"),
                },
            )
            return None
        # The harness claims a candidate, or reports failure. Either way the package (if any)
        # is verified, so a report exists; only a claimed candidate can become ready.
        outcome = self._verify(record, attempt_id, number, lineage, built, attempt_dir)
        if outcome is None:
            self._finish_attempt(
                attempt_id, "cancelled", FailureCategory.CANCELLED, built.usage, built.harness_exit
            )
            return None
        report = outcome.report
        report_ref = str((attempt_dir / "verification.report.json").relative_to(self._root))
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE build_attempts SET report_ref = ? WHERE attempt_id = ?",
                (report_ref, attempt_id),
            )
        if built.status == "failed":
            category = built.category or FailureCategory.HARNESS_ERROR
            self._finish_attempt(attempt_id, "failed", category, built.usage, built.harness_exit)
            status = str((built.output or {}).get("status"))
            self._fail(
                build_id,
                attempt_id,
                f"harness_{status}",
                category,
                {
                    "diagnostics": (built.output or {}).get("diagnostics"),
                    "checks_passed_anyway": sum(
                        1 for c in report.checks if c.status is CheckStatus.PASSED
                    ),
                },
                validation=report.model_dump(mode="json"),
            )
            return None
        if report.passed and outcome.sealed is not None:
            self._finish_attempt(attempt_id, "candidate", None, built.usage, built.harness_exit)
            self._ready(record, attempt_id, number, attempt_dir, outcome, report_ref)
            return None
        self._finish_attempt(
            attempt_id, "failed", self._category_of(report), built.usage, built.harness_exit
        )
        return outcome, attempt_dir, built.usage

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
        self._transition(
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
            self._append(
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
            self._record_dependency_request(build_id, attempt_id, request.model_dump())
        self._append(
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
        self._transition(
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

    # ----- persistence helpers ------------------------------------------------------------

    def _record_dependency_request(
        self, build_id: str, attempt_id: str, request: dict[str, Any]
    ) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO dependency_requests(request_id, build_id, attempt_id, package,
                   version, found_in, location, runtime_profile_id, reason, state, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("depreq"),
                    build_id,
                    attempt_id,
                    request["package"],
                    request.get("version"),
                    request["found_in"],
                    request["where"],
                    request["runtime_profile_id"],
                    request["reason"],
                    "requested",
                    _dt(utc_now()),
                ),
            )
            self._append_locked(
                conn, build_id, attempt_id, "dependency.qualification_requested", request
            )

    def _append(
        self, build_id: str, attempt_id: str | None, kind: str, payload: dict[str, Any]
    ) -> None:
        with self._store.transaction() as conn:
            self._append_locked(conn, build_id, attempt_id, kind, payload)

    def _append_locked(
        self, conn: Any, build_id: str, attempt_id: str | None, kind: str, payload: dict[str, Any]
    ) -> None:
        row = conn.execute(
            "SELECT latest_sequence FROM builds WHERE build_id = ?", (build_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(build_id)
        sequence = int(row["latest_sequence"]) + 1
        now = _dt(utc_now())
        conn.execute(
            "INSERT INTO build_events(event_id, build_id, attempt_id, sequence, kind, occurred_at,"
            " payload_json) VALUES (?,?,?,?,?,?,?)",
            (
                new_id("bevt"),
                build_id,
                attempt_id,
                sequence,
                kind,
                now,
                json.dumps(payload, sort_keys=True, default=str),
            ),
        )
        conn.execute(
            "UPDATE builds SET latest_sequence = ?, updated_at = ? WHERE build_id = ?",
            (sequence, now, build_id),
        )

    def _transition(
        self,
        build_id: str,
        *,
        new_state: BuildState,
        event_kind: str,
        payload: dict[str, Any],
        attempt_id: str | None = None,
        expected: set[BuildState] | None = None,
        terminal_reason: str | None = None,
        failure_category: FailureCategory | None = None,
        candidate: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
    ) -> None:
        now = _dt(utc_now())
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT state FROM builds WHERE build_id = ?", (build_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(build_id)
            current = BuildState(row["state"])
            if current in TERMINAL_BUILD_STATES:
                self._append_locked(
                    conn,
                    build_id,
                    attempt_id,
                    "build.transition_skipped",
                    {"attempted": new_state.value, "current": current.value},
                )
                return
            if expected is not None and current not in expected:
                raise ConflictError(f"build {build_id} is {current.value}, expected {expected}")
            sets = ["state = ?", "updated_at = ?"]
            params: list[Any] = [new_state.value, now]
            if new_state in TERMINAL_BUILD_STATES:
                sets += ["finished_at = ?", "terminal_reason = ?", "failure_category = ?"]
                params += [
                    now,
                    terminal_reason,
                    failure_category.value if failure_category else None,
                ]
            if candidate is not None:
                sets.append("candidate_json = ?")
                params.append(json.dumps(candidate))
            if validation is not None:
                sets.append("validation_json = ?")
                params.append(json.dumps(validation, default=str))
            params.append(build_id)
            conn.execute(f"UPDATE builds SET {', '.join(sets)} WHERE build_id = ?", params)
            self._append_locked(conn, build_id, attempt_id, event_kind, payload)

    def _fail(
        self,
        build_id: str,
        attempt_id: str,
        reason: str,
        category: FailureCategory,
        payload: dict[str, Any],
        validation: dict[str, Any] | None = None,
    ) -> None:
        self._transition(
            build_id,
            new_state=BuildState.FAILED,
            event_kind="build.failed",
            payload={"reason": reason, "failure_category": category.value, **payload},
            attempt_id=attempt_id,
            terminal_reason=reason,
            failure_category=category,
            validation=validation,
        )

    def _finish_attempt(
        self,
        attempt_id: str,
        status: str,
        category: FailureCategory | None,
        usage: BuildUsage | None,
        harness_exit: dict[str, Any] | None,
    ) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE build_attempts SET status = ?, failure_category = ?, finished_at = ?,
                   usage_json = ?, harness_exit_json = ? WHERE attempt_id = ?""",
                (
                    status,
                    category.value if category else None,
                    _dt(utc_now()),
                    usage.model_dump_json() if usage else None,
                    json.dumps(harness_exit, default=str) if harness_exit else None,
                    attempt_id,
                ),
            )

    def _row_to_record(self, row: Any) -> BuildRecord:
        attempts = self._store.query(
            "SELECT * FROM build_attempts WHERE build_id = ? ORDER BY number", (row["build_id"],)
        )
        if row["plan_json"]:
            plan = ValidationPlan.model_validate_json(row["plan_json"])
        else:  # an F02 build: its examples are the plan
            plan = plan_from_examples(
                [AcceptanceExample.model_validate(e) for e in json.loads(row["acceptance_json"])]
            )
        return BuildRecord(
            build_id=row["build_id"],
            state=BuildState(row["state"]),
            goal=row["goal"],
            instructions=row["instructions"],
            plan=plan,
            route_id=row["route_id"],
            harness=row["harness"],
            budget=BuildBudget.model_validate_json(row["budget_json"]),
            brief_ref=row["brief_ref"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
            terminal_reason=row["terminal_reason"],
            failure_category=row["failure_category"],
            attempts=[
                AttemptRecord(
                    attempt_id=a["attempt_id"],
                    number=int(a["number"]),
                    status=a["status"],
                    failure_category=a["failure_category"],
                    workspace_ref=a["workspace_ref"],
                    started_at=a["started_at"],
                    finished_at=a["finished_at"],
                    usage=json.loads(a["usage_json"]) if a["usage_json"] else None,
                    harness_exit=json.loads(a["harness_exit_json"])
                    if a["harness_exit_json"]
                    else None,
                    report_ref=a["report_ref"],
                )
                for a in attempts
            ],
            candidate=json.loads(row["candidate_json"]) if row["candidate_json"] else None,
            validation=json.loads(row["validation_json"]) if row["validation_json"] else None,
            seed_package=row["seed_package"],
            latest_sequence=int(row["latest_sequence"]),
        )


def _failed_ids(report: VerificationReport) -> list[str]:
    return [c.id for c in report.checks if c.status is CheckStatus.FAILED]
