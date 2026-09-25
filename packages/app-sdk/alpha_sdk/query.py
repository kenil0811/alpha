"""Typed query builders. Generated code composes these; it never writes SQL.

    from alpha_sdk.query import gte, eq, all_of, total, count, by_day

    ctx.records.query("items", where=all_of(eq("category", "a"), gte("quantity", 2)),
                      order_by=["-noted_on", "title"], limit=50)
    ctx.records.aggregate("items", metrics={"n": count(), "qty": total("quantity")},
                          group_by=["category", by_day("happened_at")])

A plain mapping passed as `where` means "every field equals this value".
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Filter:
    node: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return self.node

    def __and__(self, other: Filter) -> Filter:
        return all_of(self, other)

    def __or__(self, other: Filter) -> Filter:
        return any_of(self, other)

    def __invert__(self) -> Filter:
        return not_(self)


def _clause(field: str, op: str, value: Any = None) -> Filter:
    return Filter({"field": field, "op": op, "value": value})


def eq(field: str, value: Any) -> Filter:
    return _clause(field, "eq", value)


def ne(field: str, value: Any) -> Filter:
    return _clause(field, "ne", value)


def lt(field: str, value: Any) -> Filter:
    return _clause(field, "lt", value)


def lte(field: str, value: Any) -> Filter:
    return _clause(field, "lte", value)


def gt(field: str, value: Any) -> Filter:
    return _clause(field, "gt", value)


def gte(field: str, value: Any) -> Filter:
    return _clause(field, "gte", value)


def one_of(field: str, values: Iterable[Any]) -> Filter:
    return _clause(field, "in", list(values))


def contains(field: str, text: str) -> Filter:
    """Case-insensitive substring match on a text field."""
    return _clause(field, "contains", text)


def starts_with(field: str, text: str) -> Filter:
    return _clause(field, "starts_with", text)


def is_empty(field: str) -> Filter:
    return _clause(field, "is_null", True)


def is_set(field: str) -> Filter:
    return _clause(field, "is_null", False)


def all_of(*filters: Filter) -> Filter:
    return Filter({"all": [f.to_dict() for f in filters]})


def any_of(*filters: Filter) -> Filter:
    return Filter({"any": [f.to_dict() for f in filters]})


def not_(inner: Filter) -> Filter:
    return Filter({"not": inner.to_dict()})


def where_to_dict(where: Filter | Mapping[str, Any] | None) -> dict[str, Any] | None:
    if where is None:
        return None
    if isinstance(where, Filter):
        return where.to_dict()
    if isinstance(where, Mapping):
        clauses = [eq(str(k), v) for k, v in where.items()]
        if not clauses:
            return None
        return clauses[0].to_dict() if len(clauses) == 1 else all_of(*clauses).to_dict()
    raise TypeError("where must be a Filter from alpha_sdk.query or a mapping of field -> value")


def order_to_list(order_by: Sequence[str] | str | None) -> list[dict[str, str]]:
    if order_by is None:
        return []
    items = [order_by] if isinstance(order_by, str) else list(order_by)
    keys: list[dict[str, str]] = []
    for item in items:
        name = str(item)
        if name.startswith("-"):
            keys.append({"field": name[1:], "direction": "desc"})
        else:
            keys.append({"field": name, "direction": "asc"})
    return keys


# ----- aggregation --------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricSpec:
    fn: str
    field: str | None = None


def count() -> MetricSpec:
    return MetricSpec("count")


def total(field: str) -> MetricSpec:
    return MetricSpec("sum", field)


def average(field: str) -> MetricSpec:
    return MetricSpec("avg", field)


def smallest(field: str) -> MetricSpec:
    return MetricSpec("min", field)


def largest(field: str) -> MetricSpec:
    return MetricSpec("max", field)


@dataclass(frozen=True)
class GroupSpec:
    field: str
    bucket: str | None = None
    timezone: str | None = None

    def to_dict(self) -> dict[str, Any]:
        node: dict[str, Any] = {"field": self.field}
        if self.bucket is not None:
            node["bucket"] = self.bucket
        if self.timezone is not None:
            node["timezone"] = self.timezone
        return node


def by_day(field: str, timezone: str | None = None) -> GroupSpec:
    """Group a date/datetime field by calendar day (in the run's timezone unless given)."""
    return GroupSpec(field, "day", timezone)


def by_week(field: str, timezone: str | None = None) -> GroupSpec:
    """Group by ISO week; the key is the Monday that starts the week."""
    return GroupSpec(field, "week", timezone)


def by_month(field: str, timezone: str | None = None) -> GroupSpec:
    return GroupSpec(field, "month", timezone)


def group_to_list(group_by: Sequence[str | GroupSpec] | None) -> list[dict[str, Any]]:
    if not group_by:
        return []
    return [g.to_dict() if isinstance(g, GroupSpec) else {"field": str(g)} for g in group_by]


def metrics_to_list(metrics: Mapping[str, MetricSpec]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, spec in metrics.items():
        if not isinstance(spec, MetricSpec):
            raise TypeError(f"metric {name!r} must come from count()/total()/average()/...")
        node: dict[str, Any] = {"name": name, "fn": spec.fn}
        if spec.field is not None:
            node["field"] = spec.field
        out.append(node)
    return out
