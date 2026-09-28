"""Compile typed record queries to parameterized SQLite (Implementation Blueprint §8).

Only declared or system fields can appear, and a field name reaches SQL only after it matched the
strict identifier pattern and the collection schema; every value is a bound parameter. Page and
group limits are platform policy (Current Release Specification §8): 100 by default, at most
1,000, a continuation cursor, and unbounded requests are rejected rather than truncated.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alpha_contracts.records import (
    IDENTIFIER_PATTERN,
    AggregateQuery,
    AllOf,
    AnyOf,
    Bucket,
    Clause,
    CollectionSchema,
    FieldKind,
    FieldSpec,
    Filter,
    FilterOp,
    MetricFn,
    Not,
    RecordQuery,
    SortKey,
)

from alpha.capabilities.errors import invalid, limit
from alpha.data.values import normalize


@dataclass(frozen=True)
class QueryPolicy:
    page_default: int = 100
    page_max: int = 1_000
    groups_max: int = 1_000
    filter_max_depth: int = 4
    filter_max_clauses: int = 32
    in_max_values: int = 100
    text_match_max: int = 200
    max_offset: int = 1_000_000


DEFAULT_POLICY = QueryPolicy()
_IDENT = re.compile(IDENTIFIER_PATTERN)
_SYSTEM: dict[str, tuple[str, FieldKind]] = {
    "id": ("r.record_id", FieldKind.TEXT),
    "created_at": ("r.created_at", FieldKind.DATETIME),
    "updated_at": ("r.updated_at", FieldKind.DATETIME),
}
_ORDERABLE = {
    FieldKind.TEXT,
    FieldKind.NUMBER,
    FieldKind.INTEGER,
    FieldKind.DATE,
    FieldKind.DATETIME,
    FieldKind.CHOICE,
    FieldKind.BOOLEAN,
    FieldKind.REFERENCE,
    FieldKind.RELATION,
}


@dataclass(frozen=True)
class Resolved:
    name: str
    expr: str
    kind: FieldKind
    spec: FieldSpec


def resolve_field(schema: CollectionSchema, name: str) -> Resolved:
    if name in _SYSTEM:
        expr, kind = _SYSTEM[name]
        return Resolved(name, expr, kind, FieldSpec.model_construct(name=name, kind=kind))
    spec = schema.field(name)
    if spec is None or not _IDENT.match(name):
        raise invalid(
            f"{schema.name} has no field {name!r}",
            field=name,
            fields=sorted([f.name for f in schema.fields] + list(_SYSTEM)),
        )
    # `name` matched the identifier pattern and the declared schema, so it is safe as a literal
    # JSON path; the literal form lets SQLite use the declared expression indexes.
    return Resolved(name, f"json_extract(r.values_json, '$.{name}')", spec.kind, spec)


def _value(resolved: Resolved, value: Any) -> Any:
    if resolved.name == "id":
        if not isinstance(value, str):
            raise invalid("id must be a record id", field="id")
        return value
    normalized = normalize(resolved.spec, value, where="filter on ")
    if normalized is None:
        raise invalid(f"use is_null to match an empty {resolved.name}", field=resolved.name)
    return normalized


def compile_filter(
    schema: CollectionSchema, node: Filter | None, policy: QueryPolicy = DEFAULT_POLICY
) -> tuple[str, list[Any]]:
    if node is None:
        return "1", []
    counter = {"clauses": 0}
    return _compile(schema, node, 1, counter, policy)


def _compile(
    schema: CollectionSchema,
    node: Filter,
    depth: int,
    counter: dict[str, int],
    policy: QueryPolicy,
) -> tuple[str, list[Any]]:
    if depth > policy.filter_max_depth:
        raise limit(f"filters can nest at most {policy.filter_max_depth} levels")
    if isinstance(node, AllOf | AnyOf):
        parts = node.all if isinstance(node, AllOf) else node.any
        joiner = " AND " if isinstance(node, AllOf) else " OR "
        sqls: list[str] = []
        params: list[Any] = []
        for part in parts:
            sql, p = _compile(schema, part, depth + 1, counter, policy)
            sqls.append(sql)
            params += p
        return "(" + joiner.join(sqls) + ")", params
    if isinstance(node, Not):
        sql, params = _compile(schema, node.not_, depth + 1, counter, policy)
        return f"(NOT {sql})", params
    assert isinstance(node, Clause)
    counter["clauses"] += 1
    if counter["clauses"] > policy.filter_max_clauses:
        raise limit(f"a filter can have at most {policy.filter_max_clauses} conditions")
    field = resolve_field(schema, node.field)
    if field.kind is FieldKind.JSON:
        raise invalid(f"{field.name} holds free-form data and cannot be filtered", field=field.name)
    op = node.op
    expr = field.expr
    if op is FilterOp.IS_NULL:
        # A missing value means "is null": {"op": "is_null"} reads as true.
        wanted = True if node.value is None else node.value
        if not isinstance(wanted, bool):
            raise invalid("is_null takes true or false", field=field.name)
        return f"({expr} IS {'' if wanted else 'NOT '}NULL)", []
    if op in (FilterOp.EQ, FilterOp.NE):
        value = _value(field, node.value)
        return (f"({expr} = ?)" if op is FilterOp.EQ else f"({expr} IS NOT ?)"), [value]
    if op in (FilterOp.LT, FilterOp.LTE, FilterOp.GT, FilterOp.GTE):
        if field.kind in (
            FieldKind.BOOLEAN,
            FieldKind.CHOICE,
            FieldKind.REFERENCE,
            FieldKind.RELATION,
        ):
            raise invalid(f"{field.name} cannot be compared with {op.value}", field=field.name)
        symbol = {FilterOp.LT: "<", FilterOp.LTE: "<=", FilterOp.GT: ">", FilterOp.GTE: ">="}[op]
        return f"({expr} {symbol} ?)", [_value(field, node.value)]
    if op is FilterOp.IN:
        if not isinstance(node.value, list) or not node.value:
            raise invalid("in takes a non-empty list", field=field.name)
        if len(node.value) > policy.in_max_values:
            raise limit(f"in takes at most {policy.in_max_values} values", field=field.name)
        values = [_value(field, v) for v in node.value]
        return f"({expr} IN ({','.join('?' for _ in values)}))", values
    if op in (FilterOp.CONTAINS, FilterOp.STARTS_WITH):
        if field.kind is not FieldKind.TEXT or field.name == "id":
            raise invalid(f"{op.value} works on text fields only", field=field.name)
        text = node.value
        if not isinstance(text, str) or not 1 <= len(text) <= policy.text_match_max:
            raise invalid(
                f"{op.value} takes text of 1 to {policy.text_match_max} characters",
                field=field.name,
            )
        if op is FilterOp.CONTAINS:
            return f"(instr(lower({expr}), lower(?)) > 0)", [text]
        return f"(substr({expr}, 1, ?) = ?)", [len(text), text]
    raise invalid(f"unsupported filter operation {op}")  # pragma: no cover


def compile_order(schema: CollectionSchema, keys: list[SortKey]) -> str:
    parts: list[str] = []
    for key in keys:
        field = resolve_field(schema, key.field)
        if field.kind not in _ORDERABLE:
            raise invalid(f"{field.name} cannot be sorted", field=field.name)
        parts.append(f"{field.expr} {'DESC' if key.direction == 'desc' else 'ASC'}")
    if not keys:
        parts.append("r.created_at ASC")
    parts.append("r.record_id ASC")
    return ", ".join(parts)


def query_digest(query: RecordQuery) -> str:
    material = query.model_dump(mode="json", by_alias=True, exclude={"limit", "cursor"})
    raw = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def encode_cursor(query: RecordQuery, offset: int) -> str:
    raw = json.dumps({"q": query_digest(query), "o": offset}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(query: RecordQuery, policy: QueryPolicy = DEFAULT_POLICY) -> int:
    if query.cursor is None:
        return 0
    try:
        padded = query.cursor + "=" * (-len(query.cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        offset = int(data["o"])
        digest = str(data["q"])
    except Exception:
        raise invalid("the cursor is not one this service issued") from None
    if digest != query_digest(query):
        raise invalid("the cursor belongs to a different query")
    if not 0 <= offset <= policy.max_offset:
        raise invalid("the cursor is out of range")
    return offset


def check_page_limit(requested: int, policy: QueryPolicy = DEFAULT_POLICY) -> int:
    if requested > policy.page_max:
        raise limit(
            f"a page holds at most {policy.page_max} records; use the cursor for more",
            requested=requested,
            maximum=policy.page_max,
        )
    return requested


# ----- aggregation --------------------------------------------------------------------------


def bucket_value(value: Any, unit: str, tz: str, kind: str) -> str | None:
    """SQLite function alpha_bucket(value, unit, tz, kind): calendar bucket in a timezone."""
    if value is None:
        return None
    if kind == "datetime":
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        day = moment.astimezone(ZoneInfo(tz)).date()
    else:
        day = date.fromisoformat(str(value))
    if unit == "day":
        return day.isoformat()
    if unit == "week":
        return (day - timedelta(days=day.weekday())).isoformat()
    if unit == "month":
        return day.strftime("%Y-%m")
    return None


def check_timezone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise invalid(f"unknown timezone {name!r}") from None
    return name


def compile_aggregate(
    schema: CollectionSchema,
    query: AggregateQuery,
    default_timezone: str,
    policy: QueryPolicy = DEFAULT_POLICY,
) -> tuple[str, list[Any], list[str], list[str]]:
    """Return (sql, params, key names, metric names); the caller runs it on the App store."""
    if query.limit > policy.groups_max:
        raise limit(f"an aggregation returns at most {policy.groups_max} groups")
    where_sql, where_params = compile_filter(schema, query.where, policy)
    select: list[str] = []
    params: list[Any] = []
    keys: list[str] = []
    for index, group in enumerate(query.group_by):
        field = resolve_field(schema, group.field)
        if field.kind is FieldKind.JSON:
            raise invalid(f"{field.name} cannot be grouped", field=field.name)
        if group.bucket is None:
            select.append(f"{field.expr} AS k{index}")
            keys.append(field.name)
            continue
        if field.kind not in (FieldKind.DATE, FieldKind.DATETIME):
            raise invalid(
                f"{group.bucket.value} buckets need a date or datetime field", field=field.name
            )
        tz = check_timezone(group.timezone or default_timezone)
        select.append(f"alpha_bucket({field.expr}, ?, ?, ?) AS k{index}")
        params += [group.bucket.value, tz, field.kind.value]
        keys.append(f"{field.name}_{Bucket(group.bucket).value}")
    metrics: list[str] = []
    for metric in query.metrics:
        if metric.fn is MetricFn.COUNT:
            select.append(f"COUNT(*) AS m_{metric.name}")
        else:
            assert metric.field is not None
            field = resolve_field(schema, metric.field)
            numeric = field.kind in (FieldKind.NUMBER, FieldKind.INTEGER)
            if metric.fn in (MetricFn.SUM, MetricFn.AVG) and not numeric:
                raise invalid(f"{metric.fn.value} needs a number field", field=field.name)
            if metric.fn in (MetricFn.MIN, MetricFn.MAX) and not (
                numeric or field.kind in (FieldKind.DATE, FieldKind.DATETIME)
            ):
                raise invalid(
                    f"{metric.fn.value} needs a number, date or datetime field", field=field.name
                )
            select.append(f"{metric.fn.value.upper()}({field.expr}) AS m_{metric.name}")
        metrics.append(metric.name)
    if len(set(keys) | set(metrics)) != len(keys) + len(metrics):
        raise invalid("group and metric names must be distinct")
    sql = f"SELECT {', '.join(select)} FROM records r WHERE r.collection = ? AND {where_sql}"
    params = params + [schema.name] + where_params
    if query.group_by:
        group_cols = ", ".join(f"k{i}" for i in range(len(query.group_by)))
        sql += f" GROUP BY {group_cols} ORDER BY {group_cols}"
    sql += " LIMIT ?"
    params.append(query.limit + 1)
    return sql, params, keys, metrics
