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
from alpha_contracts.records import AggregateQuery, AggregateResult, RecordPage, RecordQuery
from alpha_contracts.runs import Run, RunOrigin
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from alpha.artifacts.service import ArtifactService
from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.data.store import RecordService
from alpha.data.views import ViewQueryRequest, resolve_view, run_view
from alpha.execution.app_runs import AppRunService, HandlerBinder
from alpha.execution.broker import CapabilityBroker
from alpha.execution.profiles import ProfileInventory
from alpha.models.runtime import AppModelService
from alpha.solutions.registry import AppRegistry

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

    def close(self) -> None:
        self.records.close()


class ActionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input: dict[str, Any] = Field(default_factory=dict)
    origin: RunOrigin = RunOrigin.USER


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(app: FastAPI, platform: AppPlatform) -> None:
    @app.get("/api/runtime-profiles")
    def runtime_profiles() -> dict[str, Any]:
        return {"profiles": platform.inventory.list_profiles()}

    @app.get("/api/apps")
    def list_apps() -> dict[str, Any]:
        return {"apps": platform.registry.list_apps()}

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
            "ui": source.ui.model_dump(mode="json", by_alias=True) if source.ui else None,
        }

    @app.post("/api/apps/{app_id}/actions/{action_id}/runs", response_model=Run, status_code=202)
    def run_action(app_id: str, action_id: str, body: ActionRunRequest) -> Run:
        try:
            return platform.runs.invoke(app_id, action_id, body.input, origin=body.origin)
        except OperationFailed as exc:
            raise _fail(exc) from exc

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
            view = resolve_view(version.source.ui, view_id)
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
