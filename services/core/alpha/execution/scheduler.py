"""Local schedules: run a module's action every N minutes or daily at a local time, while Core
is running (UX specification §9).

State per (app, schedule) lives in the control store: whether it is switched on, when it last
ran and with which run, when it runs next, and the last problem. On start, and whenever a new
schedule appears, the next run is computed from now: missed occurrences while Alpha was closed
are never caught up, and never silently. A person can switch a schedule off, on, or run it now.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from alpha_contracts.apps import ScheduleSpec
from alpha_contracts.runs import RunOrigin

from alpha.capabilities.errors import OperationFailed, not_found
from alpha.storage.control_store import ControlStore

log = logging.getLogger("alpha.scheduler")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_schedules (
    app_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    last_run_at TEXT,
    last_run_id TEXT,
    last_error TEXT,
    next_run_at TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (app_id, schedule_id)
);
"""

TICK_SECONDS = 15.0


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse(text: str | None) -> datetime | None:
    return datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def next_occurrence(spec: ScheduleSpec, after: datetime, timezone: str) -> datetime:
    """The first time `spec` is due strictly after `after`."""
    if spec.every_minutes is not None:
        return after + timedelta(minutes=spec.every_minutes)
    assert spec.daily_at is not None
    hour, minute = (int(part) for part in spec.daily_at.split(":"))
    local = after.astimezone(ZoneInfo(timezone))
    candidate = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate.astimezone(UTC)


def describe(spec: ScheduleSpec) -> str:
    if spec.every_minutes is not None:
        minutes = spec.every_minutes
        if minutes % 1440 == 0:
            days = minutes // 1440
            return "every day" if days == 1 else f"every {days} days"
        if minutes % 60 == 0:
            hours = minutes // 60
            return "every hour" if hours == 1 else f"every {hours} hours"
        return f"every {minutes} minutes"
    return f"every day at {spec.daily_at}"


class Scheduler:
    def __init__(
        self,
        store: ControlStore,
        *,
        active_apps: Callable[[], list[tuple[str, list[ScheduleSpec]]]],
        invoke: Callable[[str, str, dict[str, Any], RunOrigin], str],
        timezone: str,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._active_apps = active_apps
        self._invoke = invoke
        self._timezone = timezone
        self._now = now or (lambda: datetime.now(tz=UTC))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        store.execute_script(_SCHEMA)

    # ----- lifecycle -----

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="alpha-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:  # a broken tick must not end scheduling for good
                log.exception("scheduler tick failed")
            self._stop.wait(TICK_SECONDS)

    # ----- one pass -----

    def tick(self) -> list[str]:
        """Run whatever is due; returns the run ids started."""
        now = self._now()
        started: list[str] = []
        for app_id, specs in self._active_apps():
            for spec in specs:
                row = self._row(app_id, spec.id)
                if row is None:
                    self._insert(app_id, spec, now)
                    continue
                if not row["enabled"]:
                    continue
                due = _parse(row["next_run_at"])
                if due is None:
                    self._set_next(app_id, spec, now)
                    continue
                if due > now:
                    continue
                run_id = self._run(app_id, spec, now)
                if run_id:
                    started.append(run_id)
        return started

    def _run(self, app_id: str, spec: ScheduleSpec, now: datetime) -> str | None:
        try:
            run_id = self._invoke(app_id, spec.action, dict(spec.input), RunOrigin.TRIGGER)
            error = None
        except OperationFailed as exc:
            run_id, error = None, exc.message
        except Exception as exc:  # the module's problem, kept for the person to see
            run_id, error = None, f"{type(exc).__name__}: {exc}"
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE app_schedules SET last_run_at = ?, last_run_id = ?, last_error = ?,
                   next_run_at = ?, updated_at = ? WHERE app_id = ? AND schedule_id = ?""",
                (
                    _iso(now),
                    run_id,
                    error,
                    _iso(next_occurrence(spec, now, self._timezone)),
                    _iso(now),
                    app_id,
                    spec.id,
                ),
            )
        return run_id

    # ----- state -----

    def _row(self, app_id: str, schedule_id: str) -> Any:
        rows = self._store.query(
            "SELECT * FROM app_schedules WHERE app_id = ? AND schedule_id = ?",
            (app_id, schedule_id),
        )
        return rows[0] if rows else None

    def _insert(self, app_id: str, spec: ScheduleSpec, now: datetime) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO app_schedules(app_id, schedule_id, enabled, next_run_at,
                   updated_at) VALUES (?,?,?,?,?)""",
                (
                    app_id,
                    spec.id,
                    1 if spec.enabled else 0,
                    _iso(next_occurrence(spec, now, self._timezone)),
                    _iso(now),
                ),
            )

    def _set_next(self, app_id: str, spec: ScheduleSpec, now: datetime) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE app_schedules SET next_run_at = ?, updated_at = ?
                   WHERE app_id = ? AND schedule_id = ?""",
                (_iso(next_occurrence(spec, now, self._timezone)), _iso(now), app_id, spec.id),
            )

    def status(self, app_id: str, specs: list[ScheduleSpec]) -> list[dict[str, Any]]:
        now = self._now()
        out: list[dict[str, Any]] = []
        for spec in specs:
            row = self._row(app_id, spec.id)
            if row is None:
                self._insert(app_id, spec, now)
                row = self._row(app_id, spec.id)
            out.append(
                {
                    "id": spec.id,
                    "title": spec.title,
                    "action": spec.action,
                    "when": describe(spec),
                    "enabled": bool(row["enabled"]),
                    "last_run_at": row["last_run_at"],
                    "last_run_id": row["last_run_id"],
                    "last_error": row["last_error"],
                    "next_run_at": row["next_run_at"] if row["enabled"] else None,
                }
            )
        return out

    def set_enabled(
        self, app_id: str, specs: list[ScheduleSpec], schedule_id: str, enabled: bool
    ) -> None:
        spec = next((s for s in specs if s.id == schedule_id), None)
        if spec is None:
            raise not_found(f"this module has no schedule {schedule_id!r}")
        now = self._now()
        if self._row(app_id, schedule_id) is None:
            self._insert(app_id, spec, now)
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE app_schedules SET enabled = ?, next_run_at = ?, updated_at = ?
                   WHERE app_id = ? AND schedule_id = ?""",
                (
                    1 if enabled else 0,
                    _iso(next_occurrence(spec, now, self._timezone)) if enabled else None,
                    _iso(now),
                    app_id,
                    schedule_id,
                ),
            )

    def run_now(self, app_id: str, specs: list[ScheduleSpec], schedule_id: str) -> str | None:
        spec = next((s for s in specs if s.id == schedule_id), None)
        if spec is None:
            raise not_found(f"this module has no schedule {schedule_id!r}")
        now = self._now()
        if self._row(app_id, schedule_id) is None:
            self._insert(app_id, spec, now)
        return self._run(app_id, spec, now)
