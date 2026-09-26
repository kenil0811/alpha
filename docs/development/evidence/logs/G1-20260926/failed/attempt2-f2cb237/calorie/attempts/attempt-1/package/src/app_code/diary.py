"""Shared helpers for the diary: days, numbers, usual foods and day totals."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from alpha_sdk import Context
from alpha_sdk.query import eq, gte, lte

MEALS = ("breakfast", "lunch", "dinner", "snack")
MEAL_LABELS = {
    "breakfast": "Breakfast",
    "lunch": "Lunch",
    "dinner": "Dinner",
    "snack": "Snack",
}
UNITS = (
    "piece",
    "slice",
    "bowl",
    "plate",
    "cup",
    "glass",
    "serving",
    "gram",
    "millilitre",
    "tablespoon",
    "teaspoon",
)


class EntryRefused(ValueError):
    """Something the person typed cannot be saved; the run fails and says why."""


# --- text and numbers -------------------------------------------------------


def clean_text(value: Any, limit: int) -> str | None:
    """A trimmed string, or None when nothing was typed."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit]


def as_number(value: Any) -> float | None:
    """A number from whatever arrived, or None when there is no usable figure."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def round_calories(value: float) -> float:
    """Calorie figures are whole numbers; nobody counts half a calorie."""
    rounded = round(float(value))
    if rounded < 0:
        rounded = 0
    if rounded > 20000:
        rounded = 20000
    return float(rounded)


def normalise_name(text: Any) -> str:
    """Compare food names ignoring case, spacing and a trailing plural s."""
    words = str(text or "").casefold().split()
    return " ".join(words)


def meal_of(value: Any, default: str = "snack") -> str:
    meal = str(value or "").strip().casefold()
    return meal if meal in MEALS else default


def unit_of(value: Any) -> str | None:
    unit = str(value or "").strip().casefold()
    return unit if unit in UNITS else None


# --- days and times ---------------------------------------------------------


def local_tzinfo(ctx: Context) -> timezone:
    """The person's own offset, taken from the Context rather than the machine."""
    local = ctx.local_now()
    if local.tzinfo is not None and local.utcoffset() is not None:
        return timezone(local.utcoffset() or timedelta(0))
    utc = ctx.now()
    if utc.tzinfo is not None:
        utc = utc.replace(tzinfo=None)
    minutes = round((local - utc).total_seconds() / 60.0)
    return timezone(timedelta(minutes=minutes))


def local_now(ctx: Context) -> datetime:
    zone = local_tzinfo(ctx)
    local = ctx.local_now()
    if local.tzinfo is None:
        return local.replace(tzinfo=zone)
    return local.astimezone(zone)


def parse_day(ctx: Context, raw: Any) -> date:
    """A calendar day from a date, a datetime or nothing at all (then today)."""
    if raw is None:
        return local_now(ctx).date()
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    if not text:
        return local_now(ctx).date()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as error:
        raise EntryRefused(
            f"'{text}' is not a day I can read. Use a date like 2026-09-26."
        ) from error


def resolve_when(ctx: Context, raw: Any) -> tuple[str, str]:
    """Return (eaten_at, eaten_on): a full local timestamp and its calendar day.

    A day on its own keeps the current time of day, so entries stay in the order
    they were logged. Days run midnight to midnight in the person's timezone.
    """
    zone = local_tzinfo(ctx)
    now = local_now(ctx)
    if raw is None or not str(raw).strip():
        moment = now
    else:
        text = str(raw).strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        moment = None
        if len(text) <= 10:
            day = parse_day(ctx, text)
            moment = datetime.combine(day, now.timetz())
        else:
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError as error:
                raise EntryRefused(
                    f"'{text}' is not a time I can read. Use a date like 2026-09-26."
                ) from error
            moment = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=zone)
            moment = moment.astimezone(zone)
    return moment.isoformat(timespec="seconds"), moment.date().isoformat()


def period_days(raw: Any) -> tuple[int, str]:
    """Turn 'last 30 days' (or similar) into a number of days and a plain label."""
    text = str(raw or "").strip().casefold()
    if not text:
        return 30, "the last 30 days"
    digits = "".join(char if char.isdigit() else " " for char in text).split()
    number = int(digits[0]) if digits else None
    if number is not None and 1 <= number <= 730:
        if "week" in text:
            days = number * 7
            return days, f"the last {number} weeks"
        if "month" in text:
            days = number * 30
            return days, f"the last {number} months"
        return number, f"the last {number} days"
    if "week" in text:
        return 7, "the last 7 days"
    if "month" in text:
        return 30, "the last 30 days"
    if "year" in text:
        return 365, "the last year"
    return 30, "the last 30 days"


# --- records ----------------------------------------------------------------


def entries_on(ctx: Context, day: str) -> list[Any]:
    return list(
        ctx.records.all("food_entries", where=eq("eaten_on", day), order_by=["eaten_at"])
    )


def entries_between(ctx: Context, first: str, last: str) -> list[Any]:
    return list(
        ctx.records.all(
            "food_entries",
            where=gte("eaten_on", first) & lte("eaten_on", last),
            order_by=["eaten_at"],
        )
    )


def day_total(entries: list[Any]) -> float:
    total = 0.0
    for entry in entries:
        total += as_number(entry.get("calories")) or 0.0
    return round_calories(total)


def entry_view(record: Any) -> dict[str, Any]:
    """One entry in the person's words, for an action's answer."""
    calories = as_number(record.get("calories"))
    return {
        "id": record.id,
        "revision": record.revision,
        "eaten_at": record.get("eaten_at"),
        "date": record.get("eaten_on"),
        "food": record.get("food"),
        "amount": record.get("amount"),
        "meal": record.get("meal"),
        "calories": calories if calories is not None else 0.0,
        "calories_are_an_estimate": bool(record.get("calories_are_an_estimate")),
        "estimate_basis": record.get("estimate_basis"),
        "note": record.get("note"),
    }


def find_usual_food(ctx: Context, food: str) -> Any | None:
    """The saved usual food with this name, ignoring case and spacing."""
    wanted = normalise_name(food)
    if not wanted:
        return None
    for record in ctx.records.all("my_usual_foods"):
        if normalise_name(record.get("food")) == wanted:
            return record
    return None


def settings_record(ctx: Context) -> Any | None:
    records = list(ctx.records.all("my_settings", order_by=["created_at"]))
    return records[0] if records else None


def daily_target(ctx: Context) -> float | None:
    """The daily calorie target, or None while the person has not set one."""
    record = settings_record(ctx)
    if record is None:
        return None
    target = as_number(record.get("daily_calorie_target"))
    if target is None or target <= 0:
        return None
    return target


def group_by_meal(entries: list[Any]) -> list[dict[str, Any]]:
    """Entries grouped by meal, in the order the day is eaten."""
    groups: list[dict[str, Any]] = []
    for meal in MEALS:
        eaten = [entry for entry in entries if meal_of(entry.get("meal")) == meal]
        if not eaten:
            continue
        rows = [entry_view(entry) for entry in eaten]
        groups.append(
            {
                "meal": meal,
                "meal_label": MEAL_LABELS[meal],
                "total": day_total(eaten),
                "entry_count": len(rows),
                "entries": rows,
            }
        )
    return groups
