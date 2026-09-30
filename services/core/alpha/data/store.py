"""Per-App record stores (Domain and Persistence Model; Implementation Blueprint §8).

Each App owns one SQLite file under the platform data directory: collection schema metadata,
validated JSON rows with revisions and provenance, idempotency records and uniqueness keys.
Nothing here is reachable by generated code except through the capability broker, which selects
the store from the authenticated run's owner, never from anything the worker says.

Writes are compare-and-swap in the statement itself; zero affected rows is a conflict or a
missing record, never success. A batch is one transaction in one App store.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alpha_contracts.records import (
    AggregateGroup,
    AggregateQuery,
    AggregateResult,
    CollectionSchema,
    CorrectRecord,
    CreateRecord,
    DeleteRecord,
    FieldKind,
    FieldProvenance,
    Record,
    RecordMutation,
    RecordPage,
    RecordQuery,
    UpdateRecord,
)

from alpha.capabilities.errors import OperationFailed, conflict, forbidden, invalid, not_found
from alpha.data import query as q
from alpha.data.values import format_datetime, validate_values

_SCHEMA = """
CREATE TABLE IF NOT EXISTS store_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS collections (
    name TEXT PRIMARY KEY,
    schema_json TEXT NOT NULL,
    schema_sha256 TEXT NOT NULL,
    registered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    collection TEXT NOT NULL REFERENCES collections(name),
    record_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    values_json TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    created_by_run TEXT,
    updated_by_run TEXT,
    PRIMARY KEY (collection, record_id)
);
CREATE INDEX IF NOT EXISTS records_created_idx ON records(collection, created_at, record_id);
CREATE TABLE IF NOT EXISTS idempotency (
    collection TEXT NOT NULL,
    idem_key TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    record_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (collection, idem_key)
);
CREATE TABLE IF NOT EXISTS unique_keys (
    collection TEXT NOT NULL,
    constraint_name TEXT NOT NULL,
    value_sha256 TEXT NOT NULL,
    record_id TEXT NOT NULL,
    PRIMARY KEY (collection, constraint_name, value_sha256)
);
CREATE INDEX IF NOT EXISTS unique_keys_record_idx ON unique_keys(collection, record_id);
"""


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _ts(value: datetime) -> str:
    return format_datetime(value)


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# Resolves (field, call_id) to the provenance of a model estimate made in the same run, or raises.
EstimateResolver = Callable[[str, str], FieldProvenance]


@dataclass(frozen=True)
class WriteContext:
    run_id: str | None
    allow_correction: bool
    resolve_estimate: EstimateResolver | None


def schema_change_problems(before: CollectionSchema, after: CollectionSchema) -> list[str]:
    """Why records saved under `before` might not fit `after` (empty when the change is
    additive). Removing or retyping a field, making one required, narrowing its choices,
    tightening a bound or adding a unique constraint can all invalidate saved records."""
    problems: list[str] = []
    old = {f.name: f for f in before.fields}
    new = {f.name: f for f in after.fields}
    for name, field in old.items():
        if name not in new:
            problems.append(f"field {name} was removed")
            continue
        changed = new[name]
        if changed.kind is not field.kind:
            problems.append(f"field {name} changed from {field.kind.value} to {changed.kind.value}")
        if changed.required and not field.required:
            problems.append(f"field {name} became required")
        if field.choices is not None and (
            changed.choices is None or not set(field.choices) <= set(changed.choices)
        ):
            problems.append(f"field {name} lost choices records may use")
        if changed.collection != field.collection:
            problems.append(f"field {name} now points at a different table")
        for bound in ("max_length", "max_bytes", "maximum", "minimum"):
            new_value: float | None = getattr(changed, bound)
            old_value: float | None = getattr(field, bound)
            if new_value is None:
                continue  # dropping a bound only widens what fits
            if old_value is None or (
                new_value > old_value if bound == "minimum" else new_value < old_value
            ):
                problems.append(f"field {name} tightened its {bound}")
    for name, field in new.items():
        if name not in old and field.required:
            problems.append(f"new field {name} is required (new fields must be optional)")
    if [sorted(u) for u in after.unique] != [sorted(u) for u in before.unique]:
        if any(sorted(u) not in [sorted(v) for v in before.unique] for u in after.unique):
            problems.append("a new uniqueness rule could already be broken by saved records")
    return problems


class AppRecordStore:
    def __init__(self, path: Path, app_id: str, policy: q.QueryPolicy = q.DEFAULT_POLICY) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.app_id = app_id
        self.path = path
        self._policy = policy
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.create_function("alpha_bucket", 4, q.bucket_value, deterministic=True)
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO store_meta(key, value) VALUES ('app_id', ?)", (app_id,)
        )
        owner = self._conn.execute("SELECT value FROM store_meta WHERE key='app_id'").fetchone()
        if owner["value"] != app_id:
            raise RuntimeError(f"record store {path} belongs to {owner['value']}, not {app_id}")
        self._schemas: dict[str, CollectionSchema] = {}
        for row in self._conn.execute("SELECT schema_json FROM collections"):
            schema = CollectionSchema.model_validate_json(row["schema_json"])
            self._schemas[schema.name] = schema

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    # ----- schema -------------------------------------------------------------------------

    def register_collections(self, schemas: list[CollectionSchema]) -> list[dict[str, str]]:
        """Register declared collections. Identical schemas are a no-op. A changed schema is
        accepted only when every record already saved stays valid under it (additive: new
        optional fields, wider choices, new indexes); anything that would orphan or invalidate
        saved records is refused, so a changed App never loses the person's data."""
        report: list[dict[str, str]] = []
        with self._tx() as conn:
            for schema in schemas:
                body = schema.model_dump(mode="json")
                digest = _digest(body)
                row = conn.execute(
                    "SELECT schema_json, schema_sha256 FROM collections WHERE name = ?",
                    (schema.name,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        """INSERT INTO collections(name, schema_json, schema_sha256, registered_at)
                           VALUES (?,?,?,?)""",
                        (schema.name, json.dumps(body, sort_keys=True), digest, _ts(_now())),
                    )
                    report.append({"collection": schema.name, "status": "registered"})
                elif row["schema_sha256"] != digest:
                    before = CollectionSchema.model_validate_json(row["schema_json"])
                    problems = schema_change_problems(before, schema)
                    if problems:
                        raise conflict(
                            f"collection {schema.name} already exists and the new shape would "
                            "not fit the records already saved: " + "; ".join(problems),
                            collection=schema.name,
                            problems=problems,
                        )
                    conn.execute(
                        "UPDATE collections SET schema_json = ?, schema_sha256 = ? WHERE name = ?",
                        (json.dumps(body, sort_keys=True), digest, schema.name),
                    )
                    report.append({"collection": schema.name, "status": "migrated"})
                else:
                    report.append({"collection": schema.name, "status": "unchanged"})
                for fields in schema.indexes:
                    # Field names are validated identifiers; see query.resolve_field.
                    exprs = ", ".join(
                        q.resolve_field(schema, f).expr.replace("r.", "") for f in fields
                    )
                    name = f"ix_{schema.name}_{'_'.join(fields)}"
                    conn.execute(
                        f"CREATE INDEX IF NOT EXISTS {name} ON records(collection, {exprs})"
                    )
        for schema in schemas:
            self._schemas[schema.name] = schema
        return report

    def schema(self, collection: str) -> CollectionSchema:
        schema = self._schemas.get(collection)
        if schema is None:
            raise not_found(
                f"this App has no collection {collection!r}",
                collection=collection,
                collections=sorted(self._schemas),
            )
        return schema

    def collections(self) -> list[CollectionSchema]:
        return list(self._schemas.values())

    # ----- reads --------------------------------------------------------------------------

    def get(self, collection: str, record_id: str) -> Record:
        self.schema(collection)
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM records WHERE collection = ? AND record_id = ?",
                (collection, record_id),
            ).fetchone()
        if row is None:
            raise not_found(
                f"no {collection} record {record_id}", collection=collection, id=record_id
            )
        return _row_to_record(row)

    def query(self, query: RecordQuery) -> RecordPage:
        schema = self.schema(query.collection)
        page = q.check_page_limit(query.limit, self._policy)
        offset = q.decode_cursor(query, self._policy)
        where_sql, params = q.compile_filter(schema, query.where, self._policy)
        order = q.compile_order(schema, query.order_by)
        sql = (
            f"SELECT * FROM records r WHERE r.collection = ? AND {where_sql} "
            f"ORDER BY {order} LIMIT ? OFFSET ?"
        )
        with self._lock:
            rows = self._conn.execute(sql, [query.collection, *params, page + 1, offset]).fetchall()
        records = [_row_to_record(row) for row in rows[:page]]
        if query.fields is not None:
            wanted = set(query.fields)
            for name in wanted:
                q.resolve_field(schema, name)
            records = [
                r.model_copy(
                    update={
                        "values": {k: v for k, v in r.values.items() if k in wanted},
                        "provenance": {k: v for k, v in r.provenance.items() if k in wanted},
                    }
                )
                for r in records
            ]
        next_cursor = q.encode_cursor(query, offset + page) if len(rows) > page else None
        return RecordPage(records=records, next_cursor=next_cursor)

    def aggregate(self, query: AggregateQuery, default_timezone: str) -> AggregateResult:
        schema = self.schema(query.collection)
        sql, params, keys, metrics = q.compile_aggregate(
            schema, query, default_timezone, self._policy
        )
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        groups: list[AggregateGroup] = []
        for row in rows[: query.limit]:
            key = {name: row[f"k{i}"] for i, name in enumerate(keys)}
            values = {name: row[f"m_{name}"] for name in metrics}
            groups.append(AggregateGroup(key=key, values=values))
        return AggregateResult(groups=groups, truncated=len(rows) > query.limit)

    # ----- writes -------------------------------------------------------------------------

    def apply(self, mutations: list[RecordMutation], ctx: WriteContext) -> list[Record | None]:
        """Apply mutations in one transaction: all commit or none do."""
        results: list[Record | None] = []
        with self._tx() as conn:
            for index, mutation in enumerate(mutations):
                try:
                    results.append(self._apply_one(conn, mutation, ctx))
                except OperationFailed as exc:
                    if len(mutations) > 1:
                        exc.details = {**exc.details, "operation_index": index}
                        exc.message = f"operation {index + 1} of {len(mutations)}: {exc.message}"
                    raise
        return results

    def _apply_one(
        self, conn: sqlite3.Connection, mutation: RecordMutation, ctx: WriteContext
    ) -> Record | None:
        if isinstance(mutation, CreateRecord):
            return self._create(conn, mutation, ctx)
        if isinstance(mutation, UpdateRecord):
            return self._change(
                conn,
                mutation.collection,
                mutation.id,
                mutation.expected_revision,
                mutation.changes,
                mutation.estimated,
                ctx,
                correction=False,
            )
        if isinstance(mutation, CorrectRecord):
            if not ctx.allow_correction:
                raise forbidden(
                    "corrections can only come from a run a person started (UI, assistant or "
                    "manual), not from a trigger or another automated run"
                )
            return self._change(
                conn,
                mutation.collection,
                mutation.id,
                mutation.expected_revision,
                mutation.changes,
                {},
                ctx,
                correction=True,
            )
        assert isinstance(mutation, DeleteRecord)
        self._delete(conn, mutation)
        return None

    def _estimate_provenance(
        self, estimated: dict[str, str], values: dict[str, Any], ctx: WriteContext
    ) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for name, call_id in estimated.items():
            if values.get(name) is None:
                raise invalid(f"{name} is marked as an estimate but has no value", field=name)
            if ctx.resolve_estimate is None:
                raise forbidden("model estimates can only be recorded from an App run")
            out[name] = ctx.resolve_estimate(name, call_id).model_dump(mode="json")
        return out

    def _check_references(
        self, conn: sqlite3.Connection, schema: CollectionSchema, values: dict[str, Any]
    ) -> None:
        for spec in schema.fields:
            if spec.kind is FieldKind.REFERENCE and values.get(spec.name) is not None:
                found = conn.execute(
                    "SELECT 1 FROM records WHERE collection = ? AND record_id = ?",
                    (spec.collection, values[spec.name]),
                ).fetchone()
                if found is None:
                    raise invalid(
                        f"{schema.name}.{spec.name} points to a {spec.collection} record that "
                        "does not exist",
                        field=spec.name,
                    )

    def _write_unique_keys(
        self,
        conn: sqlite3.Connection,
        schema: CollectionSchema,
        record_id: str,
        values: dict[str, Any],
    ) -> None:
        conn.execute(
            "DELETE FROM unique_keys WHERE collection = ? AND record_id = ?",
            (schema.name, record_id),
        )
        for fields in schema.unique:
            parts = [values.get(f) for f in fields]
            if any(p is None for p in parts):
                continue
            name = "+".join(fields)
            try:
                conn.execute(
                    """INSERT INTO unique_keys(collection, constraint_name, value_sha256, record_id)
                       VALUES (?,?,?,?)""",
                    (schema.name, name, _digest(parts), record_id),
                )
            except sqlite3.IntegrityError:
                raise conflict(
                    f"another {schema.name} record already has this {' and '.join(fields)}",
                    fields=fields,
                ) from None

    def _create(
        self, conn: sqlite3.Connection, mutation: CreateRecord, ctx: WriteContext
    ) -> Record:
        schema = self.schema(mutation.collection)
        values = validate_values(
            schema.fields, mutation.values, partial=False, collection=schema.name
        )
        values = {k: v for k, v in values.items() if v is not None}
        if mutation.idempotency_key is not None:
            payload = _digest({"values": values, "estimated": mutation.estimated})
            prior = conn.execute(
                """SELECT payload_sha256, record_id FROM idempotency
                   WHERE collection = ? AND idem_key = ?""",
                (schema.name, mutation.idempotency_key),
            ).fetchone()
            if prior is not None:
                if prior["payload_sha256"] != payload:
                    raise conflict(
                        "this idempotency key was already used with different values",
                        idempotency_key=mutation.idempotency_key,
                    )
                row = conn.execute(
                    "SELECT * FROM records WHERE collection = ? AND record_id = ?",
                    (schema.name, prior["record_id"]),
                ).fetchone()
                if row is None:
                    raise conflict("the record created with this idempotency key was deleted")
                return _row_to_record(row)
        self._check_references(conn, schema, values)
        provenance = self._estimate_provenance(mutation.estimated, values, ctx)
        record_id = f"rec_{uuid.uuid4().hex}"
        now = _ts(_now())
        self._write_unique_keys(conn, schema, record_id, values)
        conn.execute(
            """INSERT INTO records(collection, record_id, revision, values_json, provenance_json,
               created_at, updated_at, created_by_run, updated_by_run)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                schema.name,
                record_id,
                1,
                json.dumps(values, sort_keys=True),
                json.dumps(provenance, sort_keys=True),
                now,
                now,
                ctx.run_id,
                ctx.run_id,
            ),
        )
        if mutation.idempotency_key is not None:
            conn.execute(
                """INSERT INTO idempotency(collection, idem_key, payload_sha256, record_id,
                   created_at) VALUES (?,?,?,?,?)""",
                (
                    schema.name,
                    mutation.idempotency_key,
                    _digest({"values": values, "estimated": mutation.estimated}),
                    record_id,
                    now,
                ),
            )
        row = conn.execute(
            "SELECT * FROM records WHERE collection = ? AND record_id = ?", (schema.name, record_id)
        ).fetchone()
        return _row_to_record(row)

    def _change(
        self,
        conn: sqlite3.Connection,
        collection: str,
        record_id: str,
        expected_revision: int,
        changes: dict[str, Any],
        estimated: dict[str, str],
        ctx: WriteContext,
        *,
        correction: bool,
    ) -> Record:
        schema = self.schema(collection)
        normalized = validate_values(schema.fields, changes, partial=True, collection=schema.name)
        current = conn.execute(
            "SELECT * FROM records WHERE collection = ? AND record_id = ?", (collection, record_id)
        ).fetchone()
        if current is None:
            raise not_found(
                f"no {collection} record {record_id}", collection=collection, id=record_id
            )
        values = json.loads(current["values_json"])
        provenance: dict[str, dict[str, Any]] = json.loads(current["provenance_json"])
        now = _now()
        for name, value in normalized.items():
            previous_value = values.get(name)
            if value is None:
                values.pop(name, None)
            else:
                values[name] = value
            if correction:
                prior = provenance.get(name)
                provenance[name] = FieldProvenance(
                    source="user_correction",
                    at=now,
                    previous={
                        "value": previous_value,
                        "source": (prior or {}).get("source", "app"),
                        "call_id": (prior or {}).get("call_id"),
                    },
                ).model_dump(mode="json")
            else:
                provenance.pop(name, None)
        for name, estimate in self._estimate_provenance(estimated, values, ctx).items():
            provenance[name] = estimate
        self._check_references(conn, schema, values)
        self._write_unique_keys(conn, schema, record_id, values)
        cursor = conn.execute(
            """UPDATE records SET values_json = ?, provenance_json = ?, revision = revision + 1,
               updated_at = ?, updated_by_run = ?
               WHERE collection = ? AND record_id = ? AND revision = ?""",
            (
                json.dumps(values, sort_keys=True),
                json.dumps(provenance, sort_keys=True),
                _ts(now),
                ctx.run_id,
                collection,
                record_id,
                expected_revision,
            ),
        )
        if cursor.rowcount == 0:
            raise conflict(
                f"{collection} record {record_id} changed since it was read "
                f"(expected revision {expected_revision}, current {current['revision']})",
                expected_revision=expected_revision,
                current_revision=current["revision"],
            )
        row = conn.execute(
            "SELECT * FROM records WHERE collection = ? AND record_id = ?", (collection, record_id)
        ).fetchone()
        return _row_to_record(row)

    def _delete(self, conn: sqlite3.Connection, mutation: DeleteRecord) -> None:
        schema = self.schema(mutation.collection)
        for other in self._schemas.values():
            for spec in other.fields:
                if spec.kind is FieldKind.REFERENCE and spec.collection == schema.name:
                    count = conn.execute(
                        f"SELECT COUNT(*) AS n FROM records r WHERE r.collection = ? AND "
                        f"{q.resolve_field(other, spec.name).expr} = ?",
                        (other.name, mutation.id),
                    ).fetchone()["n"]
                    if count:
                        raise conflict(
                            f"{count} {other.name} record(s) still point to this {schema.name} "
                            "record",
                            referenced_by=other.name,
                        )
        cursor = conn.execute(
            "DELETE FROM records WHERE collection = ? AND record_id = ? AND revision = ?",
            (schema.name, mutation.id, mutation.expected_revision),
        )
        if cursor.rowcount == 0:
            row = conn.execute(
                "SELECT revision FROM records WHERE collection = ? AND record_id = ?",
                (schema.name, mutation.id),
            ).fetchone()
            if row is None:
                raise not_found(f"no {schema.name} record {mutation.id}")
            raise conflict(
                f"{schema.name} record {mutation.id} changed since it was read "
                f"(expected revision {mutation.expected_revision}, current {row['revision']})",
                current_revision=row["revision"],
            )
        conn.execute(
            "DELETE FROM unique_keys WHERE collection = ? AND record_id = ?",
            (schema.name, mutation.id),
        )

    def counts(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT collection, COUNT(*) AS n FROM records GROUP BY collection"
            ).fetchall()
        return {row["collection"]: row["n"] for row in rows}


def _row_to_record(row: sqlite3.Row) -> Record:
    return Record(
        id=row["record_id"],
        collection=row["collection"],
        revision=row["revision"],
        values=json.loads(row["values_json"]),
        provenance=json.loads(row["provenance_json"]),
        created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        updated_at=datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
    )


class RecordService:
    """Opens and caches one store per App; the only way Core code reaches App data."""

    def __init__(self, apps_root: Path, policy: q.QueryPolicy = q.DEFAULT_POLICY) -> None:
        self._root = apps_root
        self._policy = policy
        self._stores: dict[str, AppRecordStore] = {}
        self._lock = threading.Lock()

    def store(self, app_id: str) -> AppRecordStore:
        with self._lock:
            store = self._stores.get(app_id)
            if store is None:
                store = AppRecordStore(self._root / app_id / "records.sqlite", app_id, self._policy)
                self._stores[app_id] = store
            return store

    def drop(self, app_id: str) -> None:
        """Close an App's store and forget it (its module is being removed)."""
        with self._lock:
            store = self._stores.pop(app_id, None)
        if store is not None:
            store.close()

    def close(self) -> None:
        with self._lock:
            for store in self._stores.values():
                store.close()
            self._stores.clear()
