"""Plan value placeholders and the deep match used by behaviour checks."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from alpha.builds.plan import UnresolvedReference, matches, resolve_values


def test_placeholders_resolve_from_earlier_outputs_and_the_local_date() -> None:
    outputs = {"add": {"id": "rec_1", "nested": {"n": 3}}}
    tomorrow = (datetime.now(ZoneInfo("Asia/Kolkata")).date() + timedelta(days=1)).isoformat()
    value = {
        "id": {"$ref": "add.output.id"},
        "deep": [{"$ref": "add.output.nested.n"}],
        "on": {"$today": 1},
    }
    assert resolve_values(value, outputs, "Asia/Kolkata") == {
        "id": "rec_1",
        "deep": [3],
        "on": tomorrow,
    }
    with pytest.raises(UnresolvedReference):
        resolve_values({"$ref": "later.output.id"}, outputs, "UTC")
    with pytest.raises(UnresolvedReference):
        resolve_values({"$ref": "add.output.missing"}, outputs, "UTC")


def test_matching_is_a_subset_unless_exact() -> None:
    observed = {"id": "r", "total": 12.0, "items": [{"a": 1, "b": 2}], "done": False}
    assert matches({"total": 12}, observed)
    assert matches({"items": [{"a": 1}]}, observed)
    assert not matches({"items": [{"a": 1}]}, observed, exact=True)
    assert not matches({"total": 13}, observed)
    assert not matches({"done": 0}, observed), "booleans never equal numbers"
    assert not matches({"items": []}, observed), "lists must have the same length"
    assert matches(observed, observed, exact=True)


def test_any_value_requires_presence_not_a_particular_value() -> None:
    expected = {"id": {"$any": True}, "revision": {"$any": True}, "calories_are_estimated": True}
    observed = {"id": "rec_1", "revision": 1, "calories_are_estimated": True, "extra": 3}
    assert matches(expected, observed)
    assert not matches(expected, {"revision": 1, "calories_are_estimated": True})
    assert not matches(expected, {**observed, "id": None})
    assert not matches({"id": "*"}, {"id": "rec_1"}), "a literal star is only a literal"


def test_star_expectations_from_the_planner_become_any_value() -> None:
    """Found in G1: the planner wrote {"id": "*", "revision": "*"}; every check failed."""
    from alpha.solutions.planner import normalize_expectations
    from alpha_contracts.verification import ValidationPlan

    plan = ValidationPlan.model_validate(
        {
            "scenarios": [
                {
                    "id": "log",
                    "description": "log one",
                    "steps": [
                        {
                            "kind": "invoke",
                            "id": "add",
                            "action": "log_food",
                            "input": {"food": "*"},
                            "output": {"id": "*", "revision": "*"},
                        },
                        {
                            "kind": "records",
                            "id": "stored",
                            "collection": "food",
                            "includes": [{"food": "*", "id": "*"}],
                        },
                    ],
                }
            ]
        }
    )
    fixed, changed = normalize_expectations(plan)
    steps = fixed.scenarios[0].steps
    assert changed == 4
    assert steps[0].output == {"id": {"$any": True}, "revision": {"$any": True}}
    assert steps[0].input == {"food": "*"}, "inputs are data and stay as written"
    assert steps[1].includes == [{"food": {"$any": True}, "id": {"$any": True}}]
