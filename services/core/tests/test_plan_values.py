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


def test_an_expected_null_means_unknown() -> None:
    """A record whose estimate was unavailable stores the field as unknown (absent or null)."""
    assert matches({"title": "x", "minutes": None}, {"title": "x"})
    assert matches({"minutes": None}, {"minutes": None})
    assert not matches({"minutes": None}, {"minutes": 30})
    assert not matches({"minutes": None}, {"minutes": 0}), "zero is a value, not unknown"


def test_handler_exceptions_reach_people_in_plain_words() -> None:
    """M1-R05: "ValueError: Paste your to-do list…" showed a Python class name to the person."""
    from alpha.execution.coordinator import plain_worker_error

    refusal = plain_worker_error(
        {"kind": "error", "code": "handler_exception", "message": "ValueError: Amount is needed."}
    )
    assert refusal["message"] == "Amount is needed."
    assert refusal["technical"] == "ValueError: Amount is needed."
    crash = plain_worker_error(
        {"kind": "error", "code": "handler_exception", "message": "KeyError: 'calories'"}
    )
    assert crash["message"] == "Something went wrong in this workflow."
    assert crash["exception"] == "KeyError"
    sdk = {"kind": "error", "code": "operation_failed", "message": "Food is needed."}
    assert plain_worker_error(sdk) == sdk


def test_a_records_filter_resolves_its_placeholders_before_reading() -> None:
    """Found in M1-R07: {"$today": 0} in a records step's filter reached the store unresolved,
    so every read failed ("filter on date must be text") and three builds were refused."""
    from types import SimpleNamespace

    from alpha.builds.plan import run_records
    from alpha_contracts.verification import RecordsStep

    seen: list[object] = []
    preview = SimpleNamespace(
        timezone="UTC",
        records_in=lambda _collection, where: seen.append(where) or [],
    )
    step = RecordsStep.model_validate(
        {
            "kind": "records",
            "id": "today",
            "collection": "food_entries",
            "where": {
                "all": [
                    {"field": "date", "op": "eq", "value": {"$today": 0}},
                    {"field": "entry", "op": "eq", "value": {"$ref": "add.output.id"}},
                ]
            },
            "count": 0,
        }
    )
    result = run_records(preview, step, {"add": {"id": "rec_1"}}, "c")  # type: ignore[arg-type]
    assert result.status.value == "passed", result.summary
    today = datetime.now(ZoneInfo("UTC")).date().isoformat()
    [where] = seen
    assert where.model_dump(mode="json", by_alias=True) == {  # type: ignore[attr-defined]
        "all": [
            {"field": "date", "op": "eq", "value": today},
            {"field": "entry", "op": "eq", "value": "rec_1"},
        ]
    }
