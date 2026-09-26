"""Action handlers for the food log. Each takes the Context first, then its declared inputs."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from alpha_sdk import Context
from alpha_sdk.query import eq, gte

COLLECTION = "food_entries"
MEALS = ("breakfast", "lunch", "dinner", "snack")
ESTIMATE_LABEL = "Estimate from your description — type your own number to replace it"


def _tidy(value: Any, what: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{what} is needed.")
    return text


def _day(value: Any, ctx: Context) -> str:
    """The day as YYYY-MM-DD; today when nothing was given."""
    if value is None or str(value).strip() == "":
        return ctx.today().isoformat()
    text = str(value).strip().replace(" ", "T")
    day_part = text.split("T", 1)[0]
    try:
        date.fromisoformat(day_part)
    except ValueError:
        raise ValueError(f"'{value}' is not a day like 2026-01-31.")
    return day_part


def _clock(value: Any, ctx: Context) -> str:
    """Time of day as HH:MM, taken from a time, a datetime, or the clock now."""
    text = "" if value is None else str(value).strip().replace(" ", "T")
    if "T" in text:
        text = text.split("T", 1)[1]
    if len(text) >= 4 and ":" in text:
        hh, mm = text.split(":", 1)[0], text.split(":", 1)[1][:2]
        try:
            hours, minutes = int(hh), int(mm)
        except ValueError:
            hours, minutes = -1, -1
        if 0 <= hours < 24 and 0 <= minutes < 60:
            return f"{hours:02d}:{minutes:02d}"
    return ctx.local_now().strftime("%H:%M")


def _meal(value: Any) -> str | None:
    text = "" if value is None else str(value).strip().lower()
    return text if text in MEALS else None


def _number(value: float) -> float | int:
    number = float(value)
    return int(number) if number == int(number) else round(number, 1)


def _fallback_estimate(amount: str) -> int:
    """A plain guess used only when the model cannot be reached."""
    digits = "".join(ch if ch.isdigit() else " " for ch in amount).split()
    servings = int(digits[0]) if digits and int(digits[0]) <= 20 else 1
    return 200 * max(1, servings)


def _estimate(ctx: Context, food: str, amount: str) -> tuple[float, dict[str, Any] | None]:
    try:
        guess = ctx.models.structured(
            "Estimate the calories (kcal) in this food at this amount. Answer with one number.",
            input={"food": food, "amount": amount},
            fields={
                "calories": {"kind": "number", "minimum": 0, "maximum": 5000, "required": True}
            },
        )
        calories = float(guess["calories"])
    except Exception:  # the log still works without the model
        ctx.log("Could not reach the model; used a plain guess instead.")
        return float(_fallback_estimate(amount)), None
    return calories, guess


def _day_total(ctx: Context, day: str) -> float | int:
    rows = ctx.records.all(COLLECTION, where=eq("when", day))
    return _number(sum(float(row.get("calories") or 0) for row in rows))


def _entry(record: Any) -> dict[str, Any]:
    return {
        "id": record.id,
        "revision": record.revision,
        "when": record.get("when"),
        "eaten_at": record.get("eaten_at"),
        "food": record.get("food"),
        "amount": record.get("amount"),
        "calories": record.get("calories"),
        "calories_are_estimate": bool(record.get("calories_are_estimate")),
        "meal": record.get("meal"),
    }


def estimate_calories(ctx: Context, food: str, amount: str) -> dict[str, Any]:
    dish = _tidy(food, "Food")
    how_much = _tidy(amount, "Amount")
    calories, _ = _estimate(ctx, dish, how_much)
    return {
        "estimated_calories": _number(round(calories)),
        "estimate_label": ESTIMATE_LABEL,
        "food": dish,
        "amount": how_much,
    }


def log_entry(
    ctx: Context,
    food: str,
    amount: str,
    when: str | None = None,
    eaten_at: str | None = None,
    calories: float | None = None,
    meal: str | None = None,
) -> dict[str, Any]:
    dish = _tidy(food, "Food")
    how_much = _tidy(amount, "Amount")
    day = _day(when, ctx)
    time_of_day = _clock(eaten_at if eaten_at else when, ctx)

    estimated: dict[str, Any] | None = None
    if calories is None:
        number, guess = _estimate(ctx, dish, how_much)
        is_estimate = True
        if guess is not None:
            estimated = {"calories": guess}
    else:
        number = float(calories)
        if number < 0:
            raise ValueError("Calories cannot be less than zero.")
        is_estimate = False

    values: dict[str, Any] = {
        "when": day,
        "eaten_at": time_of_day,
        "food": dish,
        "amount": how_much,
        "calories": _number(number),
        "calories_are_estimate": is_estimate,
    }
    label = _meal(meal)
    if label is not None:
        values["meal"] = label

    if estimated is not None:
        record = ctx.records.create(COLLECTION, values, estimated=estimated)
    else:
        record = ctx.records.create(COLLECTION, values)

    return {
        "id": record.id,
        "revision": record.revision,
        "date": day,
        "day_total": _day_total(ctx, day),
        "calories_are_estimate": is_estimate,
        "entry": _entry(record),
    }


def correct_entry(
    ctx: Context,
    entry: str,
    food: str | None = None,
    amount: str | None = None,
    when: str | None = None,
    eaten_at: str | None = None,
    calories: float | None = None,
    meal: str | None = None,
    delete: bool | None = None,
) -> dict[str, Any]:
    record = ctx.records.get(COLLECTION, entry)
    old_day = str(record.get("when"))

    if delete:
        ctx.records.delete(COLLECTION, entry, expected_revision=record.revision)
        return {
            "id": entry,
            "revision": record.revision,
            "date": old_day,
            "day_total": _day_total(ctx, old_day),
            "deleted": True,
            "entry": None,
        }

    changes: dict[str, Any] = {}
    if food is not None:
        changes["food"] = _tidy(food, "Food")
    if amount is not None:
        changes["amount"] = _tidy(amount, "Amount")
    if when is not None and str(when).strip() != "":
        changes["when"] = _day(when, ctx)
    if (eaten_at is not None and str(eaten_at).strip() != "") or "T" in str(when or ""):
        changes["eaten_at"] = _clock(eaten_at if eaten_at else when, ctx)
    if meal is not None:
        changes["meal"] = _meal(meal)
    if calories is not None:
        number = float(calories)
        if number < 0:
            raise ValueError("Calories cannot be less than zero.")
        changes["calories"] = _number(number)
        changes["calories_are_estimate"] = False

    if not changes:
        return {
            "id": record.id,
            "revision": record.revision,
            "date": old_day,
            "day_total": _day_total(ctx, old_day),
            "deleted": False,
            "entry": _entry(record),
        }

    try:
        updated = ctx.records.correct(
            COLLECTION, entry, expected_revision=record.revision, changes=changes
        )
    except Exception:
        fresh = ctx.records.get(COLLECTION, entry)
        updated = ctx.records.update(
            COLLECTION, entry, expected_revision=fresh.revision, changes=changes
        )

    new_day = str(updated.get("when"))
    return {
        "id": updated.id,
        "revision": updated.revision,
        "date": new_day,
        "day_total": _day_total(ctx, new_day),
        "deleted": False,
        "entry": _entry(updated),
    }


def day_view(ctx: Context, date: str | None = None) -> dict[str, Any]:
    day = _day(date, ctx)
    rows = ctx.records.all(COLLECTION, where=eq("when", day))
    rows = sorted(rows, key=lambda row: (str(row.get("eaten_at") or "99:99"), str(row.created_at)))
    entries = [_entry(row) for row in rows]
    day_total = _number(sum(float(row.get("calories") or 0) for row in rows))
    return {
        "date": day,
        "entries": entries,
        "day_total": day_total,
        "entry_count": len(entries),
    }


def trends(ctx: Context, days: int | None = None) -> dict[str, Any]:
    span = int(days) if days else 7
    span = max(1, min(span, 366))
    last_day = ctx.today()
    first_day = last_day - timedelta(days=span - 1)

    rows = ctx.records.all(COLLECTION, where=gte("when", first_day.isoformat()))
    per_day: dict[str, float] = {}
    for row in rows:
        day = str(row.get("when"))
        if day > last_day.isoformat():
            continue
        per_day[day] = per_day.get(day, 0.0) + float(row.get("calories") or 0)

    daily_totals = []
    for step in range(span):
        day = (first_day + timedelta(days=step)).isoformat()
        logged = day in per_day
        daily_totals.append(
            {
                "date": day,
                "total": _number(per_day[day]) if logged else None,
                "logged": logged,
            }
        )

    grand_total = sum(per_day.values())
    return {
        "days": span,
        "daily_totals": daily_totals,
        "average_per_day": _number(round(grand_total / span, 1)),
        "total_calories": _number(grand_total),
        "days_logged": len(per_day),
    }
