"""FastAPI application for the trusted shell transport (typed HTTP commands plus SSE)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from collections.abc import AsyncIterator
from typing import Any

from alpha_contracts import CONTRACT_VERSION
from alpha_contracts.builds import BuildEvent
from alpha_contracts.runs import Run, RunEvent, RunOrigin
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from alpha import __version__
from alpha.api.auth import make_auth_middleware
from alpha.assistant.service import AssistantService, ConversationRecord
from alpha.assistant.service import ConflictError as AssistantBusy
from alpha.builds.service import AcceptanceExample, BuildNotReady, BuildRecord, BuildService
from alpha.capabilities.catalog import catalog_entries
from alpha.config import CoreSettings
from alpha.execution.coordinator import RunCoordinator
from alpha.models.gateway import ModelGateway, RouteUnavailable
from alpha.storage.control_store import ConflictError, ControlStore, NotFoundError

log = logging.getLogger("alpha.api")

# Set once an exit has been requested; long-lived responses (SSE) end promptly so the server can
# close instead of waiting on the shell's open stream.
shutting_down = threading.Event()


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


class BuildSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, max_length=4000)
    acceptance_examples: list[AcceptanceExample] = Field(min_length=1, max_length=20)
    instructions: str = Field(default="", max_length=4000)
    route_id: str = Field(default="fake", max_length=64)
    max_cost_usd: float | None = Field(default=None, ge=0)


class BuildList(BaseModel):
    builds: list[BuildRecord]


class BuildEventsPage(BaseModel):
    events: list[BuildEvent]
    next_after: int


class InvokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=64)
    input: dict[str, Any]


class ConversationStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    route_id: str | None = Field(default=None, max_length=64)


class ConversationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = Field(default=None, max_length=4000)
    answers: dict[str, str] | None = None
    use_defaults: bool = False


class ConversationList(BaseModel):
    conversations: list[ConversationRecord]


# WebKit (the Tauri WebView on macOS) does not hand small streamed-fetch chunks to JavaScript
# until enough bytes accumulate; a live SSE stream with ~1 KB frames stalls after the first few.
# Every frame is followed by a comment of this size so each write is flushed to the consumer.
# Comments are ignored by SSE parsers, and the stream is loopback-only.
SSE_FLUSH_PADDING = b": " + b" " * 8192 + b"\n\n"
SSE_POLL_SECONDS = 0.2
# WebKit also holds the most recent chunk until a following one arrives, so an idle stream sends a
# keepalive comment about once per second; that releases the final frames of a finished run.
SSE_KEEPALIVE_TICKS = 5


def create_app(
    settings: CoreSettings,
    store: ControlStore,
    coordinator: RunCoordinator,
    builds: BuildService | None = None,
    gateway: ModelGateway | None = None,
    assistant: AssistantService | None = None,
) -> FastAPI:
    app = FastAPI(title="Alpha Core", version=__version__, docs_url=None, redoc_url=None)
    app.middleware("http")(make_auth_middleware(settings.session_token, settings.allowed_origins))
    # The trusted shell runs on a different origin (tauri://localhost, or the Vite dev server),
    # so its browser engine preflights every credentialed request. Answer preflights only for
    # the host-approved origins; everything else gets no CORS allowance. This is outermost so a
    # preflight (which carries no bearer token by design) never reaches the auth middleware.
    if os.environ.get("ALPHA_LOG_REQUESTS") == "1":

        @app.middleware("http")
        async def log_requests(request: Request, call_next: Any) -> Any:
            response = await call_next(request)
            log.info(
                "%s %s origin=%s host=%s auth=%s -> %s",
                request.method,
                request.url.path,
                request.headers.get("origin"),
                request.headers.get("host"),
                "yes" if request.headers.get("authorization") else "no",
                response.status_code,
            )
            return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(settings.allowed_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["authorization", "content-type"],
        allow_credentials=False,
        max_age=600,
    )

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

    if builds is not None and gateway is not None:
        register_build_routes(app, builds, gateway)
    if assistant is not None:
        register_assistant_routes(app, assistant)

    @app.get("/api/events/stream")
    async def stream_events(
        request: Request, after: int = Query(default=0, ge=0)
    ) -> StreamingResponse:
        """Server-sent events for every run event after a durable cursor. Consumers resume by
        passing the last `id:` they saw; duplicate delivery is tolerated by design."""

        async def generate() -> AsyncIterator[bytes]:
            cursor = after
            idle_ticks = 0
            yield b": connected\n\n" + SSE_FLUSH_PADDING
            while not shutting_down.is_set():
                if await request.is_disconnected():
                    return
                batch = await asyncio.to_thread(store.events_after_cursor, cursor)
                for cursor, event in batch:
                    run = await asyncio.to_thread(store.get_run, event.run_id)
                    body: dict[str, Any] = {
                        "event": event.model_dump(mode="json"),
                        "run": run.model_dump(mode="json"),
                    }
                    frame = f"id: {cursor}\nevent: run_event\ndata: {json.dumps(body)}\n\n"
                    yield frame.encode() + SSE_FLUSH_PADDING
                if batch:
                    idle_ticks = 0
                    continue
                idle_ticks += 1
                if idle_ticks >= SSE_KEEPALIVE_TICKS:
                    idle_ticks = 0
                    yield b": keepalive\n\n" + SSE_FLUSH_PADDING
                await asyncio.sleep(SSE_POLL_SECONDS)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def coordinator_profiles(coordinator: RunCoordinator) -> list[str]:
    return list(coordinator.supervisor_profiles())


def register_build_routes(app: FastAPI, builds: BuildService, gateway: ModelGateway) -> None:
    @app.get("/api/model-routes")
    def model_routes() -> dict[str, Any]:
        return {"routes": gateway.routes()}

    @app.post("/api/builds", response_model=BuildRecord, status_code=201)
    def submit_build(body: BuildSubmission) -> BuildRecord:
        try:
            return builds.submit(
                goal=body.goal,
                acceptance_examples=body.acceptance_examples,
                instructions=body.instructions,
                route_id=body.route_id,
                max_cost_usd=body.max_cost_usd,
            )
        except RouteUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/builds", response_model=BuildList)
    def list_builds(limit: int = Query(default=50, ge=1, le=200)) -> BuildList:
        return BuildList(builds=builds.list_builds(limit=limit))

    @app.get("/api/builds/{build_id}", response_model=BuildRecord)
    def get_build(build_id: str) -> BuildRecord:
        try:
            return builds.get(build_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="build_not_found") from exc

    @app.get("/api/builds/{build_id}/events", response_model=BuildEventsPage)
    def build_events(build_id: str, after: int = Query(default=0, ge=0)) -> BuildEventsPage:
        try:
            events = builds.events(build_id, after=after)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="build_not_found") from exc
        return BuildEventsPage(events=events, next_after=events[-1].sequence if events else after)

    @app.post("/api/builds/{build_id}/cancel", response_model=BuildRecord)
    def cancel_build(build_id: str) -> BuildRecord:
        try:
            return builds.cancel(build_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="build_not_found") from exc
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/builds/{build_id}/invoke")
    def invoke_candidate(build_id: str, body: InvokeRequest) -> dict[str, Any]:
        try:
            return builds.invoke(build_id, body.action_id, body.input)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="build_not_found") from exc
        except BuildNotReady as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc


def register_assistant_routes(app: FastAPI, assistant: AssistantService) -> None:
    @app.get("/api/capabilities")
    def capabilities() -> dict[str, Any]:
        return {"capabilities": catalog_entries()}

    @app.post("/api/conversations", response_model=ConversationRecord, status_code=201)
    def start_conversation(body: ConversationStart) -> ConversationRecord:
        try:
            return assistant.start(body.text, body.route_id)
        except RouteUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/conversations", response_model=ConversationList)
    def list_conversations(limit: int = Query(default=20, ge=1, le=100)) -> ConversationList:
        return ConversationList(conversations=assistant.list_conversations(limit))

    @app.get("/api/conversations/{conversation_id}", response_model=ConversationRecord)
    def get_conversation(conversation_id: str) -> ConversationRecord:
        try:
            return assistant.get(conversation_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="conversation_not_found") from exc

    @app.post("/api/conversations/{conversation_id}/messages", response_model=ConversationRecord)
    def reply_conversation(conversation_id: str, body: ConversationMessage) -> ConversationRecord:
        try:
            return assistant.reply(
                conversation_id,
                text=body.text,
                answers=body.answers,
                use_defaults=body.use_defaults,
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="conversation_not_found") from exc
        except AssistantBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/conversations/{conversation_id}/briefs/{revision}")
    def get_brief_revision(conversation_id: str, revision: int) -> dict[str, Any]:
        record = assistant.get(conversation_id)
        if not record.current_brief:
            raise HTTPException(status_code=404, detail="no_brief")
        try:
            brief = assistant.brief_revision(record.current_brief.id, revision)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="revision_not_found") from exc
        return brief.model_dump(mode="json")
