"""ctx.records: the App's own collections, validated and stored by the platform.

Records belong to the App that is running; there is no way to name another App's store. Writes
carry the revision you read, so a stale update fails with Conflict instead of overwriting a
newer change. A batch commits every operation or none of them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from alpha_sdk._channel import Transport
from alpha_sdk.query import (
    Filter,
    GroupSpec,
    MetricSpec,
    group_to_list,
    metrics_to_list,
    order_to_list,
    where_to_dict,
)

if TYPE_CHECKING:
    from alpha_sdk.models import ModelResult


def _dt(value: Any) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


@dataclass(frozen=True)
class Record:
    id: str
    collection: str
    revision: int
    values: dict[str, Any]
    provenance: dict[str, dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_wire(cls, data: Mapping[str, Any]) -> Record:
        return cls(
            id=str(data["id"]),
            collection=str(data["collection"]),
            revision=int(data["revision"]),
            values=dict(data.get("values") or {}),
            provenance={k: dict(v) for k, v in (data.get("provenance") or {}).items()},
            created_at=_dt(data["created_at"]),
            updated_at=_dt(data["updated_at"]),
        )

    def __getitem__(self, name: str) -> Any:
        return self.values[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self.values.get(name, default)

    def is_estimate(self, name: str) -> bool:
        """True when the field's current value is a model estimate nobody has corrected."""
        return self.provenance.get(name, {}).get("source") == "model_estimate"

    def is_corrected(self, name: str) -> bool:
        return self.provenance.get(name, {}).get("source") == "user_correction"


@dataclass(frozen=True)
class Page:
    records: list[Record]
    next_cursor: str | None

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)


@dataclass(frozen=True)
class Group:
    key: dict[str, Any]
    values: dict[str, float | int | str | None]


@dataclass(frozen=True)
class Aggregation:
    groups: list[Group]
    truncated: bool

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.groups)


def _estimated(estimated: Mapping[str, ModelResult | str] | None) -> dict[str, str]:
    if not estimated:
        return {}
    out: dict[str, str] = {}
    for name, source in estimated.items():
        call_id = source if isinstance(source, str) else getattr(source, "call_id", None)
        if not isinstance(call_id, str):
            raise TypeError("estimated values must map a field to the ModelResult it came from")
        out[str(name)] = call_id
    return out


class Records:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def get(self, collection: str, record_id: str) -> Record:
        return Record.from_wire(
            self._t.call("records.get", {"collection": collection, "id": record_id})
        )

    def create(
        self,
        collection: str,
        values: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        estimated: Mapping[str, ModelResult | str] | None = None,
    ) -> Record:
        """Create a record. `estimated` marks fields whose values came from a model result so
        people see them as estimates they can correct."""
        args: dict[str, Any] = {"collection": collection, "values": dict(values)}
        if idempotency_key is not None:
            args["idempotency_key"] = idempotency_key
        marks = _estimated(estimated)
        if marks:
            args["estimated"] = marks
        return Record.from_wire(self._t.call("records.create", args))

    def update(
        self,
        collection: str,
        record_id: str,
        *,
        expected_revision: int,
        changes: Mapping[str, Any],
        estimated: Mapping[str, ModelResult | str] | None = None,
    ) -> Record:
        args: dict[str, Any] = {
            "collection": collection,
            "id": record_id,
            "expected_revision": expected_revision,
            "changes": dict(changes),
        }
        marks = _estimated(estimated)
        if marks:
            args["estimated"] = marks
        return Record.from_wire(self._t.call("records.update", args))

    def correct(
        self,
        collection: str,
        record_id: str,
        *,
        expected_revision: int,
        changes: Mapping[str, Any],
    ) -> Record:
        """Apply a person's correction (for example to a model estimate). Only allowed in runs a
        person started; the platform records it as their decision."""
        return Record.from_wire(
            self._t.call(
                "records.correct",
                {
                    "collection": collection,
                    "id": record_id,
                    "expected_revision": expected_revision,
                    "changes": dict(changes),
                },
            )
        )

    def delete(self, collection: str, record_id: str, *, expected_revision: int) -> None:
        self._t.call(
            "records.delete",
            {"collection": collection, "id": record_id, "expected_revision": expected_revision},
        )

    def query(
        self,
        collection: str,
        *,
        where: Filter | Mapping[str, Any] | None = None,
        order_by: Sequence[str] | str | None = None,
        limit: int = 100,
        cursor: str | None = None,
        fields: Sequence[str] | None = None,
    ) -> Page:
        args: dict[str, Any] = {"collection": collection, "limit": limit}
        where_node = where_to_dict(where)
        if where_node is not None:
            args["where"] = where_node
        order = order_to_list(order_by)
        if order:
            args["order_by"] = order
        if cursor is not None:
            args["cursor"] = cursor
        if fields is not None:
            args["fields"] = list(fields)
        data = self._t.call("records.query", args)
        return Page(
            records=[Record.from_wire(r) for r in data.get("records", [])],
            next_cursor=data.get("next_cursor"),
        )

    def all(
        self,
        collection: str,
        *,
        where: Filter | Mapping[str, Any] | None = None,
        order_by: Sequence[str] | str | None = None,
        page_size: int = 500,
        max_records: int = 10_000,
    ) -> list[Record]:
        """Read every matching record page by page, stopping at `max_records`."""
        out: list[Record] = []
        cursor: str | None = None
        while True:
            page = self.query(
                collection, where=where, order_by=order_by, limit=page_size, cursor=cursor
            )
            out.extend(page.records)
            if page.next_cursor is None or len(out) >= max_records:
                return out[:max_records]
            cursor = page.next_cursor

    def aggregate(
        self,
        collection: str,
        *,
        metrics: Mapping[str, MetricSpec],
        group_by: Sequence[str | GroupSpec] | None = None,
        where: Filter | Mapping[str, Any] | None = None,
        limit: int = 100,
    ) -> Aggregation:
        args: dict[str, Any] = {
            "collection": collection,
            "metrics": metrics_to_list(metrics),
            "group_by": group_to_list(group_by),
            "limit": limit,
        }
        where_node = where_to_dict(where)
        if where_node is not None:
            args["where"] = where_node
        data = self._t.call("records.aggregate", args)
        return Aggregation(
            groups=[Group(dict(g["key"]), dict(g["values"])) for g in data.get("groups", [])],
            truncated=bool(data.get("truncated")),
        )

    def batch(self) -> Batch:
        return Batch(self._t)


@dataclass
class Batch:
    """Collects writes and commits them together when the `with` block ends without an error.

    with ctx.records.batch() as batch:
        batch.create("items", {...})
        batch.update("items", rid, expected_revision=2, changes={...})
    results = batch.results   # records in operation order (None for deletes)
    """

    _t: Transport
    _operations: list[dict[str, Any]] = field(default_factory=list)
    results: list[Record | None] = field(default_factory=list)

    def create(
        self,
        collection: str,
        values: Mapping[str, Any],
        *,
        idempotency_key: str | None = None,
        estimated: Mapping[str, ModelResult | str] | None = None,
    ) -> None:
        op: dict[str, Any] = {"op": "create", "collection": collection, "values": dict(values)}
        if idempotency_key is not None:
            op["idempotency_key"] = idempotency_key
        marks = _estimated(estimated)
        if marks:
            op["estimated"] = marks
        self._operations.append(op)

    def update(
        self,
        collection: str,
        record_id: str,
        *,
        expected_revision: int,
        changes: Mapping[str, Any],
    ) -> None:
        self._operations.append(
            {
                "op": "update",
                "collection": collection,
                "id": record_id,
                "expected_revision": expected_revision,
                "changes": dict(changes),
            }
        )

    def delete(self, collection: str, record_id: str, *, expected_revision: int) -> None:
        self._operations.append(
            {
                "op": "delete",
                "collection": collection,
                "id": record_id,
                "expected_revision": expected_revision,
            }
        )

    def commit(self) -> list[Record | None]:
        if not self._operations:
            return []
        data = self._t.call("records.batch", {"operations": self._operations})
        self.results = [
            Record.from_wire(item) if isinstance(item, dict) else None
            for item in data.get("results", [])
        ]
        self._operations = []
        return self.results

    def __enter__(self) -> Batch:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is None:
            self.commit()
        else:
            self._operations = []
