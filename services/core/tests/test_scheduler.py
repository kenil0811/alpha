"""Local schedules: due times, no catch-up, on/off, run now, and the module's failures kept."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from alpha.capabilities.errors import OperationFailed
from alpha.execution.scheduler import Scheduler, describe, next_occurrence
from alpha.storage.control_store import ControlStore
from alpha_contracts.apps import ScheduleSpec
from alpha_contracts.runs import RunOrigin

EVERY = ScheduleSpec(id="poll", title="Check boards", action="check", every_minutes=120)
DAILY = ScheduleSpec(id="night", title="Nightly note", action="note", daily_at="21:00")


def test_next_occurrence_and_words() -> None:
    at = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
    assert next_occurrence(EVERY, at, "Asia/Kolkata") == at + timedelta(hours=2)
    # 21:00 in Kolkata is 15:30 UTC the same day when it is 10:00 UTC (15:30 local) now.
    assert next_occurrence(DAILY, at, "Asia/Kolkata") == datetime(2026, 9, 27, 15, 30, tzinfo=UTC)
    later = datetime(2026, 9, 27, 16, 0, tzinfo=UTC)
    assert next_occurrence(DAILY, later, "Asia/Kolkata") == datetime(
        2026, 9, 28, 15, 30, tzinfo=UTC
    )
    assert describe(EVERY) == "every 2 hours"
    assert describe(DAILY) == "every day at 21:00"
    assert describe(ScheduleSpec(id="d", title="d", action="a", every_minutes=1440)) == "every day"


def test_due_schedules_run_once_and_move_on(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    clock = {"now": datetime(2026, 9, 27, 10, 0, tzinfo=UTC)}
    calls: list[tuple[str, str, dict[str, Any], RunOrigin]] = []

    def invoke(app_id: str, action: str, payload: dict[str, Any], origin: RunOrigin) -> str:
        calls.append((app_id, action, payload, origin))
        return f"run_{len(calls)}"

    scheduler = Scheduler(
        store,
        active_apps=lambda: [("jobs", [EVERY])],
        invoke=invoke,
        timezone="UTC",
        now=lambda: clock["now"],
    )
    # First sight of a schedule: nothing runs (no catch-up); the next run is computed from now.
    assert scheduler.tick() == []
    [status] = scheduler.status("jobs", [EVERY])
    assert status["next_run_at"] == "2026-09-27T12:00:00Z" and status["last_run_at"] is None
    clock["now"] += timedelta(hours=1)
    assert scheduler.tick() == []
    clock["now"] += timedelta(hours=1, minutes=1)
    assert scheduler.tick() == ["run_1"]
    assert calls == [("jobs", "check", {}, RunOrigin.TRIGGER)]
    [status] = scheduler.status("jobs", [EVERY])
    assert status["last_run_id"] == "run_1" and status["next_run_at"] == "2026-09-27T14:01:00Z"
    # Switched off: nothing runs and no next time is promised.
    scheduler.set_enabled("jobs", [EVERY], "poll", False)
    clock["now"] += timedelta(hours=3)
    assert scheduler.tick() == []
    assert scheduler.status("jobs", [EVERY])[0]["next_run_at"] is None
    # Switched on: the next run counts from now, not from the missed time.
    scheduler.set_enabled("jobs", [EVERY], "poll", True)
    assert scheduler.status("jobs", [EVERY])[0]["next_run_at"] == "2026-09-27T17:01:00Z"
    # Run now works regardless of the timer.
    assert scheduler.run_now("jobs", [EVERY], "poll") == "run_2"


def test_a_failing_action_is_recorded_not_raised(tmp_path: Path) -> None:
    store = ControlStore(tmp_path / "control.sqlite")
    now = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)

    def invoke(app_id: str, action: str, payload: dict[str, Any], origin: RunOrigin) -> str:
        raise OperationFailed("forbidden", "action check cannot be invoked from trigger")

    scheduler = Scheduler(
        store,
        active_apps=lambda: [("jobs", [EVERY])],
        invoke=invoke,
        timezone="UTC",
        now=lambda: now,
    )
    assert scheduler.run_now("jobs", [EVERY], "poll") is None
    [status] = scheduler.status("jobs", [EVERY])
    assert status["last_error"] == "action check cannot be invoked from trigger"
    assert status["last_run_id"] is None
