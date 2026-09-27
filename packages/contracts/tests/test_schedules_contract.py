"""Declared schedules: one rule each, a trigger-invocable action, and the capability declared."""

from __future__ import annotations

import copy

import pytest
from alpha_contracts.apps import AppSource
from pydantic import ValidationError

from .test_screens_contract import SOURCE


def _with_schedule(**overrides: object) -> dict:
    data = copy.deepcopy(SOURCE)
    data["capabilities"] = ["records", "schedules"]
    data["actions"][0]["invocable_from"] = ["ui", "manual", "trigger"]
    data["schedules"] = [
        {
            "id": "poll",
            "title": "Log a line",
            "action": "log_entry",
            "input": {"text": "x"},
            "every_minutes": 60,
            **overrides,
        }
    ]
    return data


def test_a_schedule_validates() -> None:
    source = AppSource.model_validate(_with_schedule())
    assert source.schedules[0].every_minutes == 60


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d["schedules"][0].update({"daily_at": "21:00"}), "exactly one of"),
        (lambda d: d["schedules"][0].pop("every_minutes"), "exactly one of"),
        (lambda d: d["schedules"][0].update({"action": "correct_entry"}), "does not list trigger"),
        (lambda d: d["schedules"][0].update({"action": "nope"}), "undeclared action"),
        (lambda d: d.update({"capabilities": ["records"]}), "declare the schedules capability"),
        (lambda d: d["schedules"][0].update({"every_minutes": 1}), "greater than or equal to 5"),
    ],
)
def test_bad_schedules_are_refused(change, message: str) -> None:
    data = _with_schedule()
    change(data)
    with pytest.raises(ValidationError, match=message):
        AppSource.model_validate(data)


def test_daily_time_must_be_hh_mm() -> None:
    data = _with_schedule()
    data["schedules"][0].pop("every_minutes")
    data["schedules"][0]["daily_at"] = "9pm"
    with pytest.raises(ValidationError):
        AppSource.model_validate(data)
