"""App source contract (`app.yaml`, Current Release Specification §3) and the sealed package index.

The source declares intent and code bindings. It cannot assign grants, secrets, resolved paths
or an active release; unknown fields are rejected. Core validates it, resolves the actual
handlers in a disposable worker and seals it into a Version.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from alpha_contracts.profiles import DependencyManifest, Sha256Hex
from alpha_contracts.records import (
    SYSTEM_FIELDS,
    AllOf,
    AnyOf,
    Clause,
    CollectionSchema,
    FieldKind,
    Filter,
    GroupKey,
    Metric,
    Not,
    SortKey,
)
from alpha_contracts.runs import ContractModel

APP_ID_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"
ACTION_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
HANDLER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"

# Capability families an App can declare in this release. Anything else is rejected rather than
# silently ignored; later tickets add families with their providers.
KNOWN_CAPABILITIES: frozenset[str] = frozenset({"records", "artifacts", "models"})


class EffectClass(StrEnum):
    NONE = "none"
    LOCAL_WRITE = "local_write"
    EXTERNAL_READ = "external_read"
    EXTERNAL_WRITE = "external_write"


class Invocable(StrEnum):
    ASSISTANT = "assistant"
    UI = "ui"
    MANUAL = "manual"
    TRIGGER = "trigger"


class RetryClass(StrEnum):
    PURE = "pure"
    IDEMPOTENT = "idempotent"
    REQUIRES_RECONCILIATION = "requires_reconciliation"


class ActionDefinition(ContractModel):
    id: str = Field(pattern=ACTION_ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    handler: str = Field(pattern=HANDLER_PATTERN, max_length=200)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    capability_requirements: list[str] = Field(default_factory=list, max_length=8)
    effect_class: EffectClass = EffectClass.NONE
    invocable_from: list[Invocable] = Field(min_length=1)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_class: RetryClass = RetryClass.PURE

    @model_validator(mode="after")
    def _schemas_are_objects(self) -> ActionDefinition:
        for label, schema in (
            ("input_schema", self.input_schema),
            ("output_schema", self.output_schema),
        ):
            if schema.get("type") != "object":
                raise ValueError(f"{label} of action {self.id!r} must describe an object")
            required = schema.get("required", [])
            props = schema.get("properties", {})
            if not isinstance(required, list) or not isinstance(props, dict):
                raise ValueError(f"{label} of action {self.id!r} has malformed required/properties")
            missing = [name for name in required if name not in props]
            if missing:
                raise ValueError(f"{label} of action {self.id!r} requires undeclared {missing}")
        return self


class AppSource(ContractModel):
    contract_version: Literal["0.2"]
    app_id: str = Field(pattern=APP_ID_PATTERN)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    runtime_profile: str = Field(min_length=1, max_length=64)
    sdk_version: str = Field(min_length=1, max_length=32)
    modules: dict[str, str] = Field(default_factory=dict)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    collections: list[CollectionSchema] = Field(default_factory=list, max_length=32)
    actions: list[ActionDefinition] = Field(min_length=1, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=16)
    ui: UiDeclaration | None = None
    trigger_templates: list[dict[str, Any]] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def _consistent(self) -> AppSource:
        action_ids = [a.id for a in self.actions]
        if len(set(action_ids)) != len(action_ids):
            raise ValueError("action ids must be unique")
        names = [c.name for c in self.collections]
        if len(set(names)) != len(names):
            raise ValueError("collection names must be unique")
        declared = set(names)
        for collection in self.collections:
            for spec in collection.fields:
                if spec.kind is FieldKind.REFERENCE and spec.collection not in declared:
                    raise ValueError(
                        f"{collection.name}.{spec.name} references undeclared collection "
                        f"{spec.collection!r}"
                    )
        unknown = sorted(set(self.capabilities) - KNOWN_CAPABILITIES)
        if unknown:
            raise ValueError(f"unknown capability families {unknown}")
        for action in self.actions:
            extra = sorted(set(action.capability_requirements) - set(self.capabilities))
            if extra:
                raise ValueError(f"action {action.id!r} requires undeclared capabilities {extra}")
        if self.collections and "records" not in self.capabilities:
            raise ValueError("an App with collections must declare the records capability")
        if self.ui is not None:
            by_name = {c.name: c for c in self.collections}
            view_ids = [v.id for v in self.ui.views]
            if len(set(view_ids)) != len(view_ids):
                raise ValueError("ui view ids must be unique")
            for view in self.ui.views:
                target = by_name.get(view.collection)
                if target is None:
                    raise ValueError(
                        f"ui view {view.id} reads undeclared collection {view.collection}"
                    )
                known = {f.name for f in target.fields} | SYSTEM_FIELDS
                unknown = sorted(view.mentioned_fields() - known)
                if unknown:
                    raise ValueError(f"ui view {view.id} names unknown fields {unknown}")
            for action_id in self.ui.actions:
                ui_action = self.action(action_id)
                if ui_action is None:
                    raise ValueError(f"ui action {action_id} is not declared")
                if Invocable.UI not in ui_action.invocable_from:
                    raise ValueError(f"ui action {action_id} is not invocable from ui")
        return self

    def action(self, action_id: str) -> ActionDefinition | None:
        return next((a for a in self.actions if a.id == action_id), None)


VIEW_ID_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)?$"


class ViewKind(StrEnum):
    RECORDS = "records"
    AGGREGATE = "aggregate"


def filter_fields(node: Filter | None) -> set[str]:
    """Every field a filter mentions."""
    if node is None:
        return set()
    if isinstance(node, Clause):
        return {node.field}
    if isinstance(node, AllOf):
        return set().union(*(filter_fields(n) for n in node.all))
    if isinstance(node, AnyOf):
        return set().union(*(filter_fields(n) for n in node.any))
    assert isinstance(node, Not)
    return filter_fields(node.not_)


class ViewSpec(ContractModel):
    """A bounded read view the App's UI may query (App UI Bridge, records.query). The view fixes
    the collection, an optional base filter, the projection and limits; the UI can only narrow it
    with filters on `filterable` fields and sort on `sortable` fields."""

    id: str = Field(pattern=VIEW_ID_PATTERN, max_length=64)
    kind: ViewKind = ViewKind.RECORDS
    collection: str = Field(min_length=1, max_length=48)
    description: str = Field(default="", max_length=300)
    where: Filter | None = None
    fields: list[str] | None = Field(default=None, max_length=64)
    filterable: list[str] = Field(default_factory=list, max_length=32)
    sortable: list[str] = Field(default_factory=list, max_length=32)
    default_order: list[SortKey] = Field(default_factory=list, max_length=3)
    max_limit: int = Field(default=100, ge=1, le=1000)
    group_by: list[GroupKey] = Field(default_factory=list, max_length=3)
    metrics: list[Metric] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def _kind_shape(self) -> ViewSpec:
        if self.kind is ViewKind.AGGREGATE:
            if not self.metrics:
                raise ValueError(f"aggregate view {self.id} needs metrics")
            if self.fields or self.sortable or self.default_order:
                raise ValueError(f"aggregate view {self.id} cannot declare fields or sorting")
        elif self.group_by or self.metrics:
            raise ValueError(f"records view {self.id} cannot declare group_by or metrics")
        return self

    def mentioned_fields(self) -> set[str]:
        names = set(self.fields or []) | set(self.filterable) | set(self.sortable)
        names |= {k.field for k in self.default_order} | {g.field for g in self.group_by}
        names |= {m.field for m in self.metrics if m.field} | filter_fields(self.where)
        return names


class UiDeclaration(ContractModel):
    """What an App's custom UI may read and do. It carries no native privileges; the shell derives
    the bridge grant from it and Core enforces the views."""

    entry: str | None = Field(default=None, max_length=200)
    kit_version: str | None = Field(default=None, max_length=32)
    bridge_version: str | None = Field(default=None, max_length=32)
    views: list[ViewSpec] = Field(default_factory=list, max_length=32)
    actions: list[str] = Field(default_factory=list, max_length=50)

    def view(self, view_id: str) -> ViewSpec | None:
        return next((v for v in self.views if v.id == view_id), None)


class PackageFile(ContractModel):
    path: str = Field(min_length=1, max_length=300)
    sha256: Sha256Hex
    size: int = Field(ge=0)


class PackageIndex(ContractModel):
    """package.index.json: platform-produced digests of every sealed file plus the identities
    the Version was validated against. `package_sha256` is the canonical digest of the rest."""

    contract_version: Literal["0.2"] = "0.2"
    app_id: str
    files: list[PackageFile]
    dependency_manifest_sha256: Sha256Hex
    toolchain: dict[str, str]
    package_sha256: Sha256Hex


class SealedVersion(ContractModel):
    version_id: str
    app_id: str
    package_sha256: Sha256Hex
    dependency_manifest: DependencyManifest
    dependency_manifest_sha256: Sha256Hex


AppSource.model_rebuild()
