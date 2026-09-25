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
from alpha_contracts.records import CollectionSchema, FieldKind
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
    ui: dict[str, Any] | None = None
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
        return self

    def action(self, action_id: str) -> ActionDefinition | None:
        return next((a for a in self.actions if a.id == action_id), None)


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
