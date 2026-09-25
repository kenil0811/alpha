"""Rendered UI checks (F07.C02): Core's side of workers/validator.

The Node validator drives the candidate's sealed static UI in a pinned headless browser. Every
bridge request the screen makes arrives here over the worker's pipes and is answered from the
candidate's preview, under the same grant the shell would give it: only declared views, only
declared UI actions, only operations this session started. Control requests seed sample data
through the App's own actions and read the preview store directly to judge what was saved.
"""

from __future__ import annotations

import json
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from alpha_contracts.runs import RunOrigin
from alpha_contracts.verification import CheckResult, CheckStatus, UiPlan

from alpha.builds.plan import run_invoke, run_records
from alpha.builds.preview import PreviewPlatform
from alpha.builds.toolchain import UiToolchain
from alpha.capabilities.errors import OperationFailed
from alpha.execution.profiles import ProfileInventory
from alpha.execution.supervisor import WorkerSupervisor
from alpha.execution.worker_io import StderrTail

PLAYWRIGHT_VERSION = "1.62.0"
_BRIDGE_CODES = {
    "invalid_input": "invalid_request",
    "forbidden": "forbidden",
    "not_found": "not_found",
    "unavailable": "unsupported",
}


def _bridge_error(exc: OperationFailed) -> dict[str, Any]:
    return {"code": _BRIDGE_CODES.get(exc.code, "internal"), "message": exc.message[:500]}


class UiRenderCheck:
    def __init__(
        self,
        supervisor: WorkerSupervisor,
        inventory: ProfileInventory,
        toolchain: UiToolchain,
        timeout_seconds: float = 240.0,
    ) -> None:
        self._supervisor = supervisor
        self._inventory = inventory
        self._toolchain = toolchain
        self._timeout = timeout_seconds

    def run(
        self,
        preview: PreviewPlatform,
        plan: UiPlan | None,
        evidence_dir: Path,
        evidence_ref: str,
        stop: threading.Event | None = None,
    ) -> tuple[list[CheckResult], dict[str, str]]:
        app = preview.app
        ui = app.source.ui
        ui_build = app.dependency_manifest.ui_build
        problems = self._toolchain.render_problems()
        if ui is None or ui_build is None or problems:
            reason = "; ".join(problems) or "the Version has no built UI"
            return [
                CheckResult(
                    id="ui.render",
                    stage="ui",
                    status=CheckStatus.SKIPPED,
                    summary=f"the screen could not be rendered: {reason}",
                )
            ], {}
        ui_profile = self._inventory.ready(ui_build.profile_id)
        job = {
            "app_id": app.app_id,
            "dist_dir": str(app.location / "dist" / "ui"),
            "bridge_dir": str(
                ui_profile.location / "node_modules" / "@alpha" / "ui-bridge" / "dist"
            ),
            "browser": str(self._toolchain.browser),
            "playwright_version": PLAYWRIGHT_VERSION,
            "timezone": preview.timezone,
            "grant": {"actions": list(ui.actions), "read_views": [v.id for v in ui.views]},
            "evidence_dir": str(evidence_dir),
            "evidence_ref": evidence_ref,
            "plan": None
            if plan is None
            else {
                "primary": [s.model_dump(exclude_none=True) for s in plan.primary],
                "shows": plan.shows,
                "seed": [s.model_dump() for s in plan.seed],
                "seed_shows": plan.seed_shows,
                "saved": plan.saved is not None,
                "saved_collection": plan.saved.collection if plan.saved else None,
            },
        }
        session = _Session(preview, plan, set(ui.actions), {v.id for v in ui.views})
        handle = self._supervisor.launch(
            "ui_validator",
            f"uicheck-{uuid.uuid4().hex[:12]}",
            node=(self._toolchain.node, self._toolchain.resources.ui_validator),
        )
        stderr = StderrTail(handle, 4000)
        timed_out = threading.Event()

        def on_timeout() -> None:
            timed_out.set()
            self._supervisor.terminate(handle)

        timer = threading.Timer(self._timeout, on_timeout)
        timer.daemon = True
        timer.start()
        finished = threading.Event()

        def watch_stop() -> None:
            # A cancelled build or a quitting Core ends the browser session promptly.
            while stop is not None and not finished.is_set():
                if stop.wait(0.5):
                    self._supervisor.terminate(handle)
                    return

        if stop is not None:
            threading.Thread(target=watch_stop, daemon=True).start()
        checks: list[CheckResult] = []
        environment: dict[str, str] = {}
        failure: str | None = None
        try:
            assert handle.process.stdin is not None
            handle.process.stdin.write(json.dumps(job) + "\n")
            handle.process.stdin.flush()
            for raw in handle.stdout:
                line = raw.strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = message.get("kind")
                if kind in ("bridge", "control"):
                    reply = session.answer(message)
                    try:
                        handle.process.stdin.write(json.dumps(reply, default=str) + "\n")
                        handle.process.stdin.flush()
                    except (BrokenPipeError, OSError):
                        break
                elif kind == "check":
                    fields = {k: v for k, v in message.items() if k != "kind"}
                    checks.append(CheckResult.model_validate(fields))
                elif kind == "result":
                    environment = {
                        k: str(v)
                        for k, v in (message.get("output") or {}).get("environment", {}).items()
                    }
                elif kind == "error":
                    failure = str(message.get("message"))[:1500]
            try:
                handle.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                pass
        finally:
            finished.set()
            timer.cancel()
            self._supervisor.terminate(handle)
        checks = session.checks + checks
        if timed_out.is_set() or failure or not environment:
            reason = (
                f"the render check ran over {self._timeout:.0f}s"
                if timed_out.is_set()
                else failure or f"the render check stopped: {stderr.text()[-800:]}"
            )
            checks.append(
                CheckResult(
                    id="ui.render.complete", stage="ui", status=CheckStatus.FAILED, summary=reason
                )
            )
        return checks, environment


class _Session:
    """Answers one validator session's requests under the screen's declared grant."""

    def __init__(
        self, preview: PreviewPlatform, plan: UiPlan | None, actions: set[str], views: set[str]
    ) -> None:
        self.preview = preview
        self.plan = plan
        self.actions = actions
        self.views = views
        self.operations: set[str] = set()
        self.checks: list[CheckResult] = []
        self._outputs: dict[str, Any] = {}

    def answer(self, message: dict[str, Any]) -> dict[str, Any]:
        reply_id = message.get("id")
        try:
            if message["kind"] == "bridge":
                result = self._bridge(str(message.get("type")), dict(message.get("payload") or {}))
            else:
                result = self._control(str(message.get("op")), message)
        except OperationFailed as exc:
            return {"id": reply_id, "ok": False, "error": _bridge_error(exc)}
        except Exception as exc:  # the validator must see a reply, never a hang
            return {
                "id": reply_id,
                "ok": False,
                "error": {"code": "internal", "message": str(exc)[:300]},
            }
        return {"id": reply_id, "ok": True, "result": result}

    def _bridge(self, kind: str, payload: dict[str, Any]) -> Any:
        app = self.preview.app
        if kind == "records.query":
            view = str(payload.pop("view", ""))
            if view not in self.views:
                return _deny(f"view {view} is not granted to this screen")
            return self.preview.query_view(view, payload)
        if kind == "action.invoke":
            action = str(payload.get("action_id", ""))
            if action not in self.actions:
                return _deny(f"action {action} is not granted to this screen")
            run = self.preview.runs.invoke(
                app.app_id, action, dict(payload.get("input") or {}), origin=RunOrigin.UI
            )
            self.operations.add(run.run_id)
            return {"operation_id": run.run_id}
        if kind == "operation.observe":
            operation = str(payload.get("operation_id", ""))
            if operation not in self.operations:
                return _deny("the operation was not started by this screen")
            return self.preview.outcome(operation)
        return _deny(f"{kind} is not available to generated screens during checks")

    def _control(self, op: str, message: dict[str, Any]) -> Any:
        if op == "seed":
            results = []
            for step in self.plan.seed if self.plan else []:
                result = run_invoke(self.preview, step, self._outputs, f"ui.seed.{step.id}")
                result = result.model_copy(update={"stage": "ui"})
                results.append(result)
                self.checks.append(result)
            failed = [r for r in results if r.status is not CheckStatus.PASSED]
            return {
                "ok": not failed,
                "summary": failed[0].summary if failed else f"{len(results)} sample run(s)",
            }
        if op == "saved":
            if self.plan is None or self.plan.saved is None:
                return {"status": "skipped", "summary": "the plan names nothing to save"}
            result = run_records(self.preview, self.plan.saved, self._outputs, "ui.primary.saved")
            return {
                "status": result.status.value,
                "summary": result.summary,
                "detail": result.detail,
            }
        if op == "count":
            return {"count": self.preview.count(str(message.get("collection", "")))}
        raise OperationFailed("invalid_input", f"unknown control request {op!r}")


def _deny(message: str) -> Any:
    raise OperationFailed("forbidden", message)
