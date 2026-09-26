"""Action handlers. Each takes the Context first, then the action's declared inputs."""

from __future__ import annotations

import csv
import io
from datetime import timedelta
from typing import Any

from alpha_sdk import Context

from . import calories as calorie_help
from . import diary
from .diary import (
    MEAL_LABELS,
    MEALS,
    EntryRefused,
    as_number,
    clean_text,
    day_total,
    entries_between,
    entries_on,
    entry_view,
    find_usual_food,
    group_by_meal,
    local_now,
    meal_of,
    normalise_name,
    parse_day,
    resolve_when,
    round_calories,
    unit_of,
)


def log_food(
    ctx: Context,
    food: str,
    amount: str,
    meal: str,
    eaten_at: str | None = None,
    calories: float | None = None,
    quantity: float | None = None,
    unit: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Save one thing I ate and give back the day's new total."""
    food_name = clean_text(food, 300)
    if not food_name:
        raise EntryRefused("Type what you ate before logging it.")
    amount_text = clean_text(amount, 120)
    if not amount_text:
        raise EntryRefused("Say how much you ate, for example '1 bowl' or '2 rotis'.")

    when, day = resolve_when(ctx, eaten_at)
    my_number = as_number(calories)
    usual = find_usual_food(ctx, food_name)

    basis: str | None = None
    estimated_by_model: Any | None = None
    from_usual = False

    if my_number is not None and my_number > 0:
        figure = round_calories(my_number)
        is_estimate = False
    elif usual is not None:
        figure = round_calories(as_number(usual.get("calories_per_portion")) or 0.0)
        is_estimate = False
        from_usual = True
    else:
        figure, basis, estimated_by_model = calorie_help.estimate(
            ctx, food_name, amount_text, as_number(quantity), unit_of(unit)
        )
        is_estimate = True

    values: dict[str, Any] = {
        "eaten_at": when,
        "eaten_on": day,
        "food": food_name,
        "amount": amount_text,
        "quantity": as_number(quantity),
        "unit": unit_of(unit),
        "meal": meal_of(meal, "snack"),
        "calories": figure,
        "calories_are_an_estimate": is_estimate,
        "estimate_basis": clean_text(basis, 240) if is_estimate else None,
        "note": clean_text(note, 500),
    }

    record = None
    if estimated_by_model is not None:
        try:
            record = ctx.records.create(
                "food_entries", values, estimated={"calories": estimated_by_model}
            )
        except Exception as error:  # keep the entry even if the label cannot be attached
            ctx.log("Saving without the model's own label", reason=str(error))
            record = None
    if record is None:
        record = ctx.records.create("food_entries", values)

    if from_usual and usual is not None:
        _bump_times_logged(ctx, usual)

    entries = entries_on(ctx, day)
    return {
        "id": record.id,
        "revision": record.revision,
        "food": food_name,
        "amount": amount_text,
        "meal": values["meal"],
        "eaten_at": when,
        "date": day,
        "calories": figure,
        "calories_are_an_estimate": is_estimate,
        "estimate_basis": values["estimate_basis"],
        "from_usual_food": from_usual,
        "day_total": day_total(entries),
        "day_entry_count": len(entries),
    }


def _bump_times_logged(ctx: Context, usual: Any) -> None:
    """Count one more use of a usual food; never worth failing the entry for."""
    times = (as_number(usual.get("times_logged")) or 0.0) + 1.0
    try:
        ctx.records.update(
            "my_usual_foods",
            usual.id,
            expected_revision=usual.revision,
            changes={"times_logged": times},
        )
    except Exception as error:
        ctx.log("Could not update how often this usual food is logged", reason=str(error))


def estimate_calories(
    ctx: Context,
    food: str,
    amount: str | None = None,
    quantity: float | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Estimate calories for a description, always as a figure I can overwrite."""
    food_name = clean_text(food, 300)
    if not food_name:
        raise EntryRefused("Type what you ate before asking for an estimate.")
    amount_text = clean_text(amount, 120)

    usual = find_usual_food(ctx, food_name)
    if usual is not None:
        figure = round_calories(as_number(usual.get("calories_per_portion")) or 0.0)
        return {
            "calories": figure,
            "basis": (
                f"one of your usual foods: {usual.get('portion')} "
                f"≈ {figure:.0f} kcal"
            ),
            "calories_are_an_estimate": False,
            "from_usual_food": True,
        }

    figure, basis, _model = calorie_help.estimate(
        ctx, food_name, amount_text, as_number(quantity), unit_of(unit)
    )
    return {
        "calories": figure,
        "basis": basis,
        "calories_are_an_estimate": True,
        "from_usual_food": False,
    }


def correct_entry(
    ctx: Context,
    entry_id: str,
    expected_revision: int | None = None,
    food: str | None = None,
    amount: str | None = None,
    meal: str | None = None,
    calories: float | None = None,
    note: str | None = None,
    remove: bool | None = None,
    save_as_usual_food: bool | None = None,
    portion: str | None = None,
) -> dict[str, Any]:
    """Change or remove one entry I already logged."""
    record = ctx.records.get("food_entries", entry_id)
    revision = expected_revision if expected_revision is not None else record.revision
    day = str(record.get("eaten_on") or local_now(ctx).date().isoformat())

    if remove:
        ctx.records.delete("food_entries", entry_id, expected_revision=revision)
        entries = entries_on(ctx, day)
        return {
            "entry_id": entry_id,
            "removed": True,
            "id": None,
            "revision": None,
            "food": record.get("food"),
            "amount": record.get("amount"),
            "meal": record.get("meal"),
            "calories": None,
            "calories_are_an_estimate": None,
            "date": day,
            "day_total": day_total(entries),
            "day_entry_count": len(entries),
            "usual_food": None,
            "can_save_as_usual_food": False,
        }

    changes: dict[str, Any] = {}
    new_food = clean_text(food, 300)
    if new_food and new_food != record.get("food"):
        changes["food"] = new_food
    new_amount = clean_text(amount, 120)
    if new_amount and new_amount != record.get("amount"):
        changes["amount"] = new_amount
    if meal is not None and str(meal).strip():
        chosen = meal_of(meal, str(record.get("meal") or "snack"))
        if chosen != record.get("meal"):
            changes["meal"] = chosen
    if note is not None:
        changes["note"] = clean_text(note, 500)

    my_number = as_number(calories)
    corrected_figure = my_number is not None and my_number >= 0
    if corrected_figure:
        changes["calories"] = round_calories(my_number or 0.0)
        changes["calories_are_an_estimate"] = False
        changes["estimate_basis"] = None

    if not changes:
        raise EntryRefused(
            "Nothing to change. Give a new food, amount, meal, calorie figure or note."
        )

    updated = _apply_changes(ctx, entry_id, revision, changes, corrected_figure)

    usual_food: dict[str, Any] | None = None
    if save_as_usual_food:
        usual_food = _remember_usual_food(
            ctx,
            food=str(updated.get("food") or ""),
            portion=clean_text(portion, 120) or str(updated.get("amount") or ""),
            calories=as_number(updated.get("calories")) or 0.0,
        )

    new_day = str(updated.get("eaten_on") or day)
    entries = entries_on(ctx, new_day)
    answer = entry_view(updated)
    return {
        "entry_id": entry_id,
        "removed": False,
        "id": updated.id,
        "revision": updated.revision,
        "food": answer["food"],
        "amount": answer["amount"],
        "meal": answer["meal"],
        "calories": answer["calories"],
        "calories_are_an_estimate": answer["calories_are_an_estimate"],
        "date": new_day,
        "day_total": day_total(entries),
        "day_entry_count": len(entries),
        "usual_food": usual_food,
        "can_save_as_usual_food": bool(
            not answer["calories_are_an_estimate"] and usual_food is None
        ),
    }


def _apply_changes(
    ctx: Context,
    entry_id: str,
    revision: int,
    changes: dict[str, Any],
    is_correction: bool,
) -> Any:
    """Record a correction of an estimate as such; otherwise a plain change."""
    if is_correction:
        try:
            return ctx.records.correct(
                "food_entries", entry_id, expected_revision=revision, changes=changes
            )
        except Exception as error:
            ctx.log("Saving the correction as a plain change", reason=str(error))
    return ctx.records.update(
        "food_entries", entry_id, expected_revision=revision, changes=changes
    )


def _remember_usual_food(
    ctx: Context, food: str, portion: str, calories: float
) -> dict[str, Any] | None:
    """Keep this figure as one of my usual foods, updating one already saved."""
    food_name = clean_text(food, 200)
    portion_text = clean_text(portion, 120) or "1 portion"
    figure = round_calories(calories)
    if not food_name or figure <= 0:
        return None
    existing = find_usual_food(ctx, food_name)
    if existing is not None:
        record = ctx.records.update(
            "my_usual_foods",
            existing.id,
            expected_revision=existing.revision,
            changes={"portion": portion_text, "calories_per_portion": figure},
        )
    else:
        record = ctx.records.create(
            "my_usual_foods",
            {
                "food": food_name,
                "portion": portion_text,
                "calories_per_portion": figure,
                "times_logged": 0.0,
            },
        )
    return {
        "id": record.id,
        "food": record.get("food"),
        "portion": record.get("portion"),
        "calories_per_portion": as_number(record.get("calories_per_portion")),
    }


def day_summary(
    ctx: Context, date: str | None = None, daily_calorie_target: float | None = None
) -> dict[str, Any]:
    """One day's entries grouped by meal, with the day's total."""
    day = parse_day(ctx, date)
    day_text = day.isoformat()
    entries = entries_on(ctx, day_text)
    total = day_total(entries)

    target = as_number(daily_calorie_target)
    if target is None or target <= 0:
        target = diary.daily_target(ctx)

    difference: float | None = None
    target_note: str | None = None
    if target is not None and target > 0:
        difference = round_calories(abs(total - target)) * (1 if total >= target else -1)
        if total > target:
            target_note = f"{total - target:.0f} kcal over your {target:.0f} kcal target"
        elif total < target:
            target_note = f"{target - total:.0f} kcal left of your {target:.0f} kcal target"
        else:
            target_note = f"exactly your {target:.0f} kcal target"

    return {
        "date": day_text,
        "day_total": total,
        "entry_count": len(entries),
        "estimated_entry_count": sum(
            1 for entry in entries if entry.get("calories_are_an_estimate")
        ),
        "has_target": target is not None,
        "daily_calorie_target": target,
        "difference_from_target": difference,
        "target_note": target_note,
        "meals": group_by_meal(entries),
    }


def trends(
    ctx: Context, period: str | None = None, save_summary_file: bool | None = None
) -> dict[str, Any]:
    """Daily totals, the 7-day rolling average and where my eating is heading."""
    days, period_label = diary.period_days(period)
    last_day = local_now(ctx).date()
    first_day = last_day - timedelta(days=days - 1)
    entries = entries_between(ctx, first_day.isoformat(), last_day.isoformat())

    totals: dict[str, float] = {}
    counts: dict[str, int] = {}
    for entry in entries:
        day = str(entry.get("eaten_on") or "")
        totals[day] = totals.get(day, 0.0) + (as_number(entry.get("calories")) or 0.0)
        counts[day] = counts.get(day, 0) + 1

    daily_totals: list[dict[str, Any]] = []
    ordered_days: list[str] = []
    for offset in range(days):
        day = (first_day + timedelta(days=offset)).isoformat()
        ordered_days.append(day)
        logged = day in totals
        daily_totals.append(
            {
                "date": day,
                "total": round_calories(totals[day]) if logged else None,
                "entry_count": counts.get(day, 0),
                "logged": logged,
            }
        )

    rolling: list[dict[str, Any]] = []
    for index, day in enumerate(ordered_days):
        window = ordered_days[max(0, index - 6) : index + 1]
        logged = [totals[each] for each in window if each in totals]
        rolling.append(
            {
                "date": day,
                "average": round_calories(sum(logged) / len(logged)) if logged else None,
            }
        )

    logged_days = [day for day in ordered_days if day in totals]
    average_daily = (
        round_calories(sum(totals[day] for day in logged_days) / len(logged_days))
        if logged_days
        else None
    )

    latest = next(
        (point["average"] for point in reversed(rolling) if point["average"] is not None),
        None,
    )
    earlier_points = rolling[:-7] if len(rolling) > 7 else []
    previous = next(
        (
            point["average"]
            for point in reversed(earlier_points)
            if point["average"] is not None
        ),
        None,
    )
    direction, direction_note, change = _direction(latest, previous, len(logged_days))

    meal_split: list[dict[str, Any]] = []
    grand_total = sum(totals.values())
    for meal in MEALS:
        eaten = [entry for entry in entries if meal_of(entry.get("meal")) == meal]
        if not eaten:
            continue
        meal_total = sum(as_number(entry.get("calories")) or 0.0 for entry in eaten)
        meal_split.append(
            {
                "meal": meal,
                "meal_label": MEAL_LABELS[meal],
                "total": round_calories(meal_total),
                "entry_count": len(eaten),
                "average_per_day_logged": (
                    round_calories(meal_total / len(logged_days)) if logged_days else None
                ),
                "share_percent": (
                    round(meal_total * 100.0 / grand_total, 1) if grand_total > 0 else None
                ),
            }
        )

    top_foods = _top_foods(entries)

    summary_file: dict[str, Any] | None = None
    if save_summary_file:
        summary_file = _write_summary(
            ctx,
            period_label,
            first_day.isoformat(),
            last_day.isoformat(),
            daily_totals,
            rolling,
            meal_split,
            top_foods,
            average_daily,
            direction_note,
        )

    return {
        "period": period_label,
        "from_date": first_day.isoformat(),
        "to_date": last_day.isoformat(),
        "day_count": days,
        "entry_count": len(entries),
        "days_logged": len(logged_days),
        "average_daily_calories": average_daily,
        "rolling_average_latest": latest,
        "rolling_average_previous": previous,
        "rolling_average_change": change,
        "direction": direction,
        "direction_note": direction_note,
        "daily_totals": daily_totals,
        "rolling_average": rolling,
        "meal_split": meal_split,
        "top_foods": top_foods,
        "summary_file": summary_file,
    }


def _direction(
    latest: float | None, previous: float | None, logged_days: int
) -> tuple[str, str, float | None]:
    if latest is None or logged_days < 3:
        return (
            "not enough logged yet",
            "Log a few more days and the direction will show here.",
            None,
        )
    if previous is None:
        return (
            "steady so far",
            f"Averaging {latest:.0f} kcal a day; there is not a week to compare with yet.",
            None,
        )
    change = round(latest - previous, 1)
    threshold = max(25.0, previous * 0.03)
    if change > threshold:
        return "rising", f"Up {change:.0f} kcal a day on the week before.", change
    if change < -threshold:
        return "falling", f"Down {abs(change):.0f} kcal a day on the week before.", change
    return "steady", "About the same as the week before.", change


def _top_foods(entries: list[Any]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = str(entry.get("food") or "").strip()
        key = normalise_name(name)
        if not key:
            continue
        row = seen.setdefault(key, {"food": name, "times": 0, "total": 0.0})
        row["times"] = int(row["times"]) + 1
        row["total"] = float(row["total"]) + (as_number(entry.get("calories")) or 0.0)
    ranked = sorted(seen.values(), key=lambda row: (-int(row["times"]), str(row["food"])))
    return [
        {
            "food": row["food"],
            "times": int(row["times"]),
            "total": round_calories(float(row["total"])),
        }
        for row in ranked[:5]
    ]


def _write_summary(
    ctx: Context,
    period_label: str,
    first_day: str,
    last_day: str,
    daily_totals: list[dict[str, Any]],
    rolling: list[dict[str, Any]],
    meal_split: list[dict[str, Any]],
    top_foods: list[dict[str, Any]],
    average_daily: float | None,
    direction_note: str,
) -> dict[str, Any]:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["My Food Diary", f"{period_label} ({first_day} to {last_day})"])
    writer.writerow(
        ["Average a day", f"{average_daily:.0f} kcal" if average_daily else "no data"]
    )
    writer.writerow(["Direction", direction_note])
    writer.writerow([])
    writer.writerow(["Day", "Calories", "Entries", "7-day average"])
    averages = {point["date"]: point["average"] for point in rolling}
    for row in daily_totals:
        average = averages.get(row["date"])
        writer.writerow(
            [
                row["date"],
                f"{row['total']:.0f}" if row["total"] is not None else "not logged",
                row["entry_count"],
                f"{average:.0f}" if average is not None else "",
            ]
        )
    writer.writerow([])
    writer.writerow(["Meal", "Calories in period", "Share of calories", "Entries"])
    for meal in meal_split:
        share = meal["share_percent"]
        writer.writerow(
            [
                meal["meal_label"],
                f"{meal['total']:.0f}",
                f"{share:g}%" if share is not None else "",
                meal["entry_count"],
            ]
        )
    writer.writerow([])
    writer.writerow(["Most logged food", "Times", "Calories in period"])
    for food in top_foods:
        writer.writerow([food["food"], food["times"], f"{food['total']:.0f}"])

    reference = ctx.artifacts.create(
        f"Food trends {first_day} to {last_day}.csv",
        buffer.getvalue(),
        media_type="text/csv",
    )
    return {"id": reference.id, "name": f"Food trends {first_day} to {last_day}.csv"}


def save_settings(
    ctx: Context,
    daily_calorie_target: float | None = None,
    week_starts_on: str | None = None,
    clear_target: bool | None = None,
) -> dict[str, Any]:
    """Set or clear my optional daily calorie target."""
    target = as_number(daily_calorie_target)
    if clear_target or (target is not None and target <= 0):
        target = None
    week_start = str(week_starts_on or "").strip().casefold()
    if week_start not in ("monday", "sunday"):
        week_start = ""

    existing = diary.settings_record(ctx)
    if existing is None:
        record = ctx.records.create(
            "my_settings",
            {
                "daily_calorie_target": target,
                "week_starts_on": week_start or "monday",
            },
        )
    else:
        changes: dict[str, Any] = {"daily_calorie_target": target}
        if week_start:
            changes["week_starts_on"] = week_start
        record = ctx.records.update(
            "my_settings",
            existing.id,
            expected_revision=existing.revision,
            changes=changes,
        )

    saved = as_number(record.get("daily_calorie_target"))
    return {
        "id": record.id,
        "revision": record.revision,
        "daily_calorie_target": saved,
        "week_starts_on": record.get("week_starts_on"),
        "has_target": saved is not None and saved > 0,
    }
