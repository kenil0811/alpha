"""Trusted validation and normalization of record values against declared field specs.

Generated code cannot disable this (Domain and Persistence Model, integrity rules). Values are
normalized to one canonical form so comparisons and ordering in SQL are meaningful: datetimes
become fixed-width UTC strings, dates ISO dates, choices exact strings.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

from alpha_contracts.records import FieldKind, FieldSpec

from alpha.capabilities.errors import invalid

TEXT_DEFAULT_MAX = 2_000
JSON_DEFAULT_MAX_BYTES = 16_384
JSON_MAX_DEPTH = 8
NUMBER_ABS_MAX = 1e15
RECORD_ID_PATTERN = re.compile(r"^rec_[0-9a-f]{32}$")


def _depth(value: Any, level: int = 0) -> int:
    if isinstance(value, dict):
        return max([_depth(v, level + 1) for v in value.values()], default=level + 1)
    if isinstance(value, list):
        return max([_depth(v, level + 1) for v in value], default=level + 1)
    return level


def format_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def normalize(spec: FieldSpec, value: Any, *, where: str) -> Any:
    """Return the canonical stored form of `value` for `spec`, or raise invalid_input."""
    name = spec.name
    kind = spec.kind
    if value is None:
        return None
    if kind is FieldKind.TEXT:
        if not isinstance(value, str):
            raise invalid(f"{where}{name} must be text", field=name)
        limit = spec.max_length or TEXT_DEFAULT_MAX
        if len(value) > limit:
            raise invalid(f"{where}{name} is longer than {limit} characters", field=name)
        return value
    if kind in (FieldKind.NUMBER, FieldKind.INTEGER):
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise invalid(f"{where}{name} must be a number", field=name)
        if isinstance(value, float) and not math.isfinite(value):
            raise invalid(f"{where}{name} must be a finite number", field=name)
        if kind is FieldKind.INTEGER:
            if isinstance(value, float):
                if not value.is_integer():
                    raise invalid(f"{where}{name} must be a whole number", field=name)
                value = int(value)
        if abs(value) > NUMBER_ABS_MAX:
            raise invalid(f"{where}{name} is too large", field=name)
        if spec.minimum is not None and value < spec.minimum:
            raise invalid(f"{where}{name} must be at least {spec.minimum:g}", field=name)
        if spec.maximum is not None and value > spec.maximum:
            raise invalid(f"{where}{name} must be at most {spec.maximum:g}", field=name)
        return value
    if kind is FieldKind.BOOLEAN:
        if not isinstance(value, bool):
            raise invalid(f"{where}{name} must be true or false", field=name)
        return value
    if kind is FieldKind.DATE:
        if not isinstance(value, str) or len(value) != 10:
            raise invalid(f"{where}{name} must be a date like 2026-09-25", field=name)
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            raise invalid(f"{where}{name} must be a date like 2026-09-25", field=name) from None
    if kind is FieldKind.DATETIME:
        if not isinstance(value, str) or len(value) > 40:
            raise invalid(f"{where}{name} must be a date and time with a timezone", field=name)
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise invalid(
                f"{where}{name} must be a date and time with a timezone", field=name
            ) from None
        if parsed.tzinfo is None:
            raise invalid(f"{where}{name} needs a timezone offset (for example Z)", field=name)
        return format_datetime(parsed)
    if kind is FieldKind.CHOICE:
        if not isinstance(value, str) or value not in (spec.choices or []):
            raise invalid(
                f"{where}{name} must be one of {spec.choices}", field=name, choices=spec.choices
            )
        return value
    if kind is FieldKind.REFERENCE:
        if not isinstance(value, str) or not RECORD_ID_PATTERN.match(value):
            raise invalid(f"{where}{name} must be a record id", field=name)
        return value
    if kind is FieldKind.JSON:
        try:
            encoded = json.dumps(value, allow_nan=False, sort_keys=True)
        except (TypeError, ValueError):
            raise invalid(f"{where}{name} must be plain JSON data", field=name) from None
        limit = spec.max_bytes or JSON_DEFAULT_MAX_BYTES
        if len(encoded.encode("utf-8")) > limit:
            raise invalid(f"{where}{name} is larger than {limit} bytes", field=name)
        if _depth(value) > JSON_MAX_DEPTH:
            raise invalid(f"{where}{name} is nested too deeply", field=name)
        return json.loads(encoded)
    raise invalid(f"{where}{name} has an unsupported kind {kind}", field=name)  # pragma: no cover


def validate_values(
    fields: Iterable[FieldSpec],
    values: Mapping[str, Any],
    *,
    partial: bool,
    collection: str,
) -> dict[str, Any]:
    """Validate a full value set (create) or a set of changes (update/correct)."""
    specs = {f.name: f for f in fields}
    unknown = sorted(set(values) - set(specs))
    if unknown:
        raise invalid(
            f"{collection} has no field(s) {unknown}; declared fields are {sorted(specs)}",
            unknown=unknown,
        )
    out: dict[str, Any] = {}
    for name, value in values.items():
        spec = specs[name]
        normalized = normalize(spec, value, where=f"{collection}.")
        if normalized is None and spec.required:
            raise invalid(f"{collection}.{name} is required", field=name)
        out[name] = normalized
    if not partial:
        missing = sorted(n for n, s in specs.items() if s.required and out.get(n) is None)
        if missing:
            raise invalid(f"{collection} needs {missing}", missing=missing)
    return out


def fields_to_json_schema(fields: Iterable[FieldSpec]) -> dict[str, Any]:
    """JSON Schema for a model's structured output, derived from the same field specs."""
    properties: dict[str, Any] = {}
    required: list[str] = []
    for spec in fields:
        node: dict[str, Any]
        if spec.kind is FieldKind.TEXT:
            node = {"type": "string", "maxLength": spec.max_length or TEXT_DEFAULT_MAX}
        elif spec.kind in (FieldKind.NUMBER, FieldKind.INTEGER):
            node = {"type": "number" if spec.kind is FieldKind.NUMBER else "integer"}
            if spec.minimum is not None:
                node["minimum"] = spec.minimum
            if spec.maximum is not None:
                node["maximum"] = spec.maximum
        elif spec.kind is FieldKind.BOOLEAN:
            node = {"type": "boolean"}
        elif spec.kind is FieldKind.DATE:
            node = {"type": "string", "format": "date"}
        elif spec.kind is FieldKind.DATETIME:
            node = {"type": "string", "format": "date-time"}
        elif spec.kind is FieldKind.CHOICE:
            node = {"type": "string", "enum": list(spec.choices or [])}
        elif spec.kind is FieldKind.JSON:
            # A list or object the instruction describes (one entry per item in a batch); the
            # value is bounded by max_bytes and depth when it comes back.
            node = {"type": ["array", "object"]}
        else:
            raise invalid(f"model outputs cannot contain {spec.kind.value} fields", field=spec.name)
        if spec.description:
            node["description"] = spec.description
        properties[spec.name] = node
        if spec.required:
            required.append(spec.name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
