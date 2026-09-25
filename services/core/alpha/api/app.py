"""FastAPI application for the trusted shell transport (typed HTTP commands plus SSE)."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import AsyncIterator
from typing import Any

from alpha_contracts import CONTRACT_VERSION
from alpha_contracts.runs import Run, RunEvent, RunOrigin
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from alpha import __version__
from alpha.api.auth import make_auth_middleware
from alpha.config import CoreSettings
from alpha.execution.coordinator import RunCoordinator
from alpha.storage.control_store import ConflictError, ControlStore, NotFoundError


class SyntheticRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", max_length=10_000)
    steps: int = Field(default=3, ge=0, le=100)
    delay_seconds: float = Field(default=0.05, ge=0, le=10)
    mode: str = Field(default="succeed", pattern=r"^(succeed|fail|hang|crash|exit_without_result)$")
    spawn_child: bool = False
    timeout_seconds: int = Field(default=60, ge=1, le=3600)


class HealthResponse(BaseModel):
    status: str
    core_version: str
    contract_version: str
    core_instance_id: str
    python_version: str
    python_executable: str
    python_prefix: str
    data_dir: str
    worker_profiles: list[str]
    active_runs: list[str]


class EventsPage(BaseModel):
    events: list[RunEvent]
    next_after: int


class RunList(BaseModel):
    runs: list[Run]


def create_app(settings: CoreSettings, store: ControlStore, coordinator: RunCoordinator) -> FastAPI:
    app = FastAPI(title="Alpha Core", version=__version__, docs_url=None, redoc_url=None)
    app.middleware("http")(make_auth_middleware(settings.session_token, settings.allowed_origins))

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            core_version=__version__,
            contract_version=CONTRACT_VERSION,
            core_instance_id=coordinator.instance_id,
            python_version=sys.version,
            python_executable=sys.executable,
            python_prefix=sys.prefix,
            data_dir=str(settings.data_dir),
            worker_profiles=sorted(coordinator_profiles(coordinator)),
            active_runs=coordinator.active_run_ids(),
        )

    @app.post("/api/runs", response_model=Run, status_code=201)
    def create_run(body: SyntheticRunRequest) -> Run:
        return coordinator.submit_synthetic(body.model_dump(), origin=RunOrigin.USER)

    @app.get("/api/runs", response_model=RunList)
    def list_runs(limit: int = Query(default=50, ge=1, le=200)) -> RunList:
        return RunList(runs=store.list_runs(limit=limit))

    @app.get("/api/runs/{run_id}", response_model=Run)
    def get_run(run_id: str) -> Run:
        try:
            return store.get_run(run_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.get("/api/runs/{run_id}/events", response_model=EventsPage)
    def get_events(run_id: str, after: int = Query(default=0, ge=0)) -> EventsPage:
        try:
            store.get_run(run_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        events = store.get_events(run_id, after_sequence=after)
        return EventsPage(events=events, next_after=events[-1].sequence if events else after)

    @app.post("/api/runs/{run_id}/cancel", response_model=Run)
    def cancel_run(run_id: str) -> Run:
        try:
            return coordinator.cancel(run_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/events/stream")
    async def stream_events(
        request: Request, after: int = Query(default=0, ge=0)
    ) -> StreamingResponse:
        """Server-sent events for every run event after a durable cursor. Consumers resume by
        passing the last `id:` they saw; duplicate delivery is tolerated by design."""

        async def generate() -> AsyncIterator[bytes]:
            cursor = after
            yield b": connected\n\n"
            while True:
                if await request.is_disconnected():
                    return
                batch = await asyncio.to_thread(store.events_after_cursor, cursor)
                for cursor, event in batch:
                    run = await asyncio.to_thread(store.get_run, event.run_id)
                    body: dict[str, Any] = {
                        "event": event.model_dump(mode="json"),
                        "run": run.model_dump(mode="json"),
                    }
                    yield f"id: {cursor}\nevent: run_event\ndata: {json.dumps(body)}\n\n".encode()
                if not batch:
                    await asyncio.sleep(0.2)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def coordinator_profiles(coordinator: RunCoordinator) -> list[str]:
    return list(coordinator.supervisor_profiles())
