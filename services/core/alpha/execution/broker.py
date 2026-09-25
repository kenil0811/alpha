"""Capability broker for App workers (Capability Protocol; Current Release Specification §7).

Order of checks for every call: parse the call (unknown fields rejected) → authenticate the
workload token (issued for this run, not revoked, and presented on this run's own pipe) → the
operation exists → the App declared the capability family → validate the arguments → execute
with the owner Core recorded for the run. Nothing a worker sends can name an owner, a store, a
route or a path.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from alpha_contracts.artifacts import ArtifactOwner, ArtifactProvenance, ArtifactRef, CreateArtifact
from alpha_contracts.broker import OPERATIONS, CapabilityCall, StructuredModelCall
from alpha_contracts.records import (
    AggregateQuery,
    CorrectRecord,
    CreateRecord,
    DeleteRecord,
    GetRecord,
    RecordBatch,
    RecordMutation,
    RecordQuery,
    UpdateRecord,
)
from alpha_contracts.runs import RunOrigin
from pydantic import BaseModel, ValidationError

from alpha.artifacts.service import ArtifactService
from alpha.capabilities.errors import OperationFailed, forbidden, invalid
from alpha.data.store import RecordService, WriteContext
from alpha.models.runtime import AppModelService
from alpha.storage.control_store import ControlStore, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS broker_tokens (
    token_sha256 TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    owner_ref TEXT NOT NULL,
    created_at TEXT NOT NULL,
    revoked_at TEXT
);
CREATE INDEX IF NOT EXISTS broker_tokens_run_idx ON broker_tokens(run_id);
"""

# Runs a person started may record corrections; triggers and repair tests may not.
_PERSON_ORIGINS = {RunOrigin.USER, RunOrigin.UI, RunOrigin.ASSISTANT}


@dataclass(frozen=True)
class RunGrant:
    run_id: str
    app_id: str
    action_id: str
    version_id: str
    package_sha256: str
    capabilities: frozenset[str]
    origin: RunOrigin
    timezone: str


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


class CapabilityBroker:
    def __init__(
        self,
        store: ControlStore,
        records: RecordService,
        artifacts: ArtifactService,
        models: AppModelService,
        on_event: Callable[[str, str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._store = store
        self._records = records
        self._artifacts = artifacts
        self._models = models
        self._on_event = on_event
        self._grants: dict[str, RunGrant] = {}
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)

    def revoke_all_on_startup(self) -> int:
        """Tokens from a previous Core instance can never be valid again."""
        with self._store.transaction() as conn:
            cursor = conn.execute(
                "UPDATE broker_tokens SET revoked_at = ? WHERE revoked_at IS NULL", (_now(),)
            )
            return cursor.rowcount

    def issue(self, grant: RunGrant) -> str:
        token = secrets.token_urlsafe(32)
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO broker_tokens(token_sha256, run_id, owner_ref, created_at)
                   VALUES (?,?,?,?)""",
                (_hash(token), grant.run_id, f"app:{grant.app_id}", _now()),
            )
        with self._lock:
            self._grants[grant.run_id] = grant
        return token

    def revoke(self, run_id: str) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE broker_tokens SET revoked_at = ? WHERE run_id = ? AND revoked_at IS NULL",
                (_now(), run_id),
            )
        with self._lock:
            self._grants.pop(run_id, None)

    def handle(self, channel_run_id: str, message: dict[str, Any]) -> dict[str, Any]:
        """Handle one call that arrived on `channel_run_id`'s pipe; always returns a reply."""
        started = time.monotonic()
        call_id = str(message.get("call_id", "unknown"))[:32]
        operation = str(message.get("operation", ""))[:64]
        try:
            try:
                call = CapabilityCall.model_validate(message)
            except ValidationError as exc:
                raise invalid("malformed capability call", problems=_problems(exc)) from None
            grant = self._authenticate(channel_run_id, call.token)
            if call.operation not in OPERATIONS:
                raise invalid(
                    f"unknown operation {call.operation!r}", operations=sorted(OPERATIONS)
                )
            family = call.operation.split(".", 1)[0]
            if family not in grant.capabilities:
                raise forbidden(
                    f"this App did not declare the {family} capability",
                    declared=sorted(grant.capabilities),
                )
            result = self._dispatch(grant, call.operation, call.args)
            reply = {"kind": "reply", "call_id": call_id, "status": "completed", "result": result}
            self._event(channel_run_id, operation, "completed", None, started)
            return reply
        except OperationFailed as exc:
            self._event(channel_run_id, operation, "failed", exc.code, started)
            return {
                "kind": "reply",
                "call_id": call_id,
                "status": "failed",
                "error": exc.as_error(),
            }
        except Exception as exc:  # never let a worker call crash the reader thread
            self._event(channel_run_id, operation, "failed", "internal_error", started)
            return {
                "kind": "reply",
                "call_id": call_id,
                "status": "failed",
                "error": {"code": "internal_error", "message": type(exc).__name__, "details": {}},
            }

    def _authenticate(self, channel_run_id: str, token: str) -> RunGrant:
        rows = self._store.query(
            "SELECT run_id, revoked_at FROM broker_tokens WHERE token_sha256 = ?", (_hash(token),)
        )
        if not rows or rows[0]["revoked_at"] is not None:
            raise OperationFailed("unauthenticated", "the workload token is not valid")
        if rows[0]["run_id"] != channel_run_id:
            raise OperationFailed(
                "unauthenticated", "the workload token belongs to a different run"
            )
        with self._lock:
            grant = self._grants.get(channel_run_id)
        if grant is None:
            raise OperationFailed("unauthenticated", "the run is no longer active")
        return grant

    def _event(
        self, run_id: str, operation: str, status: str, code: str | None, started: float
    ) -> None:
        if self._on_event is None:
            return
        payload: dict[str, Any] = {
            "operation": operation,
            "status": status,
            "elapsed_ms": int((time.monotonic() - started) * 1000),
        }
        if code:
            payload["code"] = code
        self._on_event(run_id, "capability.call", payload)

    def _dispatch(self, grant: RunGrant, operation: str, args: dict[str, Any]) -> Any:
        store = self._records.store(grant.app_id)
        ctx = WriteContext(
            run_id=grant.run_id,
            allow_correction=grant.origin in _PERSON_ORIGINS,
            resolve_estimate=lambda field, call_id: self._models.estimate_provenance(
                grant.run_id, field, call_id
            ),
        )
        owner = ArtifactOwner(kind="app", id=grant.app_id)
        if operation == "records.get":
            get = _parse(GetRecord, args)
            return store.get(get.collection, get.id).model_dump(mode="json")
        if operation == "records.query":
            return store.query(_parse(RecordQuery, args)).model_dump(mode="json", by_alias=True)
        if operation == "records.aggregate":
            return store.aggregate(_parse(AggregateQuery, args), grant.timezone).model_dump(
                mode="json"
            )
        if operation in ("records.create", "records.update", "records.correct", "records.delete"):
            models: dict[str, type[BaseModel]] = {
                "records.create": CreateRecord,
                "records.update": UpdateRecord,
                "records.correct": CorrectRecord,
                "records.delete": DeleteRecord,
            }
            model = models[operation]
            mutation: RecordMutation = _parse(model, args)  # type: ignore[assignment]
            (result,) = store.apply([mutation], ctx)
            return None if result is None else result.model_dump(mode="json")
        if operation == "records.batch":
            batch = _parse(RecordBatch, args)
            results = store.apply(list(batch.operations), ctx)
            return {"results": [None if r is None else r.model_dump(mode="json") for r in results]}
        if operation == "artifacts.create":
            request = _parse(CreateArtifact, args)
            for call_id in request.model_call_ids:
                self._models.estimate_provenance(grant.run_id, "artifact", call_id)
            provenance = ArtifactProvenance(
                created_by="app_run",
                run_id=grant.run_id,
                action_id=grant.action_id,
                version_id=grant.version_id,
                package_sha256=grant.package_sha256,
                derived_from=request.derived_from,
                model_call_ids=request.model_call_ids,
            )
            return self._artifacts.create(owner, request, provenance).model_dump(mode="json")
        if operation == "artifacts.get":
            ref = _parse(ArtifactRef, args)
            return self._artifacts.get(owner, ref.artifact_id).model_dump(mode="json")
        if operation == "artifacts.read":
            ref = _parse(ArtifactRef, args)
            artifact, data = self._artifacts.read(owner, ref.artifact_id)
            return {
                **artifact.model_dump(mode="json"),
                "content_b64": base64.b64encode(data).decode("ascii"),
            }
        if operation == "models.structured":
            request_m = _parse(StructuredModelCall, args)
            return self._models.call(grant.run_id, f"app:{grant.app_id}", request_m).model_dump(
                mode="json"
            )
        raise invalid(f"unknown operation {operation!r}")  # pragma: no cover


def _problems(exc: ValidationError) -> list[str]:
    return [
        f"{'.'.join(str(p) for p in err['loc']) or '(call)'}: {err['msg']}"
        for err in exc.errors()[:10]
    ]


def _parse[M: BaseModel](model: type[M], args: dict[str, Any]) -> M:
    try:
        return model.model_validate(args)
    except ValidationError as exc:
        raise invalid("the operation's arguments are not valid", problems=_problems(exc)) from None
