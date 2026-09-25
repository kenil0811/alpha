"""RunCoordinator: durable run envelope, worker dispatch, event persistence, cancellation and
restart reconciliation for the F01 synthetic path.

Every state change goes through ControlStore.transition so the run row and its event commit
together. The coordinator never mutates a terminal run.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_contracts.runs import (
    TERMINAL_RUN_STATES,
    AppOwner,
    ExecutionSnapshot,
    Run,
    RunLimits,
    RunOrigin,
    RunState,
    TaskOwner,
)

from alpha.execution.supervisor import WorkerHandle, WorkerSupervisor, process_alive
from alpha.execution.worker_io import StderrTail, read_worker_messages
from alpha.storage.control_store import ConflictError, ControlStore, new_id, utc_now

log = logging.getLogger("alpha.execution")

_STDERR_TAIL = 2000


def input_digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


@dataclass
class DispatchSpec:
    """How to run one durable Run's worker.

    profile_name   registered worker profile
    python         exact interpreter of a runtime profile (App runs); None = Core's interpreter
    build_job      makes the first stdin line from the run and its input (default: the input)
    on_call        answers capability calls; when set, stdin stays open for replies
    validate_output returns a problem description when a result violates the declared output
    on_finish      always called once the worker is gone (tokens revoked, leases released)
    reason_from_error_code  failed runs carry the worker's error code as terminal reason
    """

    profile_name: str
    python: Path | None = None
    build_job: Callable[[Run, dict[str, Any]], dict[str, Any]] | None = None
    on_call: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None
    validate_output: Callable[[dict[str, Any]], str | None] | None = None
    on_finish: Callable[[str], None] | None = None
    reason_from_error_code: bool = False


class RunCoordinator:
    def __init__(
        self,
        store: ControlStore,
        supervisor: WorkerSupervisor,
        *,
        workspace_id: str,
        default_timeout_seconds: int,
    ) -> None:
        self._store = store
        self._supervisor = supervisor
        self._workspace_id = workspace_id
        self._default_timeout = default_timeout_seconds
        self._instance_id = uuid.uuid4().hex
        self._active: dict[str, WorkerHandle] = {}
        self._specs: dict[str, DispatchSpec] = {}
        self._stdin_locks: dict[str, threading.Lock] = {}
        self._cancel_requested: set[str] = set()
        self._timed_out: set[str] = set()
        self._lock = threading.Lock()
        self._threads: list[threading.Thread] = []

    @property
    def instance_id(self) -> str:
        return self._instance_id

    # ----- submission -------------------------------------------------------------------

    def submit_synthetic(self, payload: dict[str, Any], *, origin: RunOrigin) -> Run:
        """Create a queued run for the synthetic worker profile and dispatch it.

        The synthetic fixture is modelled as a one-off Task attempt whose plan is the
        registered worker profile; no App identity is invented for it."""
        profile = self._supervisor.profile("synthetic")
        task_id = new_id("task")
        owner = TaskOwner(
            task_id=task_id,
            task_revision_id=f"{task_id}.r1",
            attempt_id=new_id("attempt"),
            plan_ref=f"worker-profile:{profile.name}",
        )
        timeout = int(payload.get("timeout_seconds", self._default_timeout))
        snapshot = ExecutionSnapshot(
            worker_profile=profile.name,
            input_digest=input_digest(payload),
            limits=RunLimits(timeout_seconds=timeout),
        )
        return self.submit_run(
            owner=owner,
            origin=origin,
            snapshot=snapshot,
            payload=payload,
            spec=DispatchSpec(profile_name=profile.name),
        )

    def submit_run(
        self,
        *,
        owner: AppOwner | TaskOwner,
        origin: RunOrigin,
        snapshot: ExecutionSnapshot,
        payload: dict[str, Any],
        spec: DispatchSpec,
    ) -> Run:
        """Create a queued durable run and dispatch its worker on a background thread."""
        run = self._store.create_run(
            workspace_id=self._workspace_id,
            owner=owner,
            origin=origin,
            snapshot=snapshot,
            input_payload=payload,
        )
        with self._lock:
            self._specs[run.run_id] = spec
        thread = threading.Thread(target=self._dispatch, args=(run.run_id,), daemon=True)
        with self._lock:
            self._threads.append(thread)
        thread.start()
        return run

    # ----- dispatch ---------------------------------------------------------------------

    def _dispatch(self, run_id: str) -> None:
        with self._lock:
            spec = self._specs.get(run_id) or DispatchSpec(profile_name="synthetic")
        try:
            self._dispatch_with(run_id, spec)
        finally:
            with self._lock:
                self._specs.pop(run_id, None)
                self._stdin_locks.pop(run_id, None)
            if spec.on_finish is not None:
                try:
                    spec.on_finish(run_id)
                except Exception:
                    log.exception("on_finish failed for %s", run_id)

    def _dispatch_with(self, run_id: str, spec: DispatchSpec) -> None:
        try:
            run = self._store.get_run(run_id)
            payload = self._store.get_run_input(run_id)
            job = spec.build_job(run, payload) if spec.build_job is not None else payload
            handle = self._supervisor.launch(spec.profile_name, run_id, python=spec.python)
        except Exception as exc:  # launch failure is an honest failed run
            log.exception("worker launch failed for %s", run_id)
            self._safe_transition(
                run_id,
                expected={RunState.QUEUED},
                new_state=RunState.FAILED,
                event_kind="run.failed",
                payload={"reason": "worker_launch_failed", "error": str(exc)},
                terminal_reason="worker_launch_failed",
            )
            return
        with self._lock:
            self._active[run_id] = handle
        self._store.record_lease(
            run_id=run_id,
            profile=handle.profile.name,
            pid=handle.pid,
            pgid=handle.pgid,
            scratch_dir=handle.scratch_dir,
            core_instance_id=self._instance_id,
        )
        self._safe_transition(
            run_id,
            expected={RunState.QUEUED},
            new_state=RunState.RUNNING,
            event_kind="run.started",
            payload={"worker_pid": handle.pid, "worker_pgid": handle.pgid},
        )
        with self._lock:
            self._stdin_locks[run_id] = threading.Lock()
        try:
            assert handle.process.stdin is not None
            handle.process.stdin.write(json.dumps(job) + "\n")
            handle.process.stdin.flush()
            if spec.on_call is None:
                handle.process.stdin.close()
        except (BrokenPipeError, OSError) as exc:
            self._store.append_event(run_id, "worker.stdin_error", {"error": str(exc)})

        timer = threading.Timer(
            run.snapshot.limits.timeout_seconds, self._on_timeout, args=(run_id,)
        )
        timer.daemon = True
        timer.start()
        collected: dict[str, Any] = {"result": None, "error": None}
        reader = threading.Thread(
            target=self._read_worker_output, args=(run_id, handle, collected, spec), daemon=True
        )
        reader.start()
        stderr = StderrTail(handle, _STDERR_TAIL)
        # Wait on the leader, not on pipe EOF: a descendant that inherits stdout must not be
        # able to keep a finished run alive. Descendants never outlive the leader.
        exit_code = handle.process.wait()
        timer.cancel()
        descendants = self._supervisor.terminate(handle)
        reader.join(timeout=5.0)
        if reader.is_alive():
            self._store.append_event(run_id, "worker.stdout_reader_timeout", {})
        stderr_tail = stderr.text()
        if handle.process.stdin is not None and not handle.process.stdin.closed:
            try:
                handle.process.stdin.close()
            except OSError:
                pass
        result = collected["result"]
        error = collected["error"]
        self._store.append_event(
            run_id, "worker.exited", {"exit_code": exit_code, "descendant_cleanup": descendants}
        )
        with self._lock:
            self._active.pop(run_id, None)
            cancelled = run_id in self._cancel_requested
            self._cancel_requested.discard(run_id)
            timed_out = run_id in self._timed_out
            self._timed_out.discard(run_id)
        self._store.release_lease(run_id)

        if cancelled:
            # The cancel path already transitioned the run; nothing else to record.
            return
        problem = None
        if exit_code == 0 and result is not None and spec.validate_output is not None:
            problem = spec.validate_output(result)
        if exit_code == 0 and result is not None and problem is None:
            self._safe_transition(
                run_id,
                expected={RunState.RUNNING},
                new_state=RunState.SUCCEEDED,
                event_kind="run.succeeded",
                payload={"exit_code": exit_code},
                output=result,
            )
        elif problem is not None:
            self._safe_transition(
                run_id,
                expected={RunState.RUNNING},
                new_state=RunState.FAILED,
                event_kind="run.failed",
                payload={"reason": "output_schema_violation", "problem": problem},
                terminal_reason="output_schema_violation",
            )
        else:
            reason = "worker_error" if error else "worker_exit_nonzero"
            if error and spec.reason_from_error_code and isinstance(error.get("code"), str):
                reason = str(error["code"])[:64]
            if exit_code == 0 and result is None:
                reason = "worker_exit_without_result"
            if exit_code < 0:
                reason = "worker_killed"
            if timed_out:
                reason = "timeout_exceeded"
            self._safe_transition(
                run_id,
                expected={RunState.RUNNING},
                new_state=RunState.FAILED,
                event_kind="run.failed",
                payload={
                    "reason": reason,
                    "exit_code": exit_code,
                    "error": error,
                    "stderr_tail": stderr_tail,
                },
                terminal_reason=reason,
            )

    def _reply(self, run_id: str, handle: WorkerHandle, reply: dict[str, Any]) -> None:
        with self._lock:
            lock = self._stdin_locks.get(run_id)
        stdin = handle.process.stdin
        if lock is None or stdin is None:
            return
        with lock:
            try:
                stdin.write(json.dumps(reply, default=str) + "\n")
                stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                self._store.append_event(run_id, "worker.stdin_error", {"error": str(exc)})

    def _read_worker_output(
        self,
        run_id: str,
        handle: WorkerHandle,
        collected: dict[str, Any],
        spec: DispatchSpec | None = None,
    ) -> None:
        def on_message(message: dict[str, Any]) -> None:
            kind = message.get("kind")
            if kind == "call" and spec is not None and spec.on_call is not None:
                self._reply(run_id, handle, spec.on_call(run_id, message))
            elif kind == "call":
                self._store.append_event(run_id, "worker.unexpected_call", {})
            elif kind == "progress":
                self._store.append_event(run_id, "worker.progress", message)
            elif kind == "result":
                output = message.get("output")
                collected["result"] = output if isinstance(output, dict) else None
                self._store.append_event(run_id, "worker.result", message)
            elif kind == "error":
                collected["error"] = message
                self._store.append_event(run_id, "worker.error", message)
            else:
                self._store.append_event(run_id, "worker.message", message)

        def on_raw(line: str) -> None:
            self._store.append_event(run_id, "worker.stdout", {"line": line})

        read_worker_messages(handle, on_message, on_raw)

    def _on_timeout(self, run_id: str) -> None:
        with self._lock:
            handle = self._active.get(run_id)
            if handle is None:
                return
            self._timed_out.add(run_id)
        # Record the decision before acting on it, then record what the action observed.
        self._store.append_event(
            run_id, "worker.timeout", {"reason": "timeout_exceeded", "worker_pid": handle.pid}
        )
        record = self._supervisor.terminate(handle)
        self._store.append_event(run_id, "worker.timeout_termination", {"termination": record})

    # ----- cancellation -----------------------------------------------------------------

    def cancel(self, run_id: str) -> Run:
        run = self._store.get_run(run_id)
        if run.state in TERMINAL_RUN_STATES:
            raise ConflictError(f"run {run_id} already {run.state.value}")
        with self._lock:
            handle = self._active.get(run_id)
            self._cancel_requested.add(run_id)
        termination: dict[str, object] = {"worker_running": handle is not None}
        if handle is not None:
            termination.update(self._supervisor.terminate(handle))
        return self._store.transition(
            run_id,
            expected_states={RunState.QUEUED, RunState.RUNNING},
            new_state=RunState.CANCELLED,
            event_kind="run.cancelled",
            payload={"termination": termination},
            terminal_reason="cancelled_by_user",
        )

    # ----- lifecycle --------------------------------------------------------------------

    def reconcile_on_startup(self) -> list[dict[str, Any]]:
        """Called before serving requests. Any run left queued/running by a previous Core
        instance is marked interrupted; an orphaned worker process group is terminated. Arbitrary
        worker stacks are not resumed (specification section 6)."""
        report: list[dict[str, Any]] = []
        leases = {lease["run_id"]: lease for lease in self._store.list_leases()}
        for run in self._store.list_runs_in_states({RunState.QUEUED, RunState.RUNNING}):
            lease = leases.get(run.run_id)
            entry: dict[str, Any] = {"run_id": run.run_id, "previous_state": run.state.value}
            if lease is not None:
                alive = process_alive(int(lease["pid"]))
                entry["lease"] = {"pid": lease["pid"], "pgid": lease["pgid"], "alive": alive}
                if alive:
                    entry["termination"] = self._supervisor.terminate_orphan(int(lease["pgid"]))
                self._store.release_lease(run.run_id)
                reason = "core_restarted_worker_orphaned" if alive else "core_restarted_worker_lost"
            else:
                reason = "core_restarted_no_lease"
            entry["reason"] = reason
            self._safe_transition(
                run.run_id,
                expected={RunState.QUEUED, RunState.RUNNING},
                new_state=RunState.INTERRUPTED,
                event_kind="run.interrupted",
                payload={"reason": reason, "reconciled_by": self._instance_id, **entry},
                terminal_reason=reason,
            )
            report.append(entry)
        return report

    def shutdown(self, reason: str = "runtime_quit") -> list[str]:
        """Explicit quit: terminate every active worker tree and mark its run interrupted."""
        with self._lock:
            handles = dict(self._active)
        interrupted: list[str] = []
        for run_id, handle in handles.items():
            with self._lock:
                self._cancel_requested.add(run_id)
            record = self._supervisor.terminate(handle)
            self._store.release_lease(run_id)
            self._safe_transition(
                run_id,
                expected={RunState.QUEUED, RunState.RUNNING},
                new_state=RunState.INTERRUPTED,
                event_kind="run.interrupted",
                payload={"reason": reason, "termination": record},
                terminal_reason=reason,
            )
            interrupted.append(run_id)
        return interrupted

    def active_run_ids(self) -> list[str]:
        with self._lock:
            return list(self._active)

    def supervisor_profiles(self) -> list[str]:
        return sorted(self._supervisor.profiles())

    def _safe_transition(
        self,
        run_id: str,
        *,
        expected: set[RunState],
        new_state: RunState,
        event_kind: str,
        payload: dict[str, Any],
        output: dict[str, Any] | None = None,
        terminal_reason: str | None = None,
    ) -> None:
        try:
            self._store.transition(
                run_id,
                expected_states=expected,
                new_state=new_state,
                event_kind=event_kind,
                payload=payload,
                output=output,
                terminal_reason=terminal_reason,
            )
        except ConflictError as exc:
            # e.g. cancelled while the worker was exiting; keep the terminal state, keep evidence.
            self._store.append_event(
                run_id,
                "run.transition_skipped",
                {"attempted": new_state.value, "reason": str(exc), "at": utc_now().isoformat()},
            )
