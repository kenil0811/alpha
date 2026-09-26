"""Reading a pasted to-do list, fitting it into the hours available, writing it back."""

from __future__ import annotations

import re
from typing import Any

# A duration at the end of a line: 1:30, 1.5h, 2h 15m, 90m.
_DURATION = re.compile(
    r"""
    (?:
        (?P<hh>\d{1,2}) : (?P<mm>[0-5]\d)
      | (?P<hours>\d+(?:[.,]\d+)?) \s* (?:h|hr|hrs|hour|hours)
        (?: \s* (?P<extra>\d+) \s* (?:m|min|mins|minute|minutes)? )?
      | (?P<minutes>\d+(?:[.,]\d+)?) \s* (?:m|min|mins|minute|minutes)
    )
    \s* [)\]]? \s* $
    """,
    re.VERBOSE | re.IGNORECASE,
)

_LEADING_BULLET = re.compile(r"^\s*(?:[-*•–—]+|\d+[.)])\s*")
_TRAILING_SEPARATOR = re.compile(r"[\s\-–—:,;(\[|~=]+$")

# Used when a line gives no duration; always reported as an estimate.
ESTIMATE_MINUTES = 30


def _minutes_from(match: "re.Match[str]") -> int:
    groups = match.groupdict()
    if groups["hh"] is not None:
        return int(groups["hh"]) * 60 + int(groups["mm"])
    if groups["hours"] is not None:
        total = float(groups["hours"].replace(",", ".")) * 60
        if groups["extra"] is not None:
            total += int(groups["extra"])
        return int(round(total))
    return int(round(float(groups["minutes"].replace(",", ".")) * 1))


def read_items(text: str) -> list[dict[str, Any]]:
    """One item per non-empty line, in the pasted order, with its duration in minutes."""
    items: list[dict[str, Any]] = []
    for raw_line in (text or "").splitlines():
        line = _LEADING_BULLET.sub("", raw_line).strip()
        if not line:
            continue
        match = _DURATION.search(line)
        name = line
        minutes = ESTIMATE_MINUTES
        estimated = True
        if match is not None:
            candidate = _TRAILING_SEPARATOR.sub("", line[: match.start()]).strip()
            parsed = _minutes_from(match)
            if candidate and parsed > 0:
                name = candidate
                minutes = parsed
                estimated = False
        items.append(
            {"name": name, "duration_minutes": minutes, "estimated": estimated}
        )
    return items


def fit_items(
    items: list[dict[str, Any]], hours_available: float
) -> dict[str, Any]:
    """Go down the list in order, keeping each item whole, never passing the hours given."""
    capacity = int(round(hours_available * 60))
    plan: list[dict[str, Any]] = []
    wont_fit: list[dict[str, Any]] = []
    running = 0
    for item in items:
        minutes = int(item["duration_minutes"])
        if running + minutes <= capacity:
            running += minutes
            entry = {
                "name": item["name"],
                "duration_minutes": minutes,
                "running_minutes": running,
                "estimated": bool(item.get("estimated", False)),
            }
            plan.append(entry)
        else:
            wont_fit.append(
                {
                    "name": item["name"],
                    "duration_minutes": minutes,
                    "estimated": bool(item.get("estimated", False)),
                }
            )
    return {
        "plan": plan,
        "wont_fit": wont_fit,
        "total_minutes": running,
        "available_minutes": capacity,
        "minutes_spare": capacity - running,
        "short_by_minutes": sum(int(i["duration_minutes"]) for i in wont_fit),
    }


def say_duration(minutes: int) -> str:
    minutes = int(minutes)
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    if hours:
        return f"{hours}h"
    return f"{rest}m"


def write_plan_text(
    plan: list[dict[str, Any]],
    wont_fit: list[dict[str, Any]],
    hours_available: float,
) -> str:
    capacity = int(round(hours_available * 60))
    running = 0
    lines = [f"Plan for the {say_duration(capacity)} you have today:"]
    if not plan:
        lines.append("Nothing fits in the time available.")
    for position, item in enumerate(plan, start=1):
        minutes = int(item["duration_minutes"])
        running = int(item.get("running_minutes") or running + minutes)
        note = " (estimated time, correct it if it is wrong)" if item.get("estimated") else ""
        lines.append(
            f"{position}. {item['name']} - {say_duration(minutes)}"
            f" (running total {say_duration(running)}){note}"
        )
    lines.append("")
    lines.append(
        f"Total planned: {say_duration(running)} of {say_duration(capacity)} available."
    )
    lines.append("")
    if wont_fit:
        lines.append("Won't fit today:")
        short_by = 0
        for item in wont_fit:
            minutes = int(item["duration_minutes"])
            short_by += minutes
            note = " (estimated time)" if item.get("estimated") else ""
            lines.append(f"- {item['name']} - needs {say_duration(minutes)}{note}")
        lines.append("")
        lines.append(f"Short by {say_duration(short_by)} to get everything done.")
    else:
        lines.append("Everything on the list fits today.")
    return "\n".join(lines)


def hours_or_fail(hours_available: Any) -> float:
    """The hours available today, or a refusal the person can act on."""
    if hours_available is None or isinstance(hours_available, bool):
        raise ValueError(
            "Say how many hours you have available today, for example 4, and run it again."
        )
    hours = float(hours_available)
    if hours <= 0:
        raise ValueError("The hours available today must be more than zero.")
    if hours > 24:
        raise ValueError("A day only has 24 hours; give the hours you actually have today.")
    return hours
