"""Declared read views for App UI (App UI Bridge `records.query`).

Core, not the frame or the shell, enforces a view: the UI may add filters only on the view's
`filterable` fields, sort only on `sortable` fields and page within `max_limit`; the view's own
base filter always applies (AND) and its projection limits the returned fields. Everything then
goes through the same typed query compiler and platform limits as worker queries.
"""

from __future__ import annotations

from alpha_contracts.apps import AppSource, ViewKind, ViewSpec, filter_fields
from alpha_contracts.records import (
    AggregateQuery,
    AggregateResult,
    AllOf,
    Filter,
    RecordPage,
    RecordQuery,
    SortKey,
)
from pydantic import BaseModel, ConfigDict, Field

from alpha.capabilities.errors import forbidden, limit, not_found
from alpha.data.store import AppRecordStore

DEFAULT_PAGE = 50


class ViewQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    where: Filter | None = None
    order_by: list[SortKey] = Field(default_factory=list, max_length=3)
    limit: int | None = Field(default=None, ge=1)
    cursor: str | None = Field(default=None, max_length=512)


def resolve_view(source: AppSource, view_id: str) -> ViewSpec:
    """A view declared at the top level (`views`) or under `ui.views`."""
    view = source.view(view_id)
    if view is None:
        raise not_found(f"this App has no view {view_id!r}", view=view_id)
    return view


def run_view(
    store: AppRecordStore, view: ViewSpec, request: ViewQueryRequest, timezone: str
) -> RecordPage | AggregateResult:
    outside = sorted(filter_fields(request.where) - set(view.filterable))
    if outside:
        raise forbidden(
            f"view {view.id} cannot be filtered by {outside}",
            filterable=view.filterable,
        )
    where: Filter | None
    if view.where is not None and request.where is not None:
        where = AllOf(all=[view.where, request.where])
    else:
        where = view.where or request.where
    if view.kind is ViewKind.AGGREGATE:
        if request.order_by or request.cursor:
            raise forbidden(f"aggregate view {view.id} has a fixed order and no pages")
        return store.aggregate(
            AggregateQuery(
                collection=view.collection,
                where=where,
                group_by=view.group_by,
                metrics=view.metrics,
                limit=view.max_limit,
            ),
            timezone,
        )
    unsortable = sorted({k.field for k in request.order_by} - set(view.sortable))
    if unsortable:
        raise forbidden(f"view {view.id} cannot be sorted by {unsortable}", sortable=view.sortable)
    page = request.limit or min(DEFAULT_PAGE, view.max_limit)
    if page > view.max_limit:
        raise limit(f"view {view.id} returns at most {view.max_limit} records per page")
    return store.query(
        RecordQuery(
            collection=view.collection,
            where=where,
            order_by=request.order_by or view.default_order,
            limit=page,
            cursor=request.cursor,
            fields=view.fields,
        )
    )
