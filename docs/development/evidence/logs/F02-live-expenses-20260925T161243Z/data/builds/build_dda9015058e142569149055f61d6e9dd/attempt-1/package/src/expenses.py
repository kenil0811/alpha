"""Pure helpers for summarising plain-text expense lines."""

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

_CENTS = Decimal("0.01")

# ISO date, one or more spaces, a single-word category, one or more spaces,
# a decimal amount. Surrounding whitespace on the line is tolerated.
_LINE_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2})\s+(\S+)\s+([+-]?\d+(?:\.\d+)?)\s*$"
)


def _parse_line(line):
    """Return ``(category, amount)`` for a parsable line, else ``None``."""
    match = _LINE_RE.match(line)
    if match is None:
        return None

    raw_date, category, raw_amount = match.groups()
    try:
        date.fromisoformat(raw_date)
    except ValueError:
        return None

    # Decimal keeps the running totals exact; binary floats would drift.
    return category, Decimal(raw_amount)


def _to_number(total):
    """Round a Decimal total to 2 decimals and hand it back as a JSON number."""
    return float(total.quantize(_CENTS, rounding=ROUND_HALF_UP))


def summarize_expenses(lines):
    """Total the expenses per category and overall, ignoring unparsable lines.

    Blank lines carry no information and are skipped without being counted as
    ignored; any other line that does not match the expected shape is counted.
    """
    if not isinstance(lines, str):
        raise TypeError("lines must be a string")

    totals = {}
    ignored = 0

    for line in lines.split("\n"):
        if not line.strip():
            continue

        parsed = _parse_line(line)
        if parsed is None:
            ignored += 1
            continue

        category, amount = parsed
        totals[category] = totals.get(category, Decimal(0)) + amount

    overall = _to_number(sum(totals.values(), Decimal(0)))
    rounded = {category: _to_number(total) for category, total in totals.items()}

    return {"totals": rounded, "overall": overall, "ignored": ignored}
