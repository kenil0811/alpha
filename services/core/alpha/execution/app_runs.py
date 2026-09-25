"""App action invocation (Current Release Specification §3 and §6).

Invocation validates the input against the action's declared schema in Core, creates a durable
Run whose owner is the App's current release and whose snapshot pins the exact Version, package
digest, runtime profile and dependency manifest, then launches the App worker with that
profile's interpreter. The worker gets a per-run workload token on stdin; the result is checked
against the declared output schema before the run can succeed.

Handler validation at install time uses the same worker in `validate` mode: a disposable process
imports each handler and checks its signature. Candidate modules are never imported into Core.
"""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any

from alpha_contracts.apps import AppSource, Invocable
from alpha_contracts.broker import WORKER_PROTOCOL_VERSION
from alpha_contracts.runs import AppOwner, ExecutionSnapshot, Run, RunLimits, RunOrigin
from jsonschema import Draft202012Validator

from alpha.capabilities.errors import OperationFailed, forbidden, invalid
from alpha.data.apps import AppRegistry
from alpha.execution.broker import CapabilityBroker, RunGrant
from alpha.execution.coordinator import DispatchSpec, RunCoordinator, input_digest
from alpha.execution.profiles import InstalledProfile, ProfileInventory
from alpha.execution.supervisor import WorkerSupervisor

_ORIGIN_TO_INVOCABLE = {
    RunOrigin.USER: Invocable.MANUAL,
    RunOrigin.UI: Invocable.UI,
    RunOrigin.ASSISTANT: Invocable.ASSISTANT,
    RunOrigin.TRIGGER: Invocable.TRIGGER,
}


def schema_problems(schema: dict[str, Any], value: Any, limit: int = 5) -> list[str]:
    validator = Draft202012Validator(schema)
    problems = []
    for error in sorted(validator.iter_errors(value), key=lambda e: list(e.path))[:limit]:
        where = ".".join(str(p) for p in error.path) or "(top level)"
        problems.append(f"{where}: {error.message}"[:300])
    return problems


class AppRunService:
    def __init__(
        self,
        coordinator: RunCoordinator,
        supervisor: WorkerSupervisor,
        registry: AppRegistry,
        inventory: ProfileInventory,
        broker: CapabilityBroker,
        *,
        timezone: str,
        validation_timeout_seconds: int = 60,
    ) -> None:
        self._coordinator = coordinator
        self._supervisor = supervisor
        self._registry = registry
        self._inventory = inventory
        self._broker = broker
        self._timezone = timezone
        self._validation_timeout = validation_timeout_seconds

    @property
    def timezone(self) -> str:
        return self._timezone

    def invoke(
        self,
        app_id: str,
        action_id: str,
        payload: dict[str, Any],
        *,
        origin: RunOrigin,
    ) -> Run:
        version = self._registry.current(app_id)
        action = version.source.action(action_id)
        if action is None:
            raise OperationFailed(
                "not_found",
                f"{app_id} has no action {action_id!r}",
                {"actions": [a.id for a in version.source.actions]},
            )
        allowed = _ORIGIN_TO_INVOCABLE.get(origin)
        if allowed is None or allowed not in action.invocable_from:
            raise forbidden(
                f"action {action_id} cannot be invoked from {origin.value}",
                invocable_from=[i.value for i in action.invocable_from],
            )
        problems = schema_problems(action.input_schema, payload)
        if problems:
            raise invalid(f"the input for {action_id} is not valid", problems=problems)
        profile = self._inventory.ready(version.runtime_profile_id)
        owner = AppOwner(app_id=app_id, release_id=version.release_id, action_id=action_id)
        snapshot = ExecutionSnapshot(
            worker_profile="app",
            input_digest=input_digest(payload),
            limits=RunLimits(timeout_seconds=action.timeout_seconds),
            version_id=version.version_id,
            package_sha256=version.package_sha256,
            runtime_profile_id=profile.profile_id,
            dependency_manifest_sha256=version.dependency_manifest_sha256,
            capabilities=sorted(version.source.capabilities),
            timezone=self._timezone,
        )

        def build_job(run: Run, run_input: dict[str, Any]) -> dict[str, Any]:
            token = self._broker.issue(
                RunGrant(
                    run_id=run.run_id,
                    app_id=app_id,
                    action_id=action_id,
                    version_id=version.version_id,
                    package_sha256=version.package_sha256,
                    capabilities=frozenset(version.source.capabilities),
                    origin=origin,
                    timezone=self._timezone,
                )
            )
            return {
                "protocol": WORKER_PROTOCOL_VERSION,
                "mode": "invoke",
                "run_id": run.run_id,
                "token": token,
                "version_dir": str(version.location),
                "app_id": app_id,
                "action_id": action_id,
                "handler": action.handler,
                "input": run_input,
                "origin": origin.value,
                "timezone": self._timezone,
            }

        def validate_output(output: dict[str, Any]) -> str | None:
            found = schema_problems(action.output_schema, output)
            return "; ".join(found) if found else None

        spec = DispatchSpec(
            profile_name="app",
            python=profile.python,
            build_job=build_job,
            on_call=self._broker.handle,
            validate_output=validate_output,
            on_finish=self._broker.revoke,
            reason_from_error_code=True,
        )
        return self._coordinator.submit_run(
            owner=owner, origin=origin, snapshot=snapshot, payload=payload, spec=spec
        )

    def validate_handlers(
        self, version_dir: Path, source: AppSource, profile: InstalledProfile
    ) -> list[dict[str, Any]]:
        """Resolve every declared handler in a disposable worker on the exact profile."""
        job = {
            "protocol": WORKER_PROTOCOL_VERSION,
            "mode": "validate",
            "version_dir": str(version_dir),
            "actions": [
                {"id": a.id, "handler": a.handler, "input_schema": a.input_schema}
                for a in source.actions
            ],
        }
        handle = self._supervisor.launch(
            "app", f"validate-{source.app_id}-{version_dir.name}-{_suffix()}", python=profile.python
        )
        try:
            try:
                stdout, _stderr = handle.process.communicate(
                    input=json.dumps(job) + "\n", timeout=self._validation_timeout
                )
            except subprocess.TimeoutExpired:
                raise invalid("resolving the package's handlers timed out") from None
        finally:
            # Also removes anything the imported modules may have spawned.
            self._supervisor.terminate(handle)
        for line in stdout.splitlines():
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("kind") == "result":
                return list(message.get("output", {}).get("actions", []))
            if message.get("kind") == "error":
                raise invalid(f"the package could not be loaded: {message.get('message')}")
        raise invalid("the validation worker produced no report")


def _suffix() -> str:
    return uuid.uuid4().hex[:8]
