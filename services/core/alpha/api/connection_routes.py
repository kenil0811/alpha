"""Connections between modules: what a module reads from others, the person's switches, and
the related records the shell shows for relation fields."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from alpha.capabilities.errors import HTTP_STATUS, OperationFailed
from alpha.context.connections import ConnectionService


class SwitchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


def _fail(exc: OperationFailed) -> HTTPException:
    return HTTPException(status_code=HTTP_STATUS.get(exc.code, 500), detail=exc.as_error())


def register(app: FastAPI, connections: ConnectionService) -> None:
    @app.get("/api/apps/{app_id}/connections")
    def list_connections(app_id: str) -> dict[str, Any]:
        try:
            return {"connections": connections.declared(app_id)}
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.put("/api/apps/{app_id}/connections/{module}")
    def switch_connection(app_id: str, module: str, body: SwitchRequest) -> dict[str, Any]:
        try:
            return {"connections": connections.set_enabled(app_id, module, body.enabled)}
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.get("/api/apps/{app_id}/related/{module}/{collection}")
    def pick_related(
        app_id: str, module: str, collection: str, q: str = Query(default="", max_length=200)
    ) -> dict[str, Any]:
        """Rows of a connected module's collection to choose a relation from."""
        try:
            return {"rows": connections.pick(app_id, module, collection, q)}
        except OperationFailed as exc:
            raise _fail(exc) from exc

    @app.get("/api/apps/{app_id}/related/{module}/{collection}/{record_id}")
    def get_related(app_id: str, module: str, collection: str, record_id: str) -> dict[str, Any]:
        try:
            record = connections.get(app_id, module, collection, record_id)
        except OperationFailed as exc:
            raise _fail(exc) from exc
        title = connections.title_field(module, collection)
        return {
            "id": record.id,
            "title": str(record.values.get(title) or record.id) if title else record.id,
            "values": record.values,
        }
