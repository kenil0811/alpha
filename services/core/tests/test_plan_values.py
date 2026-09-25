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
