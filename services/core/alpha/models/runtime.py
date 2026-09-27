"""Runtime model access for App and Task runs (F05: ctx.models).

A worker never holds a model credential or picks a route. It asks the broker for a bounded
structured call; this service checks the run's budget and input size, derives the JSON Schema
from the requested field specs, calls the platform route through the model gateway (usage is
recorded against the run), validates every returned value against the same specs and records the
call. The result is labelled an estimate; records that store it carry model provenance until a
person corrects them.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from alpha_contracts.broker import ModelEstimate, StructuredModelCall
from alpha_contracts.records import FieldKind, FieldProvenance, FieldSpec

from alpha.capabilities.errors import (
    FailureCode,
    OperationFailed,
    forbidden,
    invalid,
    limit,
    unavailable,
)
from alpha.data.values import fields_to_json_schema, validate_values
from alpha.models.gateway import ModelGateway, ModelRoute, RouteUnavailable
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, new_id, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS model_calls (
    call_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    owner_ref TEXT NOT NULL,
    route_id TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL,
    instruction_chars INTEGER NOT NULL,
    input_bytes INTEGER NOT NULL,
    output_json TEXT,
    error TEXT,
    elapsed_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS model_calls_run_idx ON model_calls(run_id);
"""

SYSTEM_PROMPT = (
    "You fill in a small structured estimate for a person's own tool. Use only the provided "
    "input and general knowledge. Return every required field, keep numbers inside the stated "
    "ranges and use only the listed choices. The person will see these values labelled as "
    "estimates and can correct them, so give your best single estimate rather than refusing."
)
_ALLOWED_OUTPUT_KINDS = {
    FieldKind.TEXT,
    FieldKind.NUMBER,
    FieldKind.INTEGER,
    FieldKind.BOOLEAN,
    FieldKind.DATE,
    FieldKind.DATETIME,
    FieldKind.CHOICE,
    FieldKind.JSON,  # a list or object for batch work: one call scores or extracts many items
}
# A batch answer (one entry per item) needs more room than a record's JSON field.
JSON_OUTPUT_MAX_BYTES = 65_536


def fake_estimate(fields: list[FieldSpec], instruction: str) -> dict[str, Any]:
    """Deterministic control responder for the `fake` route: in-bounds values derived only from
    the specs. `[fake:out-of-bounds]` in the instruction produces a violating value so the
    rejection path can be exercised."""
    breach = "[fake:out-of-bounds]" in instruction
    out: dict[str, Any] = {}
    for spec in fields:
        if spec.kind in (FieldKind.NUMBER, FieldKind.INTEGER):
            low, high = spec.minimum, spec.maximum
            if breach:
                value: Any = (
                    (high + 1) if high is not None else ((low - 1) if low is not None else -1)
                )
            elif low is not None and high is not None:
                value = (low + high) / 2
            else:
                value = low if low is not None else (high if high is not None else 1)
            out[spec.name] = int(value) if spec.kind is FieldKind.INTEGER else float(value)
        elif spec.kind is FieldKind.TEXT:
            out[spec.name] = f"estimated {spec.name}"[: spec.max_length or 2000]
        elif spec.kind is FieldKind.BOOLEAN:
            out[spec.name] = False
        elif spec.kind is FieldKind.DATE:
            out[spec.name] = date.today().isoformat()
        elif spec.kind is FieldKind.DATETIME:
            out[spec.name] = datetime.now(tz=UTC).isoformat()
        elif spec.kind is FieldKind.CHOICE:
            out[spec.name] = (spec.choices or [""])[0]
        elif spec.kind is FieldKind.JSON:
            out[spec.name] = [{"ref": 1, "estimate": f"estimated {spec.name}"}]
    return out


class AppModelService:
    def __init__(
        self,
        store: ControlStore,
        gateway: ModelGateway,
        inference: StructuredInference,
        route_id: str,
        *,
        max_calls_per_run: int = 10,
        max_input_bytes: int = 64_000,
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._inference = inference
        self._route_id = route_id
        self._max_calls = max_calls_per_run
        self._max_input = max_input_bytes
        store.execute_script(_SCHEMA)

    @property
    def route_id(self) -> str:
        return self._route_id

    def route(self) -> ModelRoute | None:
        """The configured route, or None when it is not enabled on this Mac."""
        try:
            return self._gateway.route(self._route_id, stage="app")
        except RouteUnavailable:
            return None

    def call(self, run_id: str, owner_ref: str, request: StructuredModelCall) -> ModelEstimate:
        for spec in request.fields:
            if spec.kind not in _ALLOWED_OUTPUT_KINDS:
                raise invalid(
                    f"model outputs cannot contain {spec.kind.value} fields", field=spec.name
                )
        names = [f.name for f in request.fields]
        if len(set(names)) != len(names):
            raise invalid("output field names must be unique")
        request = request.model_copy(
            update={
                "fields": [
                    f.model_copy(update={"max_bytes": f.max_bytes or JSON_OUTPUT_MAX_BYTES})
                    if f.kind is FieldKind.JSON
                    else f
                    for f in request.fields
                ]
            }
        )
        try:
            input_json = json.dumps(request.input, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError):
            raise invalid("model input must be plain JSON data") from None
        if len(input_json.encode("utf-8")) > self._max_input:
            raise limit(f"model input is limited to {self._max_input} bytes")
        used = self._store.query(
            "SELECT COUNT(*) AS n FROM model_calls WHERE run_id = ?", (run_id,)
        )[0]["n"]
        if used >= self._max_calls:
            raise limit(f"a run can make at most {self._max_calls} model calls", used=used)
        try:
            route = self._gateway.route(self._route_id, stage="app")
        except RouteUnavailable as exc:
            raise unavailable(str(exc)) from None
        schema = fields_to_json_schema(request.fields)
        prompt = f"{request.instruction}\n\nINPUT (JSON):\n{input_json}"
        call_id = new_id("mcall")
        started = utc_now()
        try:
            result = self._inference.call(
                route,
                system=SYSTEM_PROMPT,
                prompt=prompt,
                schema=schema,
                scope_kind="app_run",
                scope_ref=run_id,
                fake=lambda _prompt: fake_estimate(request.fields, request.instruction),
            )
        except InferenceError as exc:
            self._record(
                call_id,
                run_id,
                owner_ref,
                route.route_id,
                "unknown",
                "failed",
                request,
                input_json,
                None,
                f"{exc.code}: {exc}",
                started,
            )
            code: FailureCode = "timed_out" if exc.code == "timeout" else "unavailable"
            raise OperationFailed(
                code, f"the model call failed: {exc}", {"reason": exc.code}
            ) from None
        try:
            output = validate_values(
                request.fields, result.output, partial=False, collection="model output"
            )
        except OperationFailed as exc:
            self._record(
                call_id,
                run_id,
                owner_ref,
                route.route_id,
                result.model,
                "rejected",
                request,
                input_json,
                result.output,
                exc.message,
                started,
            )
            raise unavailable(
                "the model returned values outside the requested bounds; nothing was stored",
                reason="model_output_out_of_bounds",
                problem=exc.message,
            ) from None
        self._record(
            call_id,
            run_id,
            owner_ref,
            route.route_id,
            result.model,
            "ok",
            request,
            input_json,
            output,
            None,
            started,
        )
        return ModelEstimate(
            call_id=call_id,
            output=output,
            route=route.route_id,
            model=result.model,
            created_at=started,
        )

    def _record(
        self,
        call_id: str,
        run_id: str,
        owner_ref: str,
        route_id: str,
        model: str,
        status: str,
        request: StructuredModelCall,
        input_json: str,
        output: dict[str, Any] | None,
        error: str | None,
        started: datetime,
    ) -> None:
        elapsed = int((utc_now() - started).total_seconds() * 1000)
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO model_calls(call_id, run_id, owner_ref, route_id, model, status,
                   instruction_chars, input_bytes, output_json, error, elapsed_ms, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    call_id,
                    run_id,
                    owner_ref,
                    route_id,
                    model,
                    status,
                    len(request.instruction),
                    len(input_json.encode("utf-8")),
                    json.dumps(output, sort_keys=True) if output is not None else None,
                    error,
                    elapsed,
                    started.isoformat().replace("+00:00", "Z"),
                ),
            )

    def estimate_provenance(self, run_id: str, field: str, call_id: str) -> FieldProvenance:
        """Provenance for storing `field` as an estimate from `call_id`. The call must have been
        made by this same run and succeeded; provenance cannot be borrowed from another run."""
        rows = self._store.query(
            "SELECT * FROM model_calls WHERE call_id = ? AND run_id = ? AND status = 'ok'",
            (call_id, run_id),
        )
        if not rows:
            raise forbidden(
                f"{field} cites model call {call_id}, which this run did not make", field=field
            )
        row = rows[0]
        return FieldProvenance(
            source="model_estimate",
            at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
            call_id=call_id,
            route=row["route_id"],
            model=row["model"],
        )

    def calls_for_run(self, run_id: str) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._store.query(
                "SELECT * FROM model_calls WHERE run_id = ? ORDER BY created_at", (run_id,)
            )
        ]
