"""One builder attempt: launch the builder worker, stream its normalized events, enforce the
attempt deadline outside the model, and report what the harness claimed.

A harness claim is only a claim. `candidate` means "verify me", never "ready".
"""

from __future__ import annotations

import json
import os
import pwd
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from alpha_contracts.builds import BuildResultStatus, BuildUsage, FailureCategory

from alpha.execution.supervisor import WorkerHandle, WorkerSupervisor
from alpha.execution.worker_io import StderrTail, read_worker_messages

EventSink = Callable[[str, dict[str, Any]], None]


@dataclass
class BuilderOutcome:
    """status: candidate | failed | cancelled | timed_out | no_result | launch_failed"""

    status: str
    usage: BuildUsage | None = None
    category: FailureCategory | None = None
    harness_exit: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] | None = None
    error: Any = None


class BuilderProcess:
    def __init__(
        self,
        supervisor: WorkerSupervisor,
        *,
        builder_path: str,
        builder_home: str | None,
    ) -> None:
        self._supervisor = supervisor
        self._path = builder_path
        self._home = builder_home

    def run(
        self,
        *,
        attempt_id: str,
        job: dict[str, Any],
        deadline_seconds: float,
        emit: EventSink,
        on_launch: Callable[[WorkerHandle], bool],
        on_exit: Callable[[], bool],
    ) -> BuilderOutcome:
        """`on_launch` registers the handle and returns True when the build was cancelled in the
        meantime (the process is then stopped at once). `on_exit` unregisters it and returns
        whether the build was cancelled while it ran."""
        try:
            # The builder runs the founder's own CLI login (decision 2026-09-25): it needs the
            # account name and, when configured, the real home. Derived from the process owner,
            # never from ambient environment.
            owner = pwd.getpwuid(os.getuid()).pw_name
            env = {"PATH": self._path, "USER": owner, "LOGNAME": owner}
            if self._home:
                env["HOME"] = self._home
            handle = self._supervisor.launch("builder", attempt_id, extra_env=env)
        except Exception as exc:
            return BuilderOutcome(
                "launch_failed", category=FailureCategory.HARNESS_UNAVAILABLE, error=str(exc)
            )
        if on_launch(handle):
            self._supervisor.terminate(handle)
        try:
            assert handle.process.stdin is not None
            handle.process.stdin.write(json.dumps(job) + "\n")
            handle.process.stdin.close()
        except (BrokenPipeError, OSError) as exc:
            emit("builder.stdin_error", {"error": str(exc)})

        timed_out = threading.Event()

        def on_deadline() -> None:
            timed_out.set()
            emit("builder.timeout", {"reason": "attempt_deadline_exceeded"})
            self._supervisor.terminate(handle)

        timer = threading.Timer(max(deadline_seconds, 1.0), on_deadline)
        timer.daemon = True
        timer.start()
        collected: dict[str, Any] = {"result": None, "error": None}

        def on_message(message: dict[str, Any]) -> None:
            kind = message.get("kind")
            if kind == "progress":
                stage = message.get("stage")
                if stage == "harness_event":
                    emit(f"harness.{message.get('event', 'event')}", message.get("payload") or {})
                else:
                    emit(
                        f"builder.{stage}",
                        {k: v for k, v in message.items() if k not in ("kind", "stage")},
                    )
            elif kind == "result":
                collected["result"] = message.get("output")
                emit("builder.result", {"summary": _summarize(message.get("output"))})
            elif kind == "error":
                collected["error"] = message
                emit("builder.error", message)

        reader = threading.Thread(
            target=read_worker_messages,
            args=(handle, on_message, lambda line: emit("builder.stdout", {"line": line})),
            daemon=True,
        )
        reader.start()
        stderr = StderrTail(handle, 2000)
        exit_code = handle.process.wait()
        timer.cancel()
        descendants = self._supervisor.terminate(handle)
        reader.join(timeout=5.0)
        harness_exit = {
            "exit_code": exit_code,
            "descendant_cleanup": descendants,
            "stderr_tail": stderr.text(),
        }
        emit("builder.exited", harness_exit)
        cancelled = on_exit()

        output = collected["result"] if isinstance(collected["result"], dict) else None
        usage = None
        if output and isinstance(output.get("usage"), dict):
            try:
                usage = BuildUsage.model_validate(output["usage"])
            except Exception:
                usage = None
        if cancelled:
            return BuilderOutcome(
                "cancelled", usage, FailureCategory.CANCELLED, harness_exit, output
            )
        if timed_out.is_set():
            return BuilderOutcome(
                "timed_out", usage, FailureCategory.HARNESS_TIMEOUT, harness_exit, output
            )
        if output is None:
            category = (
                FailureCategory.HARNESS_ERROR
                if collected["error"]
                else FailureCategory.HARNESS_UNAVAILABLE
            )
            return BuilderOutcome(
                "no_result", usage, category, harness_exit, None, collected["error"]
            )
        status = str(output.get("status"))
        if status != BuildResultStatus.CANDIDATE.value:
            category = FailureCategory(
                output.get("failure_category") or FailureCategory.HARNESS_ERROR.value
            )
            return BuilderOutcome("failed", usage, category, harness_exit, output)
        return BuilderOutcome("candidate", usage, None, harness_exit, output)


def _summarize(output: Any) -> dict[str, Any]:
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
