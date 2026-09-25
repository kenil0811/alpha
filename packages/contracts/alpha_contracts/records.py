"""Collection schemas, records, typed queries and aggregation (Current Release Specification §8).

Generated code never writes SQL. It declares collections with these field specs and talks to the
record service through the typed filter/sort/aggregate shapes below; Core validates every value
and compiles queries to parameterized statements. Page and group limits are platform policy
enforced by Core, so the contract only bounds shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import ConfigDict, Field, model_validator

from alpha_contracts.runs import ContractModel

IDENTIFIER_PATTERN = r"^[a-z][a-z0-9_]{0,47}$"
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]

# System fields every record has. They can be filtered/sorted but never declared or written.
SYSTEM_FIELDS: frozenset[str] = frozenset({"id", "created_at", "updated_at"})
RESERVED_FIELD_NAMES: frozenset[str] = SYSTEM_FIELDS | {"revision", "collection", "provenance"}


class FieldKind(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    CHOICE = "choice"
    REFERENCE = "reference"
    JSON = "json"


class FieldSpec(ContractModel):
    """One declared field. Bounds default to platform policy when omitted."""

    name: Identifier
    kind: FieldKind
    required: bool = False
    description: str = Field(default="", max_length=500)
    max_length: int | None = Field(default=None, ge=1, le=100_000)
    minimum: float | None = None
    maximum: float | None = None
    choices: list[Annotated[str, Field(min_length=1, max_length=200)]] | None = Field(
        default=None, max_length=200
    )
    collection: Identifier | None = None
    max_bytes: int | None = Field(default=None, ge=16, le=65_536)

    @model_validator(mode="after")
    def _consistent(self) -> FieldSpec:
        kind = self.kind
        if self.name in RESERVED_FIELD_NAMES:
            raise ValueError(f"field name {self.name!r} is reserved")
        if self.max_length is not None and kind is not FieldKind.TEXT:
            raise ValueError("max_length applies to text fields only")
        if (self.minimum is not None or self.maximum is not None) and kind not in (
            FieldKind.NUMBER,
            FieldKind.INTEGER,
        ):
            raise ValueError("minimum/maximum apply to number and integer fields only")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum is greater than maximum")
        if kind is FieldKind.CHOICE:
            if not self.choices:
                raise ValueError("a choice field needs at least one choice")
            if len(set(self.choices)) != len(self.choices):
                raise ValueError("choices must be unique")
        elif self.choices is not None:
            raise ValueError("choices apply to choice fields only")
        if kind is FieldKind.REFERENCE:
            if self.collection is None:
                raise ValueError("a reference field names its target collection")
        elif self.collection is not None:
            raise ValueError("collection applies to reference fields only")
        if self.max_bytes is not None and kind is not FieldKind.JSON:
            raise ValueError("max_bytes applies to json fields only")
        return self


class CollectionSchema(ContractModel):
    name: Identifier
    description: str = Field(default="", max_length=500)
    fields: list[FieldSpec] = Field(min_length=1, max_length=64)
    indexes: list[list[Identifier]] = Field(default_factory=list, max_length=8)
    unique: list[list[Identifier]] = Field(default_factory=list, max_length=4)

    @model_validator(mode="after")
    def _consistent(self) -> CollectionSchema:
        names = [f.name for f in self.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"collection {self.name!r} declares a field twice")
        known = set(names) | SYSTEM_FIELDS
        by_name = {f.name: f for f in self.fields}
        for group, label in ((self.indexes, "index"), (self.unique, "unique constraint")):
            for fields in group:
                if not 1 <= len(fields) <= 3:
                    raise ValueError(f"an {label} covers one to three fields")
                for name in fields:
                    if name not in known:
                        raise ValueError(f"{label} names unknown field {name!r}")
                    spec = by_name.get(name)
                    if spec is not None and spec.kind is FieldKind.JSON:
                        raise ValueError(f"json field {name!r} cannot be indexed or unique")
        return self

    def field(self, name: str) -> FieldSpec | None:
        return next((f for f in self.fields if f.name == name), None)


# ----- provenance and records ---------------------------------------------------------------


class FieldProvenance(ContractModel):
    """Where a field's current value came from when it was not typed by a person or computed by
    the App's own rules. Model output is always an estimate the person can correct."""

    source: Literal["model_estimate", "user_correction"]
    at: datetime
    call_id: str | None = None
    route: str | None = None
    model: str | None = None
    previous: dict[str, Any] | None = None


class Record(ContractModel):
    # Titled AppRecord in exported schemas so generated TypeScript never shadows Record<K, V>.
    model_config = ConfigDict(extra="forbid", frozen=True, title="AppRecord")

    contract_version: Literal["0.2"] = "0.2"
    id: str = Field(min_length=1)
    collection: Identifier
    revision: int = Field(ge=1)
    values: dict[str, Any]
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class RecordPage(ContractModel):
    records: list[Record]
    next_cursor: str | None = None


# ----- typed filter AST ---------------------------------------------------------------------


class FilterOp(StrEnum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    IS_NULL = "is_null"


class Clause(ContractModel):
    field: str = Field(min_length=1, max_length=48)
    op: FilterOp
    value: Any = None


# Structural sanity bound only; the platform's (configurable) query policy sets the real limit on
# conditions and nesting and reports it as limit_exceeded.
class AllOf(ContractModel):
    all: list[Filter] = Field(min_length=1, max_length=256)


class AnyOf(ContractModel):
    any: list[Filter] = Field(min_length=1, max_length=256)


class Not(ContractModel):
    not_: Filter = Field(alias="not")


Filter = Clause | AllOf | AnyOf | Not


class SortKey(ContractModel):
    field: str = Field(min_length=1, max_length=48)
    direction: Literal["asc", "desc"] = "asc"


class RecordQuery(ContractModel):
    collection: Identifier
    where: Filter | None = None
    order_by: list[SortKey] = Field(default_factory=list, max_length=3)
    limit: int = Field(default=100, ge=1)
    cursor: str | None = Field(default=None, max_length=512)
    fields: list[Identifier] | None = Field(default=None, max_length=64)


class Bucket(StrEnum):
    DAY = "day"
    WEEK = "week"
    MONTH = "month"


class GroupKey(ContractModel):
    field: str = Field(min_length=1, max_length=48)
    bucket: Bucket | None = None
    timezone: str | None = Field(default=None, max_length=64)


class MetricFn(StrEnum):
    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"


class Metric(ContractModel):
    name: Identifier
    fn: MetricFn
    field: str | None = Field(default=None, max_length=48)

    @model_validator(mode="after")
    def _field_needed(self) -> Metric:
        if self.fn is not MetricFn.COUNT and self.field is None:
            raise ValueError(f"{self.fn.value} needs a field")
        return self


class AggregateQuery(ContractModel):
    collection: Identifier
    where: Filter | None = None
    group_by: list[GroupKey] = Field(default_factory=list, max_length=3)
    metrics: list[Metric] = Field(min_length=1, max_length=8)
    limit: int = Field(default=100, ge=1)


class AggregateGroup(ContractModel):
    key: dict[str, Any]
    # Numbers for count/sum/avg; min/max of a date or datetime field is its ISO text.
    values: dict[str, float | int | str | None]


class AggregateResult(ContractModel):
    groups: list[AggregateGroup]
    truncated: bool = False


# ----- mutations ----------------------------------------------------------------------------


class CreateRecord(ContractModel):
    op: Literal["create"] = "create"
    collection: Identifier
    values: dict[str, Any]
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)
    estimated: dict[Identifier, str] = Field(default_factory=dict)


class UpdateRecord(ContractModel):
    op: Literal["update"] = "update"
    collection: Identifier
    id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    changes: dict[str, Any] = Field(min_length=1)
    estimated: dict[Identifier, str] = Field(default_factory=dict)


class CorrectRecord(ContractModel):
    """A person's correction of values (often model estimates). Kept distinct from App updates
    so provenance can say the person decided it (specification §8, user overrides)."""

    op: Literal["correct"] = "correct"
    collection: Identifier
    id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    changes: dict[str, Any] = Field(min_length=1)


class DeleteRecord(ContractModel):
    op: Literal["delete"] = "delete"
    collection: Identifier
    id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)


RecordMutation = Annotated[
    CreateRecord | UpdateRecord | CorrectRecord | DeleteRecord, Field(discriminator="op")
]


class RecordBatch(ContractModel):
    operations: list[RecordMutation] = Field(min_length=1, max_length=100)


class GetRecord(ContractModel):
    collection: Identifier
    id: str = Field(min_length=1, max_length=64)


AllOf.model_rebuild()
AnyOf.model_rebuild()
Not.model_rebuild()
RecordQuery.model_rebuild()
AggregateQuery.model_rebuild()
