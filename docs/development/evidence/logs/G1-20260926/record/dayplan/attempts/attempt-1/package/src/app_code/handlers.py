"""Action handlers. Each takes the Context first, then the action's declared inputs."""

from __future__ import annotations

from typing import Any

from alpha_sdk import Context

from app_code.planning import (
    fit_items,
    hours_or_fail,
    read_items,
    say_duration,
    write_plan_text,
)


def read_list(
    ctx: Context, list: str, hours_available: float | None = None
) -> dict[str, Any]:
    hours = hours_or_fail(hours_available)
    items = read_items(list)
    if not items:
        raise ValueError("Paste your to-do list, one item per line, and run it again.")
    return {
        "items": items,
        "hours_available": hours,
        "available_minutes": int(round(hours * 60)),
        "total_minutes": sum(int(item["duration_minutes"]) for item in items),
    }


def fit_plan(
    ctx: Context, list: str, hours_available: float | None = None
) -> dict[str, Any]:
    hours = hours_or_fail(hours_available)
    items = read_items(list)
    if not items:
        raise ValueError("Paste your to-do list, one item per line, and run it again.")
    result = fit_items(items, hours)
    result["items"] = items
    result["hours_available"] = hours
    return result


def report_plan(
    ctx: Context,
    plan: list[dict[str, Any]],
    hours_available: float | None = None,
    wont_fit: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hours = hours_or_fail(hours_available)
    leftovers = wont_fit or []
    text = write_plan_text(plan or [], leftovers, hours)
    total = 0
    for item in plan or []:
        total += int(item["duration_minutes"])
    short_by = sum(int(item["duration_minutes"]) for item in leftovers)
    return {
        "plan_text": text,
        "total_minutes": total,
        "short_by_minutes": short_by,
        "summary": (
            f"{len(plan or [])} item(s) planned in {say_duration(total)}, "
            f"{len(leftovers)} won't fit today."
        ),
    }
