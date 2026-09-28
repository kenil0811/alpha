"""ctx.modules: read what other modules keep, through the connections this App declared (the
`connections` capability).

    for use in ctx.modules.available():        # what this App may read right now
        use["module"], use["name"], use["views"]   # each view: id, collection, kind, fields
    rows = ctx.modules.query("academics", "courses.all", limit=50)
    rows[0].values["title"]
    course = ctx.modules.get("academics", "courses", "rec_…")   # a related record by id

Declare each module under `uses:` in app.yaml (its id, the views you read, and why, in the
person's words) and list `connections` in capabilities. Reads are read-only and go through the
other module's declared views. The person can switch any use off in Settings; then `query`
raises Forbidden, and the App says so rather than guessing.
"""

from __future__ import annotations

from typing import Any

from alpha_sdk._channel import Transport
from alpha_sdk.query import Filter, order_to_list, where_to_dict
from alpha_sdk.records import Record


class Modules:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def available(self) -> list[dict[str, Any]]:
        data = self._t.call("modules.list", {})
        return list((data or {}).get("modules", []))

    def query(
        self,
        module: str,
        view: str,
        *,
        where: Filter | dict[str, Any] | None = None,
        order_by: Any = None,
        limit: int = 100,
    ) -> list[Record]:
        body: dict[str, Any] = {"module": module, "view": view, "limit": limit}
        if where is not None:
            body["where"] = where_to_dict(where)
        if order_by is not None:
            body["order_by"] = order_to_list(order_by)
        data = self._t.call("modules.query", body)
        return [Record.from_wire(r) for r in (data or {}).get("records", [])]

    def get(self, module: str, collection: str, record_id: str) -> Record:
        data = self._t.call(
            "modules.get", {"module": module, "collection": collection, "id": record_id}
        )
        return Record.from_wire(data)
