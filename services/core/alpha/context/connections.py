"""Connections between modules: one module reading another's views.

A module declares what it reads (`uses`: the module, its views, and why) and the person sees
each use on the module's Settings with a switch. Reads stay read-only and go through the
source module's declared views, so the same limits apply as for its own screen. Nothing is
copied: the source module keeps its data; the reader sees the current rows.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from alpha_contracts.apps import AppSource
from alpha_contracts.records import AnyOf, Clause, FieldKind, Filter, FilterOp, RecordQuery, SortKey

from alpha.capabilities.errors import OperationFailed, forbidden, not_found, unavailable
from alpha.data.views import ViewQueryRequest, resolve_view, run_view
from alpha.storage.control_store import ControlStore, utc_now

log = logging.getLogger("alpha.connections")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS module_connections (
    app_id TEXT NOT NULL,
    source_app_id TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    declared_at TEXT NOT NULL,
    PRIMARY KEY (app_id, source_app_id)
);
"""

PICK_LIMIT = 50


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


class ConnectionService:
    def __init__(
        self, store: ControlStore, registry: Any | None, records: Any, timezone: str
    ) -> None:
        self._store = store
        self._registry = registry
        self._records = records
        self._timezone = timezone
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)

    def bind(self, registry: Any) -> None:
        """The registry is built after the broker; it is bound here before any read."""
        self._registry = registry

    @property
    def registry(self) -> Any:
        if self._registry is None:
            raise unavailable("connections are not ready yet")
        return self._registry

    # ----- what a module declared ------------------------------------------------------------

    def sync(self, app_id: str, source: AppSource) -> None:
        """Keep the person's switches in step with what the module declares: a new use starts
        on (the person asked for the module that reads it), a dropped use disappears."""
        declared = {u.module for u in source.uses}
        with self._lock, self._store.transaction() as conn:
            rows = conn.execute(
                "SELECT source_app_id FROM module_connections WHERE app_id = ?", (app_id,)
            ).fetchall()
            known = {r["source_app_id"] for r in rows}
            for module in declared - known:
                conn.execute(
                    "INSERT INTO module_connections(app_id, source_app_id, enabled, declared_at)"
                    " VALUES (?,?,1,?)",
                    (app_id, module, _now()),
                )
            for module in known - declared:
                conn.execute(
                    "DELETE FROM module_connections WHERE app_id = ? AND source_app_id = ?",
                    (app_id, module),
                )

    def sync_all(self) -> None:
        for entry in self.registry.list_apps():
            if entry.get("state") != "active":
                continue
            try:
                self.sync(entry["app_id"], self.registry.current(entry["app_id"]).source)
            except OperationFailed:
                continue

    def declared(self, app_id: str) -> list[dict[str, Any]]:
        """Every use the module declared, with the switch and whether the source is installed."""
        source = self.registry.current(app_id).source
        enabled = {
            r["source_app_id"]: bool(r["enabled"])
            for r in self._store.query(
                "SELECT source_app_id, enabled FROM module_connections WHERE app_id = ?", (app_id,)
            )
        }
        out = []
        for use in source.uses:
            name, installed, views = use.module, False, []
            try:
                other = self.registry.current(use.module).source
                name, installed = other.name, True
                for view_id in use.views:
                    spec = other.view(view_id)
                    if spec is not None:
                        views.append(
                            {"id": spec.id, "collection": spec.collection, "kind": spec.kind.value}
                        )
            except OperationFailed:
                pass
            out.append(
                {
                    "module": use.module,
                    "name": name,
                    "purpose": use.purpose,
                    "views": views
                    or [{"id": v, "collection": None, "kind": None} for v in use.views],
                    "enabled": enabled.get(use.module, True),
                    "installed": installed,
                }
            )
        return out

    def set_enabled(self, app_id: str, module: str, enabled: bool) -> list[dict[str, Any]]:
        with self._lock, self._store.transaction() as conn:
            conn.execute(
                "INSERT INTO module_connections(app_id, source_app_id, enabled, declared_at)"
                " VALUES (?,?,?,?) ON CONFLICT(app_id, source_app_id)"
                " DO UPDATE SET enabled = excluded.enabled",
                (app_id, module, 1 if enabled else 0, _now()),
            )
        return self.declared(app_id)

    # ----- reading through a connection ----------------------------------------------------

    def _use(self, app_id: str, module: str) -> tuple[Any, AppSource]:
        """The declared, switched-on use of `module` by `app_id`, and the source module."""
        source = self.registry.current(app_id).source
        use = next((u for u in source.uses if u.module == module), None)
        if use is None:
            raise forbidden(f"{app_id} does not declare that it reads {module}", module=module)
        row = self._store.query(
            "SELECT enabled FROM module_connections WHERE app_id = ? AND source_app_id = ?",
            (app_id, module),
        )
        if row and not row[0]["enabled"]:
            raise forbidden(
                f"reading {module} is switched off in this module's Settings", module=module
            )
        try:
            other = self.registry.current(module).source
        except OperationFailed:
            raise not_found(f"the module {module} is not installed", module=module) from None
        return use, other

    def available(self, app_id: str) -> list[dict[str, Any]]:
        """What this module may read right now: for the SDK's `ctx.modules.list()`."""
        out = []
        try:
            declared = self.declared(app_id)
        except OperationFailed:
            return []
        for entry in declared:
            if not entry["enabled"] or not entry["installed"]:
                continue
            other = self.registry.current(entry["module"]).source
            views = []
            for view in entry["views"]:
                spec = other.view(view["id"])
                if spec is None:
                    continue
                collection = next((c for c in other.collections if c.name == spec.collection), None)
                fields = [f.name for f in collection.fields] if collection else []
                views.append(
                    {
                        "id": spec.id,
                        "collection": spec.collection,
                        "kind": spec.kind.value,
                        "fields": spec.fields or fields,
                    }
                )
            out.append(
                {
                    "module": entry["module"],
                    "name": entry["name"],
                    "purpose": entry["purpose"],
                    "views": views,
                }
            )
        return out

    def read(self, app_id: str, module: str, view_id: str, request: ViewQueryRequest) -> Any:
        use, other = self._use(app_id, module)
        if view_id not in use.views:
            raise forbidden(f"{app_id} did not declare view {view_id} of {module}", view=view_id)
        view = resolve_view(other, view_id)
        return run_view(self._records.store(module), view, request, self._timezone)

    def get(self, app_id: str, module: str, collection: str, record_id: str) -> Any:
        """One record of a connected module (for relation fields): the module must be declared
        under uses; the collection must be one a declared view reads."""
        use, other = self._use(app_id, module)
        readable = {v.collection for v in other.views if v.id in use.views}
        if collection not in readable:
            raise forbidden(f"{app_id} may not read {module}'s {collection}", collection=collection)
        return self._records.store(module).get(collection, record_id)

    def pick(
        self, app_id: str, module: str, collection: str, query: str = ""
    ) -> list[dict[str, Any]]:
        """Rows to choose a relation from: id and a title, matching `query` when given."""
        use, other = self._use(app_id, module)
        readable = {v.collection for v in other.views if v.id in use.views}
        if collection not in readable:
            raise forbidden(f"{app_id} may not read {module}'s {collection}", collection=collection)
        schema = next(c for c in other.collections if c.name == collection)
        title = schema.title_field or next(
            (f.name for f in schema.fields if f.kind is FieldKind.TEXT), None
        )
        where: Filter | None = None
        if query.strip() and title:
            where = AnyOf(any=[Clause(field=title, op=FilterOp.CONTAINS, value=query.strip())])
        page = self._records.store(module).query(
            RecordQuery(
                collection=collection,
                where=where,
                order_by=[SortKey(field="updated_at", direction="desc")],
                limit=PICK_LIMIT,
            )
        )
        return [
            {"id": r.id, "title": str(r.values.get(title) or r.id) if title else r.id}
            for r in page.records
        ]

    def title_field(self, module: str, collection: str) -> str | None:
        try:
            other = self.registry.current(module).source
        except OperationFailed:
            return None
        schema = next((c for c in other.collections if c.name == collection), None)
        if schema is None:
            return None
        return schema.title_field or next(
            (f.name for f in schema.fields if f.kind is FieldKind.TEXT), None
        )
