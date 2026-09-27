"""Shell-facing routes for creating a result from a conversation (F08).

The shell asks Core to create an App from the current brief, then follows one creation record
whose stage and label are already in the person's language. Core owns every state change.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.solutions.creation import CreationRecord, CreationRefused, CreationService
from alpha.storage.control_store import NotFoundError


class CreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Control fixture only, honoured when the builder route is `fake`: the fake builder's mode
    # and arguments (for example "package notes_ok"); see alpha.builds.harness_fake.
    builder_hint: str | None = Field(
        default=None, max_length=120, pattern=r"^[a-z][a-z0-9_]*(?: [a-z0-9_-]+){0,6}$"
    )


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(app: FastAPI, creations: CreationService) -> None:
    @app.post(
        "/api/conversations/{conversation_id}/creations",
        response_model=CreationRecord,
        status_code=202,
    )
    def start_creation(conversation_id: str, body: CreationRequest) -> CreationRecord:
        try:
            return creations.start(conversation_id, builder_hint=body.builder_hint)
        except CreationRefused as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OperationFailed as exc:
            raise _fail(exc) from exc
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail="conversation_not_found") from exc

    @app.get("/api/apps/{app_id}/conversations")
    def app_conversations(app_id: str) -> dict[str, Any]:
        """The module's own thread: its creation and every change since, newest first."""
        return {"conversations": creations.conversations_for_app(app_id)}

    @app.get("/api/apps/{app_id}/checks")
    def app_checks(app_id: str) -> dict[str, Any]:
        """Where the module's latest fast-lane behaviour checks stand, if any."""
        return {"checks": creations.checks_for_app(app_id)}

    @app.get("/api/conversations/{conversation_id}/creations")
    def conversation_creations(conversation_id: str) -> dict[str, Any]:
        return {"creations": creations.list_for_conversation(conversation_id)}

    @app.get("/api/creations")
    def recent_creations(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        return {"creations": creations.list_recent(limit)}

    @app.get("/api/creations/{creation_id}", response_model=CreationRecord)
    def get_creation(creation_id: str) -> CreationRecord:
        try:
            return creations.get(creation_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.post("/api/creations/{creation_id}/cancel", response_model=CreationRecord)
    def cancel_creation(creation_id: str) -> CreationRecord:
        try:
            return creations.cancel(creation_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
