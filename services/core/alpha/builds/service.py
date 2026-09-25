"""BuildService: workspace lease, builder worker invocation, attempts, independent validation
and candidate sealing (Implementation Blueprint section 6, Current Release Specification §4).

State machine (only Core changes it): queued → building → validating → ready, or failed /
cancelled. A harness saying "done" never makes a candidate; the package must exist, pass layout
and manifest checks, have its real handler resolved in a disposable worker, and return the
independently specified acceptance outputs. Every attempt, event and usage record is retained.

One builder runs at a time (Implementation Blueprint §7, Prototype_Scope_and_Acceptance §7):
submitted builds wait in `queued`, in submission order, and a single dispatcher thread starts
them. Nothing about a waiting build survives a restart; startup marks it interrupted.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pwd
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
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
from pydantic import BaseModel, ConfigDict, Field

from alpha.execution.supervisor import WorkerHandle, WorkerSupervisor, process_alive
from alpha.execution.worker_io import StderrTail, read_worker_messages
from alpha.models.gateway import ModelGateway, ModelRoute
from alpha.storage.control_store import ConflictError, ControlStore, NotFoundError, new_id, utc_now

log = logging.getLogger("alpha.builds")

MAX_PACKAGE_FILES = 200
MAX_PACKAGE_BYTES = 2_000_000
ALLOWED_TOP_LEVEL = {"app.yaml", "src", "tests", "README.md"}
RUNNER_TIMEOUT_SECONDS = 60


def _dt(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class _QueuedBuild:
    build_id: str
    route: ModelRoute
    budget: BuildBudget


class AcceptanceExample(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=64)
    input: dict[str, Any]
    expected: dict[str, Any]


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


class BuildRecord(BaseModel):
    build_id: str
    state: BuildState
    goal: str
    instructions: str
    acceptance_examples: list[AcceptanceExample]
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
    latest_sequence: int


class BuildNotReady(Exception):
    pass


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
"""


class BuildService:
    def __init__(
        self,
        store: ControlStore,
        supervisor: WorkerSupervisor,
        gateway: ModelGateway,
        *,
        builds_root: Path,
        platform_python: Path,
        builder_path: str,
        builder_home: str | None,
        instance_id: str,
    ) -> None:
        self._store = store
        self._supervisor = supervisor
        self._gateway = gateway
        self._root = builds_root
        self._python = platform_python
        self._builder_path = builder_path
        self._builder_home = builder_home
        self._instance_id = instance_id
        self._lock = threading.Lock()
        self._active: dict[str, WorkerHandle] = {}  # "build_id:attempt_id" -> handle
        self._cancel_requested: set[str] = set()  # build ids
        self._timed_out: set[str] = set()  # attempt ids
        # The one-builder queue. The condition shares self._lock.
        self._waiting: deque[_QueuedBuild] = deque()
        self._wakeup = threading.Condition(self._lock)
        self._current: str | None = None  # build id the dispatcher is working on
        self._closing = False
        self._dispatcher: threading.Thread | None = None
        store.execute_script(_SCHEMA)
        self._root.mkdir(parents=True, exist_ok=True)

    # ----- public API -------------------------------------------------------------------

    def submit(
        self,
        *,
        goal: str,
        acceptance_examples: list[AcceptanceExample],
        instructions: str = "",
        route_id: str = "fake",
        max_cost_usd: float | None = None,
    ) -> BuildRecord:
        route = self._gateway.route(route_id)
        budget = self._gateway.budget(route, max_cost_usd)
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
                    "acceptance_examples": [e.model_dump() for e in acceptance_examples],
                    "created_at": _dt(now),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        with self._lock:
            ahead = len(self._waiting) + (1 if self._current else 0)
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO builds(build_id, brief_ref, goal, instructions, acceptance_json,
                   route_id, harness, budget_json, state, created_at, updated_at, latest_sequence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,0)""",
                (
                    build_id,
                    brief_ref,
                    goal,
                    instructions,
                    json.dumps([e.model_dump() for e in acceptance_examples]),
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

    def cancel(self, build_id: str) -> BuildRecord:
        record = self.get(build_id)
        if record.state in TERMINAL_BUILD_STATES:
            raise ConflictError(f"build {build_id} already {record.state.value}")
        with self._lock:
            self._cancel_requested.add(build_id)
            self._waiting = deque(q for q in self._waiting if q.build_id != build_id)
            handles = [h for aid, h in self._active.items() if aid.startswith(build_id + ":")]
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

    def invoke(
        self, build_id: str, action_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a sealed candidate's declared action in a disposable worker after verifying
        the package bytes still match the sealed digest."""
        record = self.get(build_id)
        if record.state is not BuildState.READY or not record.candidate:
            raise BuildNotReady(f"build {build_id} is {record.state.value}, not ready")
        package_dir = self._root / record.candidate["package_ref"]
        index = self._seal_index(package_dir)
        if index["source_digest"] != record.candidate["source_digest"]:
            raise BuildNotReady("candidate package bytes differ from the sealed digest; refusing")
        if action_id not in record.candidate["actions"]:
            raise BuildNotReady(f"action {action_id!r} is not declared by this candidate")
        outcome = self._run_candidate(package_dir, action_id, [{"input": input_payload}])
        return outcome

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
        # Nothing else survives a restart: a build that was waiting for the builder, or whose
        # attempt never recorded a process, cannot continue and is not started again.
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
            try:
                self._attempt(item.build_id, 1, item.route, item.budget)
            except Exception as exc:
                # A platform fault in one build must not stall every build behind it.
                log.exception("build %s failed inside Core", item.build_id)
                self._fail_unexpected(item.build_id, exc)
            finally:
                with self._lock:
                    self._current = None

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

    # ----- attempt -----------------------------------------------------------------------

    def _attempt(self, build_id: str, number: int, route: ModelRoute, budget: BuildBudget) -> None:
        attempt_id = new_id("attempt")
        key = f"{build_id}:{attempt_id}"
        workspace = self._root / build_id / f"attempt-{number}"
        workspace.mkdir(parents=True, exist_ok=False)
        record = self.get(build_id)
        now = utc_now()
        request = BuildRequest(
            build_id=build_id,
            attempt_id=attempt_id,
            attempt_number=number,
            brief_ref=record.brief_ref,
            context_snapshot_ref=f"{build_id}.context.synthetic",
            template_profile="pure-python-0.2",
            sdk_profile="none",
            dependency_profile="platform-runtime-3.13.9",
            validation_plan_ref=f"{build_id}.acceptance",
            model_route_ref=route.route_id,
            budget=budget,
            workspace_lease_ref=str(workspace.relative_to(self._root)),
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
            payload={"attempt_id": attempt_id, "number": number, "harness": route.harness},
            attempt_id=attempt_id,
            expected={BuildState.QUEUED, BuildState.REPAIRING},
        )
        try:
            # The builder profile runs the founder's own CLI login (decision 2026-09-25): it needs
            # the account name and, when configured, the real home. Derived from the process
            # owner, never from ambient environment.
            owner = pwd.getpwuid(os.getuid()).pw_name
            extra_env = {"PATH": self._builder_path, "USER": owner, "LOGNAME": owner}
            if self._builder_home:
                extra_env["HOME"] = self._builder_home
            handle = self._supervisor.launch("builder", attempt_id, extra_env=extra_env)
        except Exception as exc:
            log.exception("builder launch failed for %s", build_id)
            self._finish_attempt(
                attempt_id, "failed", FailureCategory.HARNESS_UNAVAILABLE, None, {"error": str(exc)}
            )
            self._transition(
                build_id,
                new_state=BuildState.FAILED,
                event_kind="build.failed",
                payload={"reason": "builder_launch_failed", "error": str(exc)},
                terminal_reason="builder_launch_failed",
                failure_category=FailureCategory.HARNESS_UNAVAILABLE,
                attempt_id=attempt_id,
            )
            return
        with self._lock:
            self._active[key] = handle
            # cancel() collects handles under this lock: either it saw this one, or the
            # request is visible here. A build cancelled while it waited never builds.
            stop_now = build_id in self._cancel_requested or self._closing
            if stop_now:
                self._cancel_requested.add(build_id)
        if stop_now:
            self._supervisor.terminate(handle)
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE build_attempts SET pid = ?, pgid = ? WHERE attempt_id = ?",
                (handle.pid, handle.pgid, attempt_id),
            )
        job = {
            "request": request.model_dump(mode="json"),
            "harness": route.harness,
            "workspace": str(workspace),
            "goal": record.goal,
            "instructions": record.instructions,
            "acceptance_examples": [e.model_dump() for e in record.acceptance_examples],
            "model": route.model,
            "platform_python": str(self._python),
        }
        try:
            assert handle.process.stdin is not None
            handle.process.stdin.write(json.dumps(job) + "\n")
            handle.process.stdin.close()
        except (BrokenPipeError, OSError) as exc:
            self._append(build_id, attempt_id, "builder.stdin_error", {"error": str(exc)})

        timer = threading.Timer(
            budget.max_attempt_seconds, self._on_timeout, args=(key, attempt_id)
        )
        timer.daemon = True
        timer.start()
        collected: dict[str, Any] = {"result": None, "error": None}

        def on_message(message: dict[str, Any]) -> None:
            kind = message.get("kind")
            if kind == "progress":
                stage = message.get("stage")
                if stage == "harness_event":
                    self._append(
                        build_id,
                        attempt_id,
                        f"harness.{message.get('event', 'event')}",
                        message.get("payload") or {},
                    )
                else:
                    self._append(
                        build_id,
                        attempt_id,
                        f"builder.{stage}",
                        {k: v for k, v in message.items() if k not in ("kind", "stage")},
                    )
            elif kind == "result":
                collected["result"] = message.get("output")
                self._append(
                    build_id,
                    attempt_id,
                    "builder.result",
                    {"summary": _summarize_result(message.get("output"))},
                )
            elif kind == "error":
                collected["error"] = message
                self._append(build_id, attempt_id, "builder.error", message)

        reader = threading.Thread(
            target=read_worker_messages,
            args=(
                handle,
                on_message,
                lambda line: self._append(build_id, attempt_id, "builder.stdout", {"line": line}),
            ),
            daemon=True,
        )
        reader.start()
        stderr = StderrTail(handle, 2000)
        exit_code = handle.process.wait()
        timer.cancel()
        descendants = self._supervisor.terminate(handle)
        reader.join(timeout=5.0)
        stderr_tail = stderr.text()
        with self._lock:
            self._active.pop(key, None)
            cancelled = build_id in self._cancel_requested
            timed_out = attempt_id in self._timed_out
            self._timed_out.discard(attempt_id)
        harness_exit = {
            "exit_code": exit_code,
            "descendant_cleanup": descendants,
            "stderr_tail": stderr_tail,
        }
        self._append(build_id, attempt_id, "builder.exited", harness_exit)

        output = collected["result"] if isinstance(collected["result"], dict) else None
        usage = None
        if output and isinstance(output.get("usage"), dict):
            try:
                usage = BuildUsage.model_validate(output["usage"])
            except Exception:
                usage = None
        if usage is not None:
            self._gateway.record_usage(route.route_id, "build_attempt", attempt_id, usage)

        if cancelled:
            self._finish_attempt(
                attempt_id, "cancelled", FailureCategory.CANCELLED, usage, harness_exit
            )
            return  # cancel() already transitioned the build
        if timed_out:
            self._finish_attempt(
                attempt_id, "failed", FailureCategory.HARNESS_TIMEOUT, usage, harness_exit
            )
            self._fail(
                build_id,
                attempt_id,
                "attempt_deadline_exceeded",
                FailureCategory.HARNESS_TIMEOUT,
                {"max_attempt_seconds": budget.max_attempt_seconds},
            )
            return
        if output is None:
            category = (
                FailureCategory.HARNESS_ERROR
                if collected["error"]
                else FailureCategory.HARNESS_UNAVAILABLE
            )
            self._finish_attempt(attempt_id, "failed", category, usage, harness_exit)
            self._fail(
                build_id,
                attempt_id,
                "builder_returned_no_result",
                category,
                {"error": collected["error"], "exit_code": exit_code},
            )
            return
        status = str(output.get("status"))
        if status != BuildResultStatus.CANDIDATE.value:
            category = FailureCategory(
                output.get("failure_category") or FailureCategory.HARNESS_ERROR.value
            )
            self._finish_attempt(attempt_id, "failed", category, usage, harness_exit)
            self._fail(
                build_id,
                attempt_id,
                f"harness_{status}",
                category,
                {"diagnostics": output.get("diagnostics")},
            )
            return
        # Harness claims a candidate: verify independently before believing it.
        self._validate(build_id, attempt_id, workspace, record, usage, harness_exit)

    def _on_timeout(self, key: str, attempt_id: str) -> None:
        with self._lock:
            handle = self._active.get(key)
            if handle is None:
                return
            self._timed_out.add(attempt_id)
        build_id = key.split(":", 1)[0]
        self._append(
            build_id, attempt_id, "builder.timeout", {"reason": "attempt_deadline_exceeded"}
        )
        self._supervisor.terminate(handle)

    # ----- validation and sealing ---------------------------------------------------------

    def _validate(
        self,
        build_id: str,
        attempt_id: str,
        workspace: Path,
        record: BuildRecord,
        usage: BuildUsage | None,
        harness_exit: dict[str, Any],
    ) -> None:
        self._transition(
            build_id,
            new_state=BuildState.VALIDATING,
            event_kind="build.validating",
            payload={"attempt_id": attempt_id},
            attempt_id=attempt_id,
            expected={BuildState.BUILDING},
        )
        package_dir = workspace / "package"
        checks: list[dict[str, Any]] = []

        def check(name: str, ok: bool, detail: Any = None) -> bool:
            checks.append({"check": name, "passed": ok, "detail": detail})
            self._append(
                build_id,
                attempt_id,
                "validation.check",
                {"check": name, "passed": ok, "detail": detail},
            )
            return ok

        report: dict[str, Any] = {"attempt_id": attempt_id, "checks": checks, "passed": False}

        def finish_failed(category: FailureCategory, reason: str) -> None:
            report["failure_category"] = category.value
            (workspace / "validation.report.json").write_text(
                json.dumps(report, indent=2, default=str), encoding="utf-8"
            )
            self._finish_attempt(attempt_id, "failed", category, usage, harness_exit)
            self._fail(
                build_id, attempt_id, reason, category, {"validation": report}, validation=report
            )

        if not check(
            "package_present", package_dir.is_dir() and (package_dir / "app.yaml").is_file()
        ):
            finish_failed(FailureCategory.NO_PACKAGE, "no_package_written")
            return
        stripped = _strip_bytecode(package_dir)
        if stripped:
            self._append(build_id, attempt_id, "validation.normalized", {"removed": stripped})
        try:
            index = self._seal_index(package_dir)
            check(
                "package_layout",
                True,
                {"files": len(index["files"]), "bytes": index["total_bytes"]},
            )
        except ValueError as exc:
            check("package_layout", False, str(exc))
            finish_failed(FailureCategory.INVALID_PACKAGE, "invalid_package_layout")
            return
        try:
            manifest = _parse_manifest(package_dir / "app.yaml")
            action_ids = [a["id"] for a in manifest["actions"]]
            check("manifest", True, {"app_id": manifest["app_id"], "actions": action_ids})
        except ValueError as exc:
            check("manifest", False, str(exc))
            finish_failed(FailureCategory.INVALID_PACKAGE, "invalid_manifest")
            return

        # Independent acceptance: expected outputs come from the brief, never from the candidate.
        by_action: dict[str, list[AcceptanceExample]] = {}
        for example in record.acceptance_examples:
            by_action.setdefault(example.action_id, []).append(example)
        all_passed = True
        for action_id, examples in by_action.items():
            if action_id not in action_ids:
                all_passed = (
                    check(f"acceptance:{action_id}:declared", False, "action not declared")
                    and all_passed
                )
                continue
            outcome = self._run_candidate(
                package_dir, action_id, [{"input": e.input} for e in examples]
            )
            if outcome.get("kind") != "result":
                all_passed = check(f"acceptance:{action_id}:binding", False, outcome) and all_passed
                continue
            check(
                f"acceptance:{action_id}:binding",
                True,
                {
                    "handler": outcome["output"].get("handler"),
                    "signature": outcome["output"].get("signature"),
                },
            )
            calls = outcome["output"].get("calls", [])
            for i, example in enumerate(examples):
                call = calls[i] if i < len(calls) else {"ok": False, "error": "no outcome"}
                ok = bool(call.get("ok")) and call.get("output") == example.expected
                detail = {
                    "input": example.input,
                    "expected": example.expected,
                    "observed": call.get("output", call.get("error")),
                }
                all_passed = check(f"acceptance:{action_id}:{i}", ok, detail) and all_passed
        report["passed"] = all_passed
        (workspace / "package.index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")
        (workspace / "validation.report.json").write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        if not all_passed:
            finish_failed(FailureCategory.VALIDATION_FAILED, "acceptance_failed")
            return
        candidate = {
            "package_ref": str(package_dir.relative_to(self._root)),
            "source_digest": index["source_digest"],
            "actions": action_ids,
            "app_id": manifest["app_id"],
            "validation_report_ref": str(
                (workspace / "validation.report.json").relative_to(self._root)
            ),
            "package_index_ref": str((workspace / "package.index.json").relative_to(self._root)),
        }
        self._finish_attempt(attempt_id, "candidate", None, usage, harness_exit)
        self._transition(
            build_id,
            new_state=BuildState.READY,
            event_kind="build.ready",
            payload={"candidate": candidate},
            attempt_id=attempt_id,
            expected={BuildState.VALIDATING},
            candidate=candidate,
            validation=report,
        )

    def _seal_index(self, package_dir: Path) -> dict[str, Any]:
        root = package_dir.resolve()
        files: list[dict[str, Any]] = []
        total = 0
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                raise ValueError(f"symlink not allowed: {relative}")
            if path.is_dir():
                if "__pycache__" in path.parts:
                    raise ValueError(f"bytecode cache not allowed: {relative}")
                continue
            if not path.is_file():
                raise ValueError(f"unsupported entry: {relative}")
            if not path.resolve().is_relative_to(root):
                raise ValueError(f"path escapes package: {relative}")
            top = relative.split("/", 1)[0]
            if top not in ALLOWED_TOP_LEVEL:
                raise ValueError(f"unexpected top-level entry: {top}")
            if (
                path.suffix in (".pyc", ".so", ".dylib")
                or os.access(path, os.X_OK)
                and path.suffix != ".py"
            ):
                raise ValueError(f"undeclared executable or binary asset: {relative}")
            data = path.read_bytes()
            total += len(data)
            files.append(
                {"path": relative, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            )
        if len(files) > MAX_PACKAGE_FILES or total > MAX_PACKAGE_BYTES:
            raise ValueError("package exceeds size limits")
        digest = hashlib.sha256()
        for entry in files:
            digest.update(f"{entry['path']}\0{entry['sha256']}\n".encode())
        return {
            "files": files,
            "total_bytes": total,
            "source_digest": "sha256:" + digest.hexdigest(),
            "sealed_at": _dt(utc_now()),
            "toolchain": {"python": str(self._python)},
        }

    def _run_candidate(
        self, package_dir: Path, action_id: str, calls: list[dict[str, Any]]
    ) -> dict[str, Any]:
        runner_id = new_id("runner")
        handle = self._supervisor.launch("candidate_runner", runner_id)
        collected: dict[str, Any] = {"result": None, "error": None}
        try:
            assert handle.process.stdin is not None
            handle.process.stdin.write(
                json.dumps(
                    {"package_dir": str(package_dir), "action_id": action_id, "calls": calls}
                )
                + "\n"
            )
            handle.process.stdin.close()

            def on_message(message: dict[str, Any]) -> None:
                if message.get("kind") == "result":
                    collected["result"] = message
                elif message.get("kind") == "error":
                    collected["error"] = message

            reader = threading.Thread(
                target=read_worker_messages,
                args=(handle, on_message, lambda _line: None),
                daemon=True,
            )
            reader.start()
            stderr = StderrTail(handle, 1000)
            try:
                exit_code = handle.process.wait(timeout=RUNNER_TIMEOUT_SECONDS)
            except Exception:
                self._supervisor.terminate(handle)
                return {
                    "kind": "error",
                    "code": "runner_timeout",
                    "message": f"candidate runner exceeded {RUNNER_TIMEOUT_SECONDS}s",
                }
            reader.join(timeout=5)
        finally:
            self._supervisor.terminate(handle)
        if collected["result"] is not None:
            return {
                "kind": "result",
                "output": collected["result"].get("output", {}),
                "exit_code": exit_code,
            }
        if collected["error"] is not None:
            return {
                "kind": "error",
                **{k: v for k, v in collected["error"].items() if k != "kind"},
                "exit_code": exit_code,
            }
        return {
            "kind": "error",
            "code": "runner_no_output",
            "message": stderr.text(),
            "exit_code": exit_code,
        }

    # ----- persistence helpers ------------------------------------------------------------

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
        return BuildRecord(
            build_id=row["build_id"],
            state=BuildState(row["state"]),
            goal=row["goal"],
            instructions=row["instructions"],
            acceptance_examples=[
                AcceptanceExample.model_validate(e) for e in json.loads(row["acceptance_json"])
            ],
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
                )
                for a in attempts
            ],
            candidate=json.loads(row["candidate_json"]) if row["candidate_json"] else None,
            validation=json.loads(row["validation_json"]) if row["validation_json"] else None,
            latest_sequence=int(row["latest_sequence"]),
        )


def _strip_bytecode(package_dir: Path) -> list[str]:
    """Bytecode caches are build residue, not source; remove them before sealing so the sealed
    bytes are exactly the source tree. Returns the removed paths (relative)."""
    removed: list[str] = []
    for path in sorted(package_dir.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        if path.is_file() and path.suffix == ".pyc":
            path.unlink()
            removed.append(path.relative_to(package_dir).as_posix())
        elif path.is_dir() and path.name == "__pycache__" and not any(path.iterdir()):
            path.rmdir()
            removed.append(path.relative_to(package_dir).as_posix() + "/")
    return removed


def _parse_manifest(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"app.yaml is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("app.yaml must be a mapping")
    if str(data.get("contract_version")) != "0.2":
        raise ValueError("contract_version must be '0.2'")
    for key in ("app_id", "name", "description", "runtime_profile", "sdk_version"):
        if not isinstance(data.get(key), str) or not data[key]:
            raise ValueError(f"missing or invalid {key}")
    for forbidden in ("grants", "secrets", "credentials", "connections", "release"):
        if forbidden in data:
            raise ValueError(f"app.yaml may not carry {forbidden}")
    actions = data.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("actions must be a non-empty list")
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("each action must be a mapping")
        action_id = action.get("id")
        if not isinstance(action_id, str) or not action_id or action_id in seen:
            raise ValueError("action id missing or duplicated")
        seen.add(action_id)
        handler = action.get("handler")
        if not isinstance(handler, str) or ":" not in handler or handler.startswith("."):
            raise ValueError(f"action {action_id}: handler must be module:function")
        for schema_key in ("input_schema", "output_schema"):
            if not isinstance(action.get(schema_key), dict):
                raise ValueError(f"action {action_id}: {schema_key} must be an object")
        if action.get("effect_class", "none") != "none" or action.get(
            "capability_requirements", []
        ):
            raise ValueError(
                f"action {action_id}: F02 pure profile allows no effects or capabilities"
            )
    return data


def _summarize_result(output: Any) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {"status": "malformed"}
    return {
        "status": output.get("status"),
        "failure_category": output.get("failure_category"),
        "harness": output.get("harness"),
        "harness_version": output.get("harness_version"),
        "exit_code": output.get("exit_code"),
        "final_text": str(output.get("final_text", ""))[:300],
    }
