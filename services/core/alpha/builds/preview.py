"""An isolated preview of one candidate Version (Implementation Blueprint §6).

Checks exercise the candidate through the real platform path: the same App worker on the same
installed runtime profile, the real capability broker with per-run tokens, the real record,
artifact and model services and the real run coordinator. Everything mutable lives under the
preview's own directory, including a separate control store, so preview runs, records and tokens
never appear among the person's Apps or runs and a preview cannot be mistaken for an activated
release. Only the worker supervisor, the profile inventory and the model gateway are shared.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_contracts.apps import Invocable
from alpha_contracts.broker import ModelEstimate, StructuredModelCall
from alpha_contracts.records import DeleteRecord, Filter, Record, RecordMutation, RecordQuery
from alpha_contracts.runs import TERMINAL_RUN_STATES, Run, RunOrigin, RunState

from alpha.artifacts.service import ArtifactService
from alpha.capabilities.errors import OperationFailed, unavailable
from alpha.data.packages import SealedPackage
from alpha.data.store import RecordService, WriteContext
from alpha.data.views import ViewQueryRequest, resolve_view, run_view
from alpha.execution.app_runs import AppRunService
from alpha.execution.broker import CapabilityBroker
from alpha.execution.coordinator import RunCoordinator
from alpha.execution.profiles import ProfileInventory
from alpha.execution.supervisor import WorkerSupervisor
from alpha.models.runtime import AppModelService
from alpha.solutions.registry import AppRegistry, AppVersion, HandlerValidator
from alpha.storage.control_store import ControlStore

# Origins tried, in order, when a check needs to run an action: the first one the action allows.
_ORIGIN_PREFERENCE = (
    (Invocable.MANUAL, RunOrigin.USER),
    (Invocable.UI, RunOrigin.UI),
    (Invocable.ASSISTANT, RunOrigin.ASSISTANT),
    (Invocable.TRIGGER, RunOrigin.TRIGGER),
)


class FaultableModels:
    """The preview's model service. A check can make it fail on purpose, exactly as a real
    failure reaches an App: unavailable, a timeout, or an answer outside the requested bounds."""

    def __init__(self, inner: AppModelService) -> None:
        self._inner = inner
        self.fault = "normal"

    def __getattr__(self, name: str) -> Any:  # everything else is the real service
        return getattr(self._inner, name)

    def call(self, run_id: str, owner_ref: str, request: StructuredModelCall) -> ModelEstimate:
        if self.fault == "unavailable":
            raise unavailable(
                "the model call failed: the model service is unavailable",
                reason="checked_unavailable",
            )
        if self.fault == "timeout":
            raise OperationFailed(
                "timed_out",
                "the model call failed: it took too long",
                {"reason": "checked_timeout"},
            )
        if self.fault == "malformed":
            raise unavailable(
                "the model returned values outside the requested bounds; nothing was stored",
                reason="model_output_out_of_bounds",
            )
        return self._inner.call(run_id, owner_ref, request)


@dataclass(frozen=True)
class PreviewDeps:
    supervisor: WorkerSupervisor
    inventory: ProfileInventory
    handler_validator: HandlerValidator
    models: Callable[[ControlStore], AppModelService]
    timezone: str


class PreviewPlatform:
    def __init__(self, root: Path, deps: PreviewDeps) -> None:
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.store = ControlStore(root / "control.sqlite")
        self.records = RecordService(root / "apps")
        artifacts = ArtifactService(self.store, root / "artifacts")

        def on_event(run_id: str, kind: str, payload: dict[str, Any]) -> None:
            self.store.append_event(run_id, kind, payload)

        self.models = FaultableModels(deps.models(self.store))
        self.broker = CapabilityBroker(
            self.store,
            self.records,
            artifacts,
            self.models,  # type: ignore[arg-type]  # same interface as AppModelService
            on_event=on_event,
        )
        self.coordinator = RunCoordinator(
            self.store, deps.supervisor, workspace_id="preview", default_timeout_seconds=60
        )
        self.registry = AppRegistry(
            self.store,
            deps.inventory,
            self.records,
            root / "versions",
            validator=deps.handler_validator,
        )
        self.runs = AppRunService(
            self.coordinator,
            deps.supervisor,
            self.registry,
            deps.inventory,
            self.broker,
            timezone=deps.timezone,
        )
        self.timezone = deps.timezone
        self._app: AppVersion | None = None

    @property
    def app(self) -> AppVersion:
        if self._app is None:
            raise RuntimeError("no candidate is installed in this preview")
        return self._app

    def install(self, sealed: SealedPackage, handler_report: dict[str, Any]) -> AppVersion:
        """Register the sealed candidate in place (its directory stays inside the build)."""
        self._app = self.registry.register(sealed, handler_report)
        return self._app

    def origin_for(self, action_id: str) -> RunOrigin:
        action = self.app.source.action(action_id)
        if action is None:
            return RunOrigin.USER
        for invocable, origin in _ORIGIN_PREFERENCE:
            if invocable in action.invocable_from:
                return origin
        return RunOrigin.USER

    def invoke_and_wait(
        self,
        action_id: str,
        payload: dict[str, Any],
        *,
        origin: RunOrigin | None = None,
        timeout_seconds: float = 120.0,
    ) -> Run:
        run = self.runs.invoke(
            self.app.app_id, action_id, payload, origin=origin or self.origin_for(action_id)
        )
        return self.wait(run.run_id, timeout_seconds)

    def wait(self, run_id: str, timeout_seconds: float = 120.0) -> Run:
        deadline = time.monotonic() + timeout_seconds
        delay = 0.02
        while True:
            run = self.store.get_run(run_id)
            if run.state in TERMINAL_RUN_STATES or time.monotonic() > deadline:
                return run
            time.sleep(delay)
            delay = min(0.25, delay * 1.5)

    def outcome(self, run_id: str) -> dict[str, Any]:
        """The same outcome shape the shell gives generated UI for operation.observe."""
        run = self.store.get_run(run_id)
        error = None
        if run.state is not RunState.SUCCEEDED and run.state in TERMINAL_RUN_STATES:
            events = self.store.get_events(run_id)
            worker_error = next((e for e in reversed(events) if e.kind == "worker.error"), None)
            failed = next((e for e in reversed(events) if e.kind == "run.failed"), None)
            payload = worker_error.payload if worker_error else {}
            failure = failed.payload if failed else {}
            message = (
                payload.get("message")
                or (
                    f"The result did not match what the action promises: {failure['problem']}"
                    if failure.get("problem")
                    else None
                )
                or run.terminal_reason
                or f"The action {run.state.value}."
            )
            code = payload.get("operation_code") or run.terminal_reason or run.state.value
            error = {"code": str(code), "message": str(message)}
        return {
            "operation_id": run.run_id,
            "state": run.state.value,
            "output": run.output,
            "error": error,
        }

    def failure_detail(self, run: Run) -> dict[str, Any]:
        """What went wrong in a failed run, for reports and repair feedback."""
        events = self.store.get_events(run.run_id)
        detail: dict[str, Any] = {"state": run.state.value, "reason": run.terminal_reason}
        for event in events:
            if event.kind == "worker.error":
                detail["error"] = {
                    k: event.payload.get(k)
                    for k in ("code", "operation_code", "message", "traceback")
                    if event.payload.get(k)
                }
            elif event.kind == "run.failed":
                for key in ("problem", "stderr_tail"):
                    if event.payload.get(key):
                        detail[key] = str(event.payload[key])[-1500:]
        return detail

    def query_view(self, view_id: str, body: dict[str, Any]) -> dict[str, Any]:
        view = resolve_view(self.app.source, view_id)
        request = ViewQueryRequest.model_validate(body)
        result = run_view(self.records.store(self.app.app_id), view, request, self.timezone)
        return result.model_dump(mode="json", by_alias=True)

    def records_in(self, collection: str, where: Filter | None = None) -> list[Record]:
        store = self.records.store(self.app.app_id)
        found: list[Record] = []
        cursor: str | None = None
        for _ in range(20):
            page = store.query(
                RecordQuery(collection=collection, where=where, limit=1000, cursor=cursor)
            )
            found += page.records
            cursor = page.next_cursor
            if cursor is None:
                break
        return found

    def clear_records(self) -> None:
        """Empty every collection of the candidate's preview data (never a person's data)."""
        deletes: list[RecordMutation] = [
            DeleteRecord(collection=c.name, id=r.id, expected_revision=r.revision)
            for c in self.app.source.collections
            for r in self.records_in(c.name)
        ]
        if deletes:
            self.records.store(self.app.app_id).apply(
                deletes, WriteContext(run_id=None, allow_correction=False, resolve_estimate=None)
            )

    def count(self, collection: str) -> int:
        try:
            return len(self.records_in(collection))
        except OperationFailed:
            return -1

    def close(self) -> None:
        self.coordinator.shutdown("preview_closed")
        self.records.close()
