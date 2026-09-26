"""Calorie estimates: a model guess when it can be had, a portion table otherwise.

Everything produced here is an estimate the person can overwrite. Their own
numbers never pass through this module.
"""

from __future__ import annotations

import re
from typing import Any

from alpha_sdk import Context

from .diary import as_number, clean_text, round_calories

# Typical calories for one ordinary portion of an everyday food.
PORTIONS: dict[str, float] = {
    "roti": 110,
    "chapati": 110,
    "phulka": 100,
    "paratha": 210,
    "naan": 260,
    "poori": 140,
    "puri": 140,
    "rice": 200,
    "biryani": 550,
    "pulao": 330,
    "khichdi": 250,
    "dal": 150,
    "sambar": 90,
    "rasam": 60,
    "rajma": 210,
    "chole": 230,
    "idli": 65,
    "idly": 65,
    "dosa": 170,
    "uttapam": 200,
    "vada": 130,
    "upma": 250,
    "poha": 250,
    "dhokla": 160,
    "oats": 150,
    "porridge": 170,
    "cornflakes": 130,
    "muesli": 190,
    "bread": 75,
    "toast": 90,
    "sandwich": 300,
    "burger": 500,
    "pizza": 285,
    "pasta": 320,
    "noodles": 300,
    "maggi": 350,
    "momos": 250,
    "egg": 78,
    "omelette": 160,
    "chicken": 250,
    "mutton": 290,
    "fish": 200,
    "prawns": 150,
    "paneer": 270,
    "tofu": 150,
    "curry": 250,
    "gravy": 220,
    "sabzi": 150,
    "salad": 180,
    "raita": 80,
    "curd": 100,
    "yoghurt": 100,
    "yogurt": 100,
    "papad": 40,
    "pickle": 20,
    "chutney": 40,
    "banana": 105,
    "apple": 95,
    "orange": 60,
    "mango": 200,
    "grapes": 60,
    "guava": 60,
    "papaya": 60,
    "milk": 120,
    "tea": 60,
    "coffee": 60,
    "juice": 110,
    "smoothie": 200,
    "lassi": 180,
    "buttermilk": 60,
    "water": 0,
    "soda": 140,
    "cola": 140,
    "beer": 150,
    "wine": 125,
    "biscuit": 50,
    "cookie": 60,
    "cake": 350,
    "chocolate": 230,
    "halwa": 320,
    "ladoo": 180,
    "jalebi": 150,
    "samosa": 260,
    "pakora": 175,
    "chips": 150,
    "namkeen": 180,
    "nuts": 180,
    "almonds": 165,
    "peanuts": 170,
    "soup": 120,
    "shake": 200,
    "protein bar": 200,
    "energy bar": 200,
    "ice cream": 250,
    "protein powder": 120,
}

# A typical portion when nothing in the description is recognised.
TYPICAL_PORTION = 250.0

WORD_NUMBERS: dict[str, float] = {
    "a": 1,
    "an": 1,
    "one": 1,
    "couple": 2,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "half": 0.5,
}

_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+")


def _stem(token: str) -> str:
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("es") and len(token) > 4:
        return token[:-2]
    if token.endswith("s") and len(token) > 3:
        return token[:-1]
    return token


def _quantity_before(tokens: list[str], index: int) -> float:
    """How many of this food the person seems to have eaten."""
    for step in (1, 2, 3):
        position = index - step
        if position < 0:
            break
        token = tokens[position]
        try:
            return float(token)
        except ValueError:
            pass
        if token in WORD_NUMBERS:
            return WORD_NUMBERS[token]
        if token in ("bowl", "plate", "cup", "glass", "bowls", "plates"):
            continue
        if token in ("of", "and", "with", "the", "my", "some"):
            continue
        break
    return 1.0


def _match_multiword(text: str) -> list[tuple[str, float, float]]:
    found: list[tuple[str, float, float]] = []
    for name, per_portion in PORTIONS.items():
        if " " not in name:
            continue
        if name in text:
            found.append((name, 1.0, per_portion))
    return found


def from_portion_table(
    food: str, amount: str | None = None, quantity: float | None = None
) -> tuple[float, str]:
    """A calorie figure from the portion table, with a one-line basis."""
    text = f"{food or ''} {amount or ''}".casefold()
    tokens = _TOKEN.findall(text)
    parts: list[tuple[str, float, float]] = []
    seen: set[str] = set()
    for name, count, per_portion in _match_multiword(text):
        parts.append((name, count, per_portion))
        seen.update(name.split())
    for index, token in enumerate(tokens):
        if token in seen:
            continue
        stem = _stem(token)
        per_portion = PORTIONS.get(stem, PORTIONS.get(token))
        if per_portion is None:
            continue
        name = stem if stem in PORTIONS else token
        if name in [part[0] for part in parts]:
            continue
        parts.append((name, _quantity_before(tokens, index), per_portion))

    if not parts:
        total = TYPICAL_PORTION * (quantity if quantity and quantity > 0 else 1.0)
        return (
            round_calories(total),
            f"no close match, so a typical portion ≈ {round_calories(total):.0f} kcal",
        )

    if quantity and quantity > 0 and len(parts) == 1 and not any(
        token.replace(".", "", 1).isdigit() for token in tokens
    ):
        name, _count, per_portion = parts[0]
        parts = [(name, float(quantity), per_portion)]

    pieces: list[str] = []
    total = 0.0
    for name, count, per_portion in parts:
        subtotal = count * per_portion
        total += subtotal
        if count == 1:
            pieces.append(f"1 {name} ≈ {per_portion:.0f} kcal")
        else:
            counted = f"{count:g}"
            pieces.append(f"{counted} × {name} ≈ {subtotal:.0f} kcal")
    basis = " + ".join(pieces)
    if len(pieces) > 1:
        basis = f"{basis} = {round_calories(total):.0f} kcal"
    return round_calories(total), basis[:240]


def _field(guess: Any, name: str) -> Any:
    try:
        return guess[name]
    except Exception:
        return getattr(guess, name, None)


def estimate(
    ctx: Context,
    food: str,
    amount: str | None = None,
    quantity: float | None = None,
    unit: str | None = None,
) -> tuple[float, str, Any | None]:
    """Estimate the calories in what was eaten.

    Returns the figure, a one-line basis for it and the model's own answer when
    one was used (so the saved value can be labelled an estimate).
    """
    described = " ".join(part for part in (food, amount) if part)
    guess: Any | None = None
    try:
        guess = ctx.models.structured(
            "Estimate the total calories in what this person ate. Judge the "
            "amount from their own words. Keep the basis to one short line, "
            "like '1 roti ≈ 110 kcal, dal ≈ 150 kcal'.",
            input={
                "food": food,
                "amount": amount or "",
                "quantity": quantity,
                "unit": unit or "",
                "described": described,
            },
            fields={
                "calories": {
                    "kind": "number",
                    "minimum": 0,
                    "maximum": 20000,
                    "required": True,
                },
                "basis": {"kind": "text", "max_length": 200, "required": True},
            },
        )
    except Exception as error:  # a missing or unhappy model must not lose the entry
        ctx.log("Falling back to the portion table for this estimate", reason=str(error))
        guess = None

    if guess is not None:
        calories = as_number(_field(guess, "calories"))
        basis = clean_text(_field(guess, "basis"), 240)
        if calories is not None and calories > 0:
            if not basis:
                basis = f"estimated from '{described}'"
            return round_calories(calories), basis, guess

    calories, basis = from_portion_table(food, amount, quantity)
    return calories, basis, None
