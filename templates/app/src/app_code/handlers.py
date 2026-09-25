"""Action handlers. Each takes the Context first, then the action's declared inputs."""

from __future__ import annotations

from typing import Any

from alpha_sdk import Context


def add_item(ctx: Context, title: str) -> dict[str, Any]:
    record = ctx.records.create(
        "items", {"title": title.strip(), "noted_on": ctx.today().isoformat()}
    )
    return {"id": record.id, "revision": record.revision}
