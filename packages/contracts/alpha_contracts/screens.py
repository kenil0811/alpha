"""Declarative screens (`app.yaml: screen`).

A screen is what Alpha's shell draws for a module without any compiled UI: tabs made of blocks
(quick entry, table, metrics, trend, board, list, form, text). Every block reads through a
declared view and writes through a declared action, so the shell renders it with the same
components for every module and Core enforces the same limits as for custom UI. A module may
still ship a custom `ui` entry when no block fits; the two can coexist.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from alpha_contracts.records import Filter
from alpha_contracts.runs import ContractModel

BLOCK_ID_PATTERN = r"^[a-z][a-z0-9_]{0,47}$"
Label = Annotated[str, Field(min_length=1, max_length=120)]


class ColumnFormat(StrEnum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    DATETIME = "datetime"
    PILL = "pill"
    LINK = "link"
    CHECK = "check"


class Column(ContractModel):
    field: str = Field(min_length=1, max_length=48)
    title: Label | None = None
    format: ColumnFormat | None = None
    unit: str | None = Field(default=None, max_length=16)
    editable: bool = False
    width: Literal["narrow", "normal", "wide"] | None = None


class ActionBinding(ContractModel):
    """Run `action` with the record id as `id_param`, plus `input` and what the block adds."""

    action: str = Field(min_length=1, max_length=64)
    id_param: str | None = Field(default=None, max_length=64)
    input: dict[str, Any] = Field(default_factory=dict)
    title: Label | None = None
    confirm: str | None = Field(default=None, max_length=200)


class SavedList(ContractModel):
    id: str = Field(pattern=BLOCK_ID_PATTERN)
    title: Label
    where: Filter | None = None


class QuickEntryBlock(ContractModel):
    kind: Literal["quick_entry"]
    action: str = Field(min_length=1, max_length=64)
    # The action input that receives what the person typed.
    input: str = Field(min_length=1, max_length=64)
    placeholder: str = Field(min_length=1, max_length=200)
    voice: bool = True
    extra: dict[str, Any] = Field(default_factory=dict)


class DetailSpec(ContractModel):
    """The record's own page, opened from a table row: every field of the view (or the ones
    listed), long text as readable paragraphs, and the actions that apply to one record."""

    title_field: str | None = Field(default=None, max_length=48)
    fields: list[str] = Field(default_factory=list, max_length=48)
    long_fields: list[str] = Field(default_factory=list, max_length=12)
    actions: list[ActionBinding] = Field(default_factory=list, max_length=8)


class TableBlock(ContractModel):
    kind: Literal["table"]
    view: str = Field(min_length=1, max_length=64)
    title: Label | None = None
    columns: list[Column] = Field(min_length=1, max_length=24)
    lists: list[SavedList] = Field(default_factory=list, max_length=12)
    # Click a row to open the record's page. Every table that tracks things should have one.
    detail: DetailSpec | None = None
    # Cell edits call this action as {id_param: id, <field>: value}.
    edit: ActionBinding | None = None
    delete: ActionBinding | None = None
    row_actions: list[ActionBinding] = Field(default_factory=list, max_length=6)
    totals: list[str] = Field(default_factory=list, max_length=8)
    empty: str | None = Field(default=None, max_length=200)
    page_size: int = Field(default=50, ge=5, le=200)


class GoalFrom(ContractModel):
    """A goal read from the first record of a records view (for goals the person sets)."""

    view: str = Field(min_length=1, max_length=64)
    field: str = Field(min_length=1, max_length=48)


class MetricCard(ContractModel):
    title: Label
    view: str = Field(min_length=1, max_length=64)
    metric: str = Field(min_length=1, max_length=48)
    unit: str | None = Field(default=None, max_length=16)
    goal: float | None = None
    goal_from: GoalFrom | None = None
    goal_label: str | None = Field(default=None, max_length=60)
    hint: str | None = Field(default=None, max_length=200)


class MetricsBlock(ContractModel):
    kind: Literal["metrics"]
    title: Label | None = None
    cards: list[MetricCard] = Field(min_length=1, max_length=6)


class TrendBlock(ContractModel):
    kind: Literal["trend"]
    title: Label
    view: str = Field(min_length=1, max_length=64)
    # The aggregate group key that becomes the x axis (a day bucket: "<field>_day") and the
    # metric name that becomes the y axis.
    x: str = Field(min_length=1, max_length=64)
    y: str = Field(min_length=1, max_length=48)
    unit: str | None = Field(default=None, max_length=16)
    goal: float | None = None
    goal_from: GoalFrom | None = None
    days: int = Field(default=14, ge=7, le=365)


class BoardBlock(ContractModel):
    kind: Literal["board"]
    view: str = Field(min_length=1, max_length=64)
    title: Label | None = None
    group_field: str = Field(min_length=1, max_length=48)
    columns: list[str] = Field(min_length=2, max_length=8)
    title_field: str = Field(min_length=1, max_length=48)
    subtitle_fields: list[str] = Field(default_factory=list, max_length=4)
    badge_field: str | None = Field(default=None, max_length=48)
    # Dragging a card to another column calls this action as {id_param: id, field_param: column}.
    move: ActionBinding | None = None
    field_param: str | None = Field(default=None, max_length=64)
    card_actions: list[ActionBinding] = Field(default_factory=list, max_length=4)


class ListBlock(ContractModel):
    kind: Literal["list"]
    view: str = Field(min_length=1, max_length=64)
    title: Label | None = None
    title_field: str = Field(min_length=1, max_length=48)
    subtitle_fields: list[str] = Field(default_factory=list, max_length=4)
    badge_field: str | None = Field(default=None, max_length=48)
    link_field: str | None = Field(default=None, max_length=48)
    item_actions: list[ActionBinding] = Field(default_factory=list, max_length=4)
    empty: str | None = Field(default=None, max_length=200)


class FormBlock(ContractModel):
    kind: Literal["form"]
    action: str = Field(min_length=1, max_length=64)
    title: Label | None = None
    description: str | None = Field(default=None, max_length=400)
    submit_label: Label | None = None
    # A records view whose first record prefills the form (for settings-like actions).
    prefill_view: str | None = Field(default=None, max_length=64)


class TextBlock(ContractModel):
    kind: Literal["text"]
    title: Label | None = None
    body: str = Field(min_length=1, max_length=4000)


class ProgressBlock(ContractModel):
    """One wide bar: a metric against a goal (calories eaten today out of the day's limit,
    applications sent out of a weekly target), with what is left or over in words."""

    kind: Literal["progress"]
    title: Label
    view: str = Field(min_length=1, max_length=64)
    metric: str = Field(min_length=1, max_length=48)
    unit: str | None = Field(default=None, max_length=16)
    goal: float | None = None
    goal_from: GoalFrom | None = None
    goal_label: str | None = Field(default=None, max_length=60)
    hint: str | None = Field(default=None, max_length=200)


# What may sit above the derived pages as the module's summary: numbers, not data entry.
SummaryBlock = Annotated[
    MetricsBlock | ProgressBlock | TrendBlock | TextBlock,
    Field(discriminator="kind"),
]

Block = Annotated[
    QuickEntryBlock
    | TableBlock
    | MetricsBlock
    | TrendBlock
    | BoardBlock
    | ListBlock
    | FormBlock
    | TextBlock
    | ProgressBlock,
    Field(discriminator="kind"),
]


class Tab(ContractModel):
    id: str = Field(pattern=BLOCK_ID_PATTERN)
    title: Label
    blocks: list[Block] = Field(min_length=1, max_length=12)


class ScreenDeclaration(ContractModel):
    icon: str | None = Field(default=None, max_length=8)
    tabs: list[Tab] = Field(min_length=1, max_length=8)
    # What the assistant should know when helping inside this module.
    assistant_hint: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _unique_tabs(self) -> ScreenDeclaration:
        ids = [t.id for t in self.tabs]
        if len(set(ids)) != len(ids):
            raise ValueError("screen tab ids must be unique")
        return self

    def views_used(self) -> set[str]:
        names: set[str] = set()
        for tab in self.tabs:
            for block in tab.blocks:
                if isinstance(block, (TableBlock, TrendBlock, BoardBlock, ListBlock)):
                    names.add(block.view)
                    if isinstance(block, TrendBlock) and block.goal_from:
                        names.add(block.goal_from.view)
                elif isinstance(block, MetricsBlock):
                    names |= {c.view for c in block.cards}
                    names |= {c.goal_from.view for c in block.cards if c.goal_from}
                elif isinstance(block, FormBlock) and block.prefill_view:
                    names.add(block.prefill_view)
        return names

    def actions_used(self) -> set[str]:
        names: set[str] = set()
        for tab in self.tabs:
            for block in tab.blocks:
                if isinstance(block, (QuickEntryBlock, FormBlock)):
                    names.add(block.action)
                elif isinstance(block, TableBlock):
                    names |= {b.action for b in (block.edit, block.delete, *block.row_actions) if b}
                elif isinstance(block, BoardBlock):
                    names |= {b.action for b in (block.move, *block.card_actions) if b}
                elif isinstance(block, ListBlock):
                    names |= {b.action for b in block.item_actions}
        return names
