"""Pure helpers for summarising plain-text expense lines."""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# ISO date, spaces, single-word category, spaces, decimal amount.
_LINE = re.compile(
    r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r" +(?P<category>\S+)"
    r" +(?P<amount>-?\d+(?:\.\d+)?)$"
)

_CENTS = Decimal("0.01")


def _parse(line):
    """Return (category, Decimal amount) for a parsable line, else None."""
    match = _LINE.match(line.strip())
    if match is None:
        return None
    try:
        date(int(match["year"]), int(match["month"]), int(match["day"]))
        amount = Decimal(match["amount"])
    except (ValueError, InvalidOperation):
        return None
    return match["category"], amount


def _round(amount):
    return float(amount.quantize(_CENTS, rounding=ROUND_HALF_UP))


def summarize_expenses(lines):
    """Total the expenses per category and overall, ignoring unparsable lines."""
    if not isinstance(lines, str):
        raise TypeError("lines must be a string")

    totals = {}
    overall = Decimal(0)
    ignored = 0

    for line in lines.split("\n"):
        if not line.strip():
            # Blank lines are separators, not malformed entries.
            continue
        parsed = _parse(line)
        if parsed is None:
            ignored += 1
            continue
        category, amount = parsed
        totals[category] = totals.get(category, Decimal(0)) + amount
        overall += amount

    return {
        "totals": {category: _round(total) for category, total in totals.items()},
        "overall": _round(overall),
        "ignored": ignored,
    }
