"""Neutral entries fixture: dated entries with an optional amount and a review status."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from alpha_sdk import Context


def add_entry(
    ctx: Context,
    title: str,
    amount: float | None = None,
    kind: str = "note",
    noted_on: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "title": title.strip(),
        "kind": kind,
        "status": "new",
        "noted_on": noted_on or ctx.today().isoformat(),
    }
    if amount is not None:
        values["amount"] = amount
    if note:
        values["note"] = note
    record = ctx.records.create("entries", values)
    return {"id": record.id, "revision": record.revision}


def update_entry(
    ctx: Context, id: str, expected_revision: int, changes: dict[str, Any]
) -> dict[str, Any]:
    record = ctx.records.update("entries", id, expected_revision=expected_revision, changes=changes)
    return {"id": record.id, "revision": record.revision}


def set_status(
    ctx: Context, id: str, expected_revision: int, status: str, reason: str = ""
) -> dict[str, Any]:
    changes: dict[str, Any] = {"status": status, "reason": reason.strip() or None}
    record = ctx.records.update("entries", id, expected_revision=expected_revision, changes=changes)
    return {"revision": record.revision}


def remove_entry(ctx: Context, id: str, expected_revision: int) -> dict[str, Any]:
    ctx.records.delete("entries", id, expected_revision=expected_revision)
    return {}


def seed_examples(ctx: Context, days: int = 14) -> dict[str, Any]:
    kinds = ["note", "task", "idea"]
    created = 0
    with ctx.records.batch() as batch:
        for offset in range(days):
            if offset % 4 == 2:  # leave some days without entries
                continue
            day = (ctx.today() - timedelta(days=offset)).isoformat()
            for n in range(1 + offset % 2):
                batch.create(
                    "entries",
                    {
                        "title": f"Example entry {offset + 1}.{n + 1}",
                        "amount": float((offset * 7 + n * 3) % 20),
                        "kind": kinds[(offset + n) % 3],
                        "status": "new" if offset < 4 else ("kept" if offset % 2 else "dismissed"),
                        "noted_on": day,
                    },
                    idempotency_key=f"example-{day}-{n}",
                )
                created += 1
    return {"created": created}
