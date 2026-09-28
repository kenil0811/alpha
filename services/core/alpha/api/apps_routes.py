"""Shell-facing routes for installed Apps, their records and artifacts, and runtime profiles.

These are trusted-shell commands behind the session token (the person's own UI). Generated App
code never reaches them: App workers use the capability broker over their pipes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_contracts.artifacts import Artifact, ArtifactOwner
from alpha_contracts.records import (
    AggregateQuery,
    AggregateResult,
    RecordMutation,
    RecordPage,
    RecordQuery,
)
from alpha_contracts.runs import Run, RunOrigin
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from alpha.artifacts.service import ArtifactService
from alpha.capabilities.browser import BrowserService
from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.context.connections import ConnectionService
from alpha.data.store import RecordService, WriteContext
from alpha.data.views import ViewQueryRequest, resolve_view, run_view
from alpha.execution.app_runs import AppRunService, HandlerBinder
from alpha.execution.broker import CapabilityBroker
from alpha.execution.profiles import ProfileInventory
from alpha.execution.scheduler import Scheduler
from alpha.models.disclosure import app_data_notice
from alpha.models.runtime import AppModelService
from alpha.solutions.registry import ANY_RELEASE, AppRegistry

_FIXTURE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass
class AppPlatform:
    inventory: ProfileInventory
    records: RecordService
    artifacts: ArtifactService
    models: AppModelService
    broker: CapabilityBroker
    registry: AppRegistry
    runs: AppRunService
    binder: HandlerBinder
    fixture_apps_dir: Path | None = None
    scheduler: Scheduler | None = None
    browser: BrowserService | None = None
    connections: ConnectionService | None = None

    def close(self) -> None:
        if self.scheduler is not None:
            self.scheduler.stop()
        self.records.close()


class ReleaseGuard(BaseModel):
    """Only act if the module's current release is still this one (from the page that offered
    the action); empty means act on whatever is current."""

    model_config = ConfigDict(extra="forbid")
    expected_release_id: str | None = None


class RecordMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mutation: RecordMutation


class ScheduleToggle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class ActionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any] = Field(default_factory=dict)
    origin: RunOrigin = RunOrigin.USER


def _app_notice(platform: AppPlatform, capabilities: list[str]) -> str:
    if "models" not in capabilities:
        return "Its records stay on this Mac."
    route = platform.models.route()
    if route is None:
        return (
            "Its records stay on this Mac. Its estimates are not available on this Mac right now."
        )
    return app_data_notice(route)


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(app: FastAPI, platform: AppPlatform) -> None:
    @app.get("/api/runtime-profiles")
    def runtime_profiles() -> dict[str, Any]:
        return {"profiles": platform.inventory.list_profiles()}

    @app.get("/api/apps")
    def list_apps() -> dict[str, Any]:
        return {"apps": [a for a in platform.registry.list_apps() if a.get("state") == "active"]}

    @app.post("/api/apps/{app_id}/revert")
    def revert_app(app_id: str, body: ReleaseGuard | None = None) -> dict[str, Any]:
        """Go back to the previous version. Records are kept."""
        expected = body.expected_release_id if body and body.expected_release_id else ANY_RELEASE
        try:
            version = platform.registry.revert(app_id, expected)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {
            "app_id": version.app_id,
            "version_id": version.version_id,
            "release_id": version.release_id,
        }

    @app.post("/api/apps/{app_id}/remove")
    def remove_app(app_id: str, body: ReleaseGuard | None = None) -> dict[str, Any]:
        """Take the module out of use. Nothing is deleted from disk."""
        expected = body.expected_release_id if body and body.expected_release_id else ANY_RELEASE
        try:
            platform.registry.retire(app_id, expected)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {"app_id": app_id, "state": "removed"}

    @app.get("/api/apps/{app_id}")
    def get_app(app_id: str) -> dict[str, Any]:
        try:
            version = platform.registry.current(app_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        source = version.source
        return {
            "app_id": version.app_id,
            "name": source.name,
            "description": source.description,
            "version_id": version.version_id,
            "release_id": version.release_id,
            "package_sha256": version.package_sha256,
            "dependency_manifest_sha256": version.dependency_manifest_sha256,
            "runtime_profile_id": version.runtime_profile_id,
            "capabilities": source.capabilities,
            "primary_action": source.primary_action,
            "collections": [c.model_dump(mode="json") for c in source.collections],
            "actions": [
                {
                    "id": a.id,
                    "title": a.title,
                    "description": a.description,
                    "input_schema": a.input_schema,
                    "output_schema": a.output_schema,
                    "invocable_from": [i.value for i in a.invocable_from],
                    "effect_class": a.effect_class.value,
                }
                for a in source.actions
            ],
            "record_counts": platform.records.store(app_id).counts(),
            # Where this App's data goes, from the configured route (F11).
            "data_notice": _app_notice(platform, source.capabilities),
            "ui": source.ui.model_dump(mode="json", by_alias=True) if source.ui else None,
            "views": [v.model_dump(mode="json", by_alias=True) for v in source.views],
            "screen": source.screen.model_dump(mode="json", by_alias=True)
            if source.screen
            else None,
            "has_screen": source.has_screen(),
            "summary": [b.model_dump(mode="json", by_alias=True) for b in source.summary],
            "uses": [u.model_dump(mode="json") for u in source.uses],
            "can_revert": platform.registry.previous_release(app_id) is not None,
        }

    @app.get("/api/apps/{app_id}/schedules")
    def list_schedules(app_id: str) -> dict[str, Any]:
        try:
            version = platform.registry.current(app_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        if platform.scheduler is None:
            return {"schedules": [], "available": False}
        return {
            "schedules": platform.scheduler.status(app_id, version.source.schedules),
            "available": True,
        }

    @app.post("/api/apps/{app_id}/schedules/{schedule_id}")
    def set_schedule(app_id: str, schedule_id: str, body: ScheduleToggle) -> dict[str, Any]:
        try:
            version = platform.registry.current(app_id)
            if platform.scheduler is None:
                raise OperationFailed("unavailable", "schedules are not running on this Mac")
            platform.scheduler.set_enabled(
                app_id, version.source.schedules, schedule_id, body.enabled
            )
            return {"schedules": platform.scheduler.status(app_id, version.source.schedules)}
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/apps/{app_id}/schedules/{schedule_id}/run")
    def run_schedule(app_id: str, schedule_id: str) -> dict[str, Any]:
        try:
            version = platform.registry.current(app_id)
            if platform.scheduler is None:
                raise OperationFailed("unavailable", "schedules are not running on this Mac")
            run_id = platform.scheduler.run_now(app_id, version.source.schedules, schedule_id)
            return {
                "run_id": run_id,
                "schedules": platform.scheduler.status(app_id, version.source.schedules),
            }
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/apps/{app_id}/actions/{action_id}/runs", response_model=Run, status_code=202)
    def run_action(app_id: str, action_id: str, body: ActionRunRequest) -> Run:
        try:
            return platform.runs.invoke(app_id, action_id, body.input, origin=body.origin)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/apps/{app_id}/records/mutate")
    def mutate_record(app_id: str, body: RecordMutationRequest) -> dict[str, Any]:
        """A person's own change to a module's data from the Data section: a new row, a
        correction (kept as the person's decision) or a removal. Not an App action: no handler
        runs, and the change is recorded as the person's."""
        try:
            platform.registry.current(app_id)
            store = platform.records.store(app_id)
            ctx = WriteContext(run_id=None, allow_correction=True, resolve_estimate=None)
            (result,) = store.apply([body.mutation], ctx)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {"record": None if result is None else result.model_dump(mode="json")}

    @app.post("/api/apps/{app_id}/records/query", response_model=RecordPage)
    def query_records(app_id: str, body: RecordQuery) -> RecordPage:
        try:
            platform.registry.current(app_id)
            return platform.records.store(app_id).query(body)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/apps/{app_id}/views/{view_id}/query")
    def query_view(app_id: str, view_id: str, body: ViewQueryRequest) -> dict[str, Any]:
        """The shell's bridge handler for records.query: Core enforces the declared view."""
        try:
            version = platform.registry.current(app_id)
            view = resolve_view(version.source, view_id)
            result = run_view(platform.records.store(app_id), view, body, platform.runs.timezone)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return result.model_dump(mode="json", by_alias=True)

    @app.post("/api/apps/{app_id}/records/aggregate", response_model=AggregateResult)
    def aggregate_records(app_id: str, body: AggregateQuery) -> AggregateResult:
        try:
            platform.registry.current(app_id)
            return platform.records.store(app_id).aggregate(body, platform.runs.timezone)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.get("/api/apps/{app_id}/artifacts")
    def list_artifacts(app_id: str, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        owner = ArtifactOwner(kind="app", id=app_id)
        return {
            "artifacts": [
                a.model_dump(mode="json") for a in platform.artifacts.list_for_owner(owner, limit)
            ]
        }

    @app.get("/api/artifacts/{artifact_id}", response_model=Artifact)
    def get_artifact(artifact_id: str) -> Artifact:
        try:
            return platform.artifacts.get(None, artifact_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.get("/api/artifacts/{artifact_id}/content")
    def artifact_content(artifact_id: str) -> Response:
        try:
            artifact, data = platform.artifacts.read(None, artifact_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return Response(
            content=data,
            media_type=artifact.media_type,
            headers={"X-Content-SHA256": artifact.sha256, "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/api/runs/{run_id}/model-calls")
    def run_model_calls(run_id: str) -> dict[str, Any]:
        return {"model_calls": platform.models.calls_for_run(run_id)}

    @app.post("/api/dev/fixture-apps/{name}/install")
    def install_fixture(name: str) -> dict[str, Any]:
        """Development/qualification only: install a neutral fixture App from the directory the
        host configured (ALPHA_DEV_FIXTURE_APPS_DIR). F08 installs Apps from verified builds."""
        root = platform.fixture_apps_dir
        if root is None or not _FIXTURE_NAME.match(name):
            raise HTTPException(status_code=404, detail="fixture_installs_disabled")
        package = root / name
        if not package.is_dir():
            raise HTTPException(status_code=404, detail="fixture_not_found")
        try:
            version = platform.registry.install(package)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        return {
            "app_id": version.app_id,
            "version_id": version.version_id,
            "release_id": version.release_id,
            "package_sha256": version.package_sha256,
            "runtime_profile_id": version.runtime_profile_id,
            "dependency_manifest_sha256": version.dependency_manifest_sha256,
        }
