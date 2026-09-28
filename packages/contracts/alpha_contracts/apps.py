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
from alpha_contracts.screens import (
    BoardBlock,
    FormBlock,
    ListBlock,
    MetricsBlock,
    ProgressBlock,
    QuickEntryBlock,
    ScreenDeclaration,
    SummaryBlock,
    Tab,
    TableBlock,
    TrendBlock,
)

APP_ID_PATTERN = r"^[a-z][a-z0-9_-]{2,63}$"
ACTION_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
HANDLER_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"

# Capability families an App can declare in this release. Anything else is rejected rather than
# silently ignored; later tickets add families with their providers.
KNOWN_CAPABILITIES: frozenset[str] = frozenset(
    {"records", "artifacts", "models", "http", "schedules", "browser", "profile"}
)


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


SCHEDULE_ID_PATTERN = r"^[a-z][a-z0-9_]{0,47}$"
TIME_OF_DAY_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class ScheduleSpec(ContractModel):
    """A local schedule: while Alpha is running, run `action` with `input` every N minutes or
    once a day at a local time. Missed occurrences are never caught up."""

    id: str = Field(pattern=SCHEDULE_ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    action: str = Field(pattern=ACTION_ID_PATTERN)
    input: dict[str, Any] = Field(default_factory=dict)
    every_minutes: int | None = Field(default=None, ge=5, le=10_080)
    daily_at: str | None = Field(default=None, pattern=TIME_OF_DAY_PATTERN)
    enabled: bool = True

    @model_validator(mode="after")
    def _one_rule(self) -> ScheduleSpec:
        if (self.every_minutes is None) == (self.daily_at is None):
            raise ValueError(f"schedule {self.id!r} needs exactly one of every_minutes or daily_at")
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
    # Declared read views shared by the declarative screen and any custom ui.
    views: list[ViewSpec] = Field(default_factory=list, max_length=32)
    # The declarative screen Alpha's shell draws (no compile step). See alpha_contracts.screens.
    # Optional: every collection already gets a derived page; a screen adds tabs beyond them.
    screen: ScreenDeclaration | None = None
    # Summary cards drawn above the derived pages: metric cards, a progress bar, a trend.
    summary: list[SummaryBlock] = Field(default_factory=list, max_length=8)
    ui: UiDeclaration | None = None
    # The one action a person runs to get this App's result. Required (by verification) for an
    # App without its own screen, so Alpha can offer one clear form instead of every internal
    # step (M1 review finding F03).
    primary_action: str | None = Field(default=None, max_length=64)
    trigger_templates: list[dict[str, Any]] = Field(default_factory=list, max_length=8)
    # Local schedules Alpha runs while it is open (the schedules capability).
    schedules: list[ScheduleSpec] = Field(default_factory=list, max_length=8)

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
        schedule_ids = [s.id for s in self.schedules]
        if len(set(schedule_ids)) != len(schedule_ids):
            raise ValueError("schedule ids must be unique")
        if self.schedules and "schedules" not in self.capabilities:
            raise ValueError("an App with schedules must declare the schedules capability")
        for schedule in self.schedules:
            scheduled = self.action(schedule.action)
            if scheduled is None:
                raise ValueError(
                    f"schedule {schedule.id!r} runs undeclared action {schedule.action!r}"
                )
            if Invocable.TRIGGER not in scheduled.invocable_from:
                raise ValueError(
                    f"schedule {schedule.id!r} runs {schedule.action!r}, which does not list "
                    "trigger in invocable_from"
                )
        if self.primary_action is not None:
            primary = self.action(self.primary_action)
            if primary is None:
                raise ValueError(f"primary_action {self.primary_action!r} is not declared")
            if Invocable.MANUAL not in primary.invocable_from:
                raise ValueError("primary_action must list manual in invocable_from")
        by_name = {c.name: c for c in self.collections}
        all_views = list(self.views) + (list(self.ui.views) if self.ui is not None else [])
        all_ids = [v.id for v in all_views]
        if len(set(all_ids)) != len(all_ids):
            raise ValueError("view ids must be unique across views and ui.views")
        for view in self.views:
            target = by_name.get(view.collection)
            if target is None:
                raise ValueError(f"view {view.id} reads undeclared collection {view.collection}")
            known = {f.name for f in target.fields} | SYSTEM_FIELDS
            unknown = sorted(view.mentioned_fields() - known)
            if unknown:
                raise ValueError(f"view {view.id} names unknown fields {unknown}")
        if self.screen is not None:
            self._check_screen(self.screen, by_name)
        if self.summary:
            blocks: list[Any] = list(self.summary)
            summary_tab = Tab(id="summary", title="Summary", blocks=blocks)
            self._check_screen(ScreenDeclaration(tabs=[summary_tab]), by_name)
        for collection in self.collections:
            quick = collection.page.quick_entry if collection.page is not None else None
            if quick is not None:
                quick_action = self.action(quick.action)
                if quick_action is None:
                    raise ValueError(f"{collection.name} quick entry runs undeclared action")
                if Invocable.UI not in quick_action.invocable_from:
                    raise ValueError(
                        f"{collection.name} quick entry action is not invocable from ui"
                    )
                if quick.input not in quick_action.input_schema.get("properties", {}):
                    raise ValueError(f"{collection.name} quick entry names an unknown input")
        if self.ui is not None:
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
            if self.ui.entry is not None:
                if self.ui.entry != "ui/src/main.tsx":
                    raise ValueError("ui.entry must be ui/src/main.tsx")
                missing = [
                    name
                    for name in ("build_profile", "kit_version", "bridge_version")
                    if getattr(self.ui, name) is None
                ]
                if missing:
                    raise ValueError(f"a ui entry needs exact {missing}")
            for action_id in self.ui.actions:
                ui_action = self.action(action_id)
                if ui_action is None:
                    raise ValueError(f"ui action {action_id} is not declared")
                if Invocable.UI not in ui_action.invocable_from:
                    raise ValueError(f"ui action {action_id} is not invocable from ui")
        return self

    def action(self, action_id: str) -> ActionDefinition | None:
        return next((a for a in self.actions if a.id == action_id), None)

    def view(self, view_id: str) -> ViewSpec | None:
        found = next((v for v in self.views if v.id == view_id), None)
        if found is None and self.ui is not None:
            found = self.ui.view(view_id)
        return found

    def has_screen(self) -> bool:
        """True when the shell can draw this App: derived pages for its collections, a
        declarative screen, or a custom ui entry."""
        return (
            bool(self.collections)
            or self.screen is not None
            or (self.ui is not None and self.ui.entry is not None)
        )

    def _check_screen(self, screen: ScreenDeclaration, by_name: dict[str, Any]) -> None:
        def view_of(view_id: str, where: str) -> ViewSpec:
            found = self.view(view_id)
            if found is None:
                raise ValueError(f"{where} reads undeclared view {view_id!r}")
            return found

        def fields_of(view: ViewSpec) -> set[str]:
            collection = by_name[view.collection]
            names = {f.name for f in collection.fields} | SYSTEM_FIELDS
            if view.fields:
                names = set(view.fields) | SYSTEM_FIELDS
            return names

        def action_ok(action_id: str, where: str) -> ActionDefinition:
            found = self.action(action_id)
            if found is None:
                raise ValueError(f"{where} runs undeclared action {action_id!r}")
            if Invocable.UI not in found.invocable_from:
                raise ValueError(f"{where} runs {action_id!r}, which is not invocable from ui")
            return found

        def goal_ok(goal_from: Any, where: str) -> None:
            if goal_from is None:
                return
            goal_view = view_of(goal_from.view, where)
            if goal_view.kind is not ViewKind.RECORDS:
                raise ValueError(f"{where}: goal_from needs a records view")
            if goal_from.field not in fields_of(goal_view):
                raise ValueError(
                    f"{where}: goal_from field {goal_from.field!r} is not in view {goal_view.id}"
                )

        for tab in screen.tabs:
            for index, block in enumerate(tab.blocks):
                where = f"screen tab {tab.id} block {index + 1} ({block.kind})"
                if isinstance(block, QuickEntryBlock):
                    action = action_ok(block.action, where)
                    props = action.input_schema.get("properties", {})
                    if block.input not in props:
                        raise ValueError(f"{where}: {block.action} has no input {block.input!r}")
                elif isinstance(block, TableBlock):
                    view = view_of(block.view, where)
                    if view.kind is not ViewKind.RECORDS:
                        raise ValueError(f"{where}: a table needs a records view")
                    known = fields_of(view)
                    for column in block.columns:
                        if column.field not in known:
                            raise ValueError(
                                f"{where}: column {column.field!r} is not in view {view.id}"
                            )
                    for total in block.totals:
                        if total not in known:
                            raise ValueError(f"{where}: total {total!r} is not in view {view.id}")
                    for binding in (block.edit, block.delete, *block.row_actions):
                        if binding is not None:
                            action_ok(binding.action, where)
                    if block.detail is not None:
                        detail = block.detail
                        named = [*detail.fields, *detail.long_fields]
                        if detail.title_field:
                            named.append(detail.title_field)
                        for name in named:
                            if name not in known:
                                raise ValueError(
                                    f"{where}: detail field {name!r} is not in view {view.id}"
                                )
                        for binding in detail.actions:
                            action_ok(binding.action, where)
                            if binding.id_param is None:
                                raise ValueError(
                                    f"{where}: detail action {binding.action} needs id_param"
                                )
                    if block.edit is not None and block.edit.id_param is None:
                        raise ValueError(f"{where}: edit needs id_param")
                    if block.delete is not None and block.delete.id_param is None:
                        raise ValueError(f"{where}: delete needs id_param")
                elif isinstance(block, MetricsBlock):
                    for card in block.cards:
                        view = view_of(card.view, where)
                        if view.kind is not ViewKind.AGGREGATE:
                            raise ValueError(
                                f"{where}: metric {card.title!r} needs an aggregate view"
                            )
                        if card.metric not in {m.name for m in view.metrics}:
                            raise ValueError(
                                f"{where}: view {view.id} has no metric {card.metric!r}"
                            )
                        goal_ok(card.goal_from, where)
                elif isinstance(block, ProgressBlock):
                    view = view_of(block.view, where)
                    if view.kind is not ViewKind.AGGREGATE:
                        raise ValueError(f"{where}: a progress bar needs an aggregate view")
                    if block.metric not in {m.name for m in view.metrics}:
                        raise ValueError(f"{where}: view {view.id} has no metric {block.metric!r}")
                    if block.goal is None and block.goal_from is None:
                        raise ValueError(f"{where}: a progress bar needs a goal or goal_from")
                    goal_ok(block.goal_from, where)
                elif isinstance(block, TrendBlock):
                    view = view_of(block.view, where)
                    if view.kind is not ViewKind.AGGREGATE:
                        raise ValueError(f"{where}: a trend needs an aggregate view")
                    keys = set()
                    for group in view.group_by:
                        keys.add(
                            f"{group.field}_{group.bucket.value}" if group.bucket else group.field
                        )
                    if block.x not in keys:
                        raise ValueError(
                            f"{where}: x {block.x!r} is not a group key of {view.id} "
                            f"({sorted(keys)})"
                        )
                    if block.y not in {m.name for m in view.metrics}:
                        raise ValueError(f"{where}: y {block.y!r} is not a metric of {view.id}")
                    goal_ok(block.goal_from, where)
                elif isinstance(block, BoardBlock):
                    view = view_of(block.view, where)
                    known = fields_of(view)
                    for name in (block.group_field, block.title_field, *block.subtitle_fields):
                        if name not in known:
                            raise ValueError(f"{where}: field {name!r} is not in view {view.id}")
                    spec = next(
                        (f for f in by_name[view.collection].fields if f.name == block.group_field),
                        None,
                    )
                    if spec is None or spec.kind is not FieldKind.CHOICE:
                        raise ValueError(f"{where}: group_field must be a choice field")
                    extra = sorted(set(block.columns) - set(spec.choices or []))
                    if extra:
                        raise ValueError(
                            f"{where}: columns {extra} are not choices of {block.group_field}"
                        )
                    if block.move is not None:
                        action_ok(block.move.action, where)
                        if block.move.id_param is None or block.field_param is None:
                            raise ValueError(f"{where}: move needs id_param and field_param")
                    for binding in block.card_actions:
                        action_ok(binding.action, where)
                elif isinstance(block, ListBlock):
                    view = view_of(block.view, where)
                    known = fields_of(view)
                    for name in (block.title_field, *block.subtitle_fields):
                        if name not in known:
                            raise ValueError(f"{where}: field {name!r} is not in view {view.id}")
                    for binding in block.item_actions:
                        action_ok(binding.action, where)
                elif isinstance(block, FormBlock):
                    action_ok(block.action, where)
                    if block.prefill_view:
                        view_of(block.prefill_view, where)


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
    # The qualified UI build profile the entry is compiled against, and the exact kit and bridge
    # versions it expects (Current Release Specification §3). Required with an entry.
    build_profile: str | None = Field(default=None, max_length=64)
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
