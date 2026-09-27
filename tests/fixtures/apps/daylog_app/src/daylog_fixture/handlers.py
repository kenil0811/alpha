"""Neutral daily-log fixture for the declarative screen: dated entries with an amount, a category
and an optional model estimate when no amount was typed. Used to check the shell's quick entry,
editable table, saved lists, metrics, trend and board blocks against a real Core."""

from __future__ import annotations

import re
from typing import Any

from alpha_sdk import Context
from alpha_sdk.query import eq

COLLECTION = "entries"
CATEGORIES = ("morning", "midday", "evening", "other")
AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:units?|u)\b", re.IGNORECASE)


def _category(ctx: Context, given: str | None) -> str:
    if given in CATEGORIES:
        return given
    hour = ctx.local_now().hour
    return "morning" if hour < 11 else "midday" if hour < 16 else "evening"


def _entry(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "revision": record.revision,
        "when": record.get("when"),
        "title": record.get("title"),
        "amount": record.get("amount"),
        "category": record.get("category"),
    }


def _day_total(ctx: Context, day: str) -> float:
    rows = ctx.records.all(COLLECTION, where=eq("when", day))
    return float(sum(float(row.get("amount") or 0) for row in rows))


def quick_add(ctx: Context, text: str) -> dict[str, Any]:
    """One line like "long walk 120 units" or just "long walk": the amount is read from the text
    when present, otherwise estimated by the model, otherwise left unknown."""
    raw = text.strip()
    if not raw:
        raise ValueError("Type what to log.")
    match = AMOUNT_RE.search(raw)
    amount: float | None = None
    estimated: dict[str, Any] | None = None
    title = raw
    if match:
        amount = float(match.group(1))
        title = (raw[: match.start()] + raw[match.end() :]).strip(" ,-") or raw
    else:
        try:
            guess = ctx.models.structured(
                "Estimate a sensible amount in units for this entry. Answer with one number.",
                input={"entry": raw},
                fields={
                    "amount": {"kind": "number", "minimum": 0, "maximum": 100000, "required": True}
                },
            )
            amount = float(guess["amount"])
            estimated = {"amount": guess}
        except Exception:
            ctx.log("No model available; the amount is left unknown.")
    day = ctx.today().isoformat()
    values: dict[str, Any] = {
        "when": day,
        "at": ctx.local_now().strftime("%H:%M"),
        "title": title,
        "category": _category(ctx, None),
    }
    if amount is not None:
        values["amount"] = amount
    record = (
        ctx.records.create(COLLECTION, values, estimated=estimated)
        if estimated is not None
        else ctx.records.create(COLLECTION, values)
    )
    words = f"Logged “{title}”"
    if amount is None:
        words += " with the amount left blank"
    elif estimated is not None:
        words += f" with an estimated {amount:g} units"
    return {
        "id": record.id,
        "revision": record.revision,
        "day_total": _day_total(ctx, day),
        "message": words + ".",
    }


def add_entry(
    ctx: Context,
    title: str,
    amount: float | None = None,
    when: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "when": when or ctx.today().isoformat(),
        "at": ctx.local_now().strftime("%H:%M"),
        "title": title.strip(),
        "category": _category(ctx, category),
    }
    if amount is not None:
        values["amount"] = amount
    record = ctx.records.create(COLLECTION, values)
    return {"id": record.id, "revision": record.revision, "message": f"Added “{values['title']}”."}


def correct_entry(
    ctx: Context,
    entry: str,
    title: str | None = None,
    amount: float | None = None,
    when: str | None = None,
    at: str | None = None,
    category: str | None = None,
    delete: bool | None = None,
) -> dict[str, Any]:
    record = ctx.records.get(COLLECTION, entry)
    if delete:
        ctx.records.delete(COLLECTION, entry, expected_revision=record.revision)
        return {"id": entry, "revision": record.revision, "deleted": True, "message": "Removed."}
    changes: dict[str, Any] = {}
    if title is not None:
        changes["title"] = title.strip()
    if amount is not None:
        changes["amount"] = float(amount)
    if when:
        changes["when"] = when
    if at:
        changes["at"] = at
    if category in CATEGORIES:
        changes["category"] = category
    if not changes:
        return {
            "id": record.id,
            "revision": record.revision,
            "deleted": False,
            "message": "Nothing changed.",
        }
    updated = ctx.records.update(
        COLLECTION, entry, expected_revision=record.revision, changes=changes
    )
    return {"id": updated.id, "revision": updated.revision, "deleted": False, "message": "Saved."}


def set_goal(ctx: Context, daily_units: float, note: str | None = None) -> dict[str, Any]:
    existing = ctx.records.all("goals")
    values: dict[str, Any] = {"daily_units": float(daily_units)}
    if note:
        values["note"] = note
    if existing:
        first = existing[0]
        record = ctx.records.update(
            "goals", first.id, expected_revision=first.revision, changes=values
        )
    else:
        record = ctx.records.create("goals", values)
    return {
        "id": record.id,
        "revision": record.revision,
        "message": f"Goal set to {daily_units:g} units a day.",
    }


def check_in(ctx: Context, note: str | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {
        "when": ctx.today().isoformat(),
        "at": ctx.local_now().strftime("%H:%M"),
        "title": (note or "Check-in").strip(),
        "amount": 0,
        "category": _category(ctx, None),
    }
    record = ctx.records.create(COLLECTION, values)
    return {"id": record.id, "revision": record.revision, "message": "Checked in."}
