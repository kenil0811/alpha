"""Neutral fixture handlers: save a note, count notes."""

from __future__ import annotations

from typing import Any

from alpha_sdk import Context


def add_note(ctx: Context, title: str) -> dict[str, Any]:
    record = ctx.records.create(
        "notes", {"title": title.strip(), "noted_on": ctx.today().isoformat()}
    )
    return {"id": record.id, "revision": record.revision}


def count_notes(ctx: Context) -> dict[str, Any]:
    return {"count": len(ctx.records.all("notes"))}
