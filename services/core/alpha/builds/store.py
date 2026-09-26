"""Durable build records: builds, attempts, events and dependency qualification requests.

The BuildService decides what happens; this store only records it. Every state change and its
event commit together, and a terminal build is never changed again (a late transition is
recorded as skipped instead).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from alpha_contracts.builds import (
    TERMINAL_BUILD_STATES,
    BuildBudget,
    BuildEvent,
    BuildState,
    BuildUsage,
    FailureCategory,
)
from alpha_contracts.verification import InvokeStep, Scenario, ValidationPlan
from pydantic import BaseModel, ConfigDict, Field

from alpha.storage.control_store import ConflictError, ControlStore, NotFoundError, new_id, utc_now


def _dt(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class AcceptanceExample(BaseModel):
    """F02 input form: one action, one input, the exact expected output. Converted into a
    ValidationPlan scenario; kept so existing callers and the F02 qualification still work."""

    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=64)
    input: dict[str, Any]
    expected: dict[str, Any]


def plan_from_examples(examples: list[AcceptanceExample]) -> ValidationPlan:
    return ValidationPlan(
        scenarios=[
            Scenario(
                id=f"example_{i + 1}",
                description=f"{e.action_id} returns exactly the expected output",
                steps=[
                    InvokeStep(
                        id="run", action=e.action_id, input=e.input, output=e.expected, exact=True
                    )
                ],
            )
            for i, e in enumerate(examples)
        ]
    )


class AttemptRecord(BaseModel):
    attempt_id: str
    number: int
    status: str
    failure_category: str | None = None
    workspace_ref: str
    started_at: str
    finished_at: str | None = None
    usage: dict[str, Any] | None = None
    harness_exit: dict[str, Any] | None = None
    report_ref: str | None = None


class BuildRecord(BaseModel):
    build_id: str
    state: BuildState
    goal: str
    instructions: str
    plan: ValidationPlan
    route_id: str
    harness: str
    budget: BuildBudget
    brief_ref: str
    created_at: str
    updated_at: str
    finished_at: str | None = None
    terminal_reason: str | None = None
    failure_category: str | None = None
    attempts: list[AttemptRecord]
    candidate: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    seed_package: str | None = None
    app_id: str | None = None
    latest_sequence: int


_SCHEMA = """
CREATE TABLE IF NOT EXISTS builds (
    build_id TEXT PRIMARY KEY,
    brief_ref TEXT NOT NULL,
    goal TEXT NOT NULL,
    instructions TEXT NOT NULL,
    acceptance_json TEXT NOT NULL,
    route_id TEXT NOT NULL,
    harness TEXT NOT NULL,
    budget_json TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    terminal_reason TEXT,
    failure_category TEXT,
    candidate_json TEXT,
    validation_json TEXT,
    latest_sequence INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS build_attempts (
    attempt_id TEXT PRIMARY KEY,
    build_id TEXT NOT NULL REFERENCES builds(build_id),
    number INTEGER NOT NULL,
    status TEXT NOT NULL,
    failure_category TEXT,
    workspace_ref TEXT NOT NULL,
    pid INTEGER,
    pgid INTEGER,
    core_instance_id TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    usage_json TEXT,
    harness_exit_json TEXT,
    UNIQUE(build_id, number)
);
CREATE TABLE IF NOT EXISTS build_events (
    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    build_id TEXT NOT NULL REFERENCES builds(build_id),
    attempt_id TEXT,
    sequence INTEGER NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    UNIQUE(build_id, sequence)
);
CREATE TABLE IF NOT EXISTS dependency_requests (
    request_id TEXT PRIMARY KEY,
    build_id TEXT NOT NULL REFERENCES builds(build_id),
    attempt_id TEXT NOT NULL,
    package TEXT NOT NULL,
    version TEXT,
    found_in TEXT NOT NULL,
    location TEXT NOT NULL,
    runtime_profile_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# Columns added after F02; an existing control store gains them on startup.
_MIGRATIONS = (
    ("builds", "plan_json", "TEXT"),
    ("builds", "seed_package", "TEXT"),
    ("builds", "app_id", "TEXT"),
    ("build_attempts", "report_ref", "TEXT"),
)


class BuildStore:
    def __init__(self, db: ControlStore) -> None:
        self._db = db
        db.execute_script(_SCHEMA)
        for table, column, kind in _MIGRATIONS:
            db.add_missing_columns(table, {column: kind})

    # ----- reads -------------------------------------------------------------------------

    def get(self, build_id: str) -> BuildRecord:
        rows = self._db.query("SELECT * FROM builds WHERE build_id = ?", (build_id,))
        if not rows:
            raise NotFoundError(build_id)
        return self._row_to_record(rows[0])

    def list_builds(self, limit: int = 50) -> list[BuildRecord]:
        rows = self._db.query(
            "SELECT * FROM builds ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        )
        return [self._row_to_record(r) for r in rows]

    def events(self, build_id: str, after: int = 0, limit: int = 1000) -> list[BuildEvent]:
        self.get(build_id)
        rows = self._db.query(
            "SELECT * FROM build_events WHERE build_id = ? AND sequence > ?"
            " ORDER BY sequence LIMIT ?",
            (build_id, after, limit),
        )
        return [
            BuildEvent(
                event_id=r["event_id"],
                build_id=r["build_id"],
                attempt_id=r["attempt_id"],
                sequence=int(r["sequence"]),
                kind=r["kind"],
                occurred_at=datetime.fromisoformat(r["occurred_at"].replace("Z", "+00:00")),
                payload=json.loads(r["payload_json"]),
            )
            for r in rows
        ]

    def running_attempts(self, build_id: str | None = None) -> list[Any]:
        if build_id is None:
            return self._db.query("SELECT * FROM build_attempts WHERE status = 'running'")
        return self._db.query(
            "SELECT * FROM build_attempts WHERE build_id = ? AND status = 'running'", (build_id,)
        )

    def unfinished_builds(self) -> list[Any]:
        placeholders = ",".join("?" for _ in TERMINAL_BUILD_STATES)
        return self._db.query(
            f"SELECT build_id, state FROM builds WHERE state NOT IN ({placeholders})",
            tuple(s.value for s in TERMINAL_BUILD_STATES),
        )

    def dependency_requests(self, build_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM dependency_requests"
        params: tuple[Any, ...] = ()
        if build_id is not None:
            sql += " WHERE build_id = ?"
            params = (build_id,)
        return [dict(r) for r in self._db.query(sql + " ORDER BY created_at", params)]

    # ----- writes ------------------------------------------------------------------------

    def insert_build(
        self,
        *,
        build_id: str,
        brief_ref: str,
        goal: str,
        instructions: str,
        plan: ValidationPlan,
        seed_package: str | None,
        app_id: str | None,
        route_id: str,
        harness: str,
        budget: BuildBudget,
        created_at: datetime,
        queued_payload: dict[str, Any],
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO builds(build_id, brief_ref, goal, instructions, acceptance_json,
                   plan_json, seed_package, app_id, route_id, harness, budget_json, state,
                   created_at, updated_at, latest_sequence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                (
                    build_id,
                    brief_ref,
                    goal,
                    instructions,
                    "[]",
                    plan.model_dump_json(),
                    seed_package,
                    app_id,
                    route_id,
                    harness,
                    budget.model_dump_json(),
                    BuildState.QUEUED.value,
                    _dt(created_at),
                    _dt(created_at),
                ),
            )
            self.append_locked(conn, build_id, None, "build.queued", queued_payload)

    def insert_attempt(
        self,
        *,
        attempt_id: str,
        build_id: str,
        number: int,
        workspace_ref: str,
        core_instance_id: str,
        started_at: datetime,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO build_attempts(attempt_id, build_id, number, status, workspace_ref,
                   core_instance_id, started_at) VALUES (?,?,?,?,?,?,?)""",
                (
                    attempt_id,
                    build_id,
                    number,
                    "running",
                    workspace_ref,
                    core_instance_id,
                    _dt(started_at),
                ),
            )

    def set_attempt_process(self, attempt_id: str, pid: int, pgid: int) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE build_attempts SET pid = ?, pgid = ? WHERE attempt_id = ?",
                (pid, pgid, attempt_id),
            )

    def set_report_ref(self, attempt_id: str, report_ref: str) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "UPDATE build_attempts SET report_ref = ? WHERE attempt_id = ?",
                (report_ref, attempt_id),
            )

    def record_dependency_request(
        self, build_id: str, attempt_id: str, request: dict[str, Any]
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """INSERT INTO dependency_requests(request_id, build_id, attempt_id, package,
                   version, found_in, location, runtime_profile_id, reason, state, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    new_id("depreq"),
                    build_id,
                    attempt_id,
                    request["package"],
                    request.get("version"),
                    request["found_in"],
                    request["where"],
                    request["runtime_profile_id"],
                    request["reason"],
                    "requested",
                    _dt(utc_now()),
                ),
            )
            self.append_locked(
                conn, build_id, attempt_id, "dependency.qualification_requested", request
            )

    def append(
        self, build_id: str, attempt_id: str | None, kind: str, payload: dict[str, Any]
    ) -> None:
        with self._db.transaction() as conn:
            self.append_locked(conn, build_id, attempt_id, kind, payload)

    def append_locked(
        self, conn: Any, build_id: str, attempt_id: str | None, kind: str, payload: dict[str, Any]
    ) -> None:
        row = conn.execute(
            "SELECT latest_sequence FROM builds WHERE build_id = ?", (build_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(build_id)
        sequence = int(row["latest_sequence"]) + 1
        now = _dt(utc_now())
        conn.execute(
            "INSERT INTO build_events(event_id, build_id, attempt_id, sequence, kind, occurred_at,"
            " payload_json) VALUES (?,?,?,?,?,?,?)",
            (
                new_id("bevt"),
                build_id,
                attempt_id,
                sequence,
                kind,
                now,
                json.dumps(payload, sort_keys=True, default=str),
            ),
        )
        conn.execute(
            "UPDATE builds SET latest_sequence = ?, updated_at = ? WHERE build_id = ?",
            (sequence, now, build_id),
        )

    def transition(
        self,
        build_id: str,
        *,
        new_state: BuildState,
        event_kind: str,
        payload: dict[str, Any],
        attempt_id: str | None = None,
        expected: set[BuildState] | None = None,
        terminal_reason: str | None = None,
        failure_category: FailureCategory | None = None,
        candidate: dict[str, Any] | None = None,
        validation: dict[str, Any] | None = None,
    ) -> None:
        now = _dt(utc_now())
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT state FROM builds WHERE build_id = ?", (build_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(build_id)
            current = BuildState(row["state"])
            if current in TERMINAL_BUILD_STATES:
                self.append_locked(
                    conn,
                    build_id,
                    attempt_id,
                    "build.transition_skipped",
                    {"attempted": new_state.value, "current": current.value},
                )
                return
            if expected is not None and current not in expected:
                raise ConflictError(f"build {build_id} is {current.value}, expected {expected}")
            sets = ["state = ?", "updated_at = ?"]
            params: list[Any] = [new_state.value, now]
            if new_state in TERMINAL_BUILD_STATES:
                sets += ["finished_at = ?", "terminal_reason = ?", "failure_category = ?"]
                params += [
                    now,
                    terminal_reason,
                    failure_category.value if failure_category else None,
                ]
            if candidate is not None:
                sets.append("candidate_json = ?")
                params.append(json.dumps(candidate))
            if validation is not None:
                sets.append("validation_json = ?")
                params.append(json.dumps(validation, default=str))
            params.append(build_id)
            conn.execute(f"UPDATE builds SET {', '.join(sets)} WHERE build_id = ?", params)
            self.append_locked(conn, build_id, attempt_id, event_kind, payload)

    def fail(
        self,
        build_id: str,
        attempt_id: str,
        reason: str,
        category: FailureCategory,
        payload: dict[str, Any],
        validation: dict[str, Any] | None = None,
    ) -> None:
        self.transition(
            build_id,
            new_state=BuildState.FAILED,
            event_kind="build.failed",
            payload={"reason": reason, "failure_category": category.value, **payload},
            attempt_id=attempt_id,
            terminal_reason=reason,
            failure_category=category,
            validation=validation,
        )

    def finish_attempt(
        self,
        attempt_id: str,
        status: str,
        category: FailureCategory | None,
        usage: BuildUsage | None,
        harness_exit: dict[str, Any] | None,
    ) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                """UPDATE build_attempts SET status = ?, failure_category = ?, finished_at = ?,
                   usage_json = ?, harness_exit_json = ? WHERE attempt_id = ?""",
                (
                    status,
                    category.value if category else None,
                    _dt(utc_now()),
                    usage.model_dump_json() if usage else None,
                    json.dumps(harness_exit, default=str) if harness_exit else None,
                    attempt_id,
                ),
            )

    def _row_to_record(self, row: Any) -> BuildRecord:
        attempts = self._db.query(
            "SELECT * FROM build_attempts WHERE build_id = ? ORDER BY number", (row["build_id"],)
        )
        if row["plan_json"]:
            plan = ValidationPlan.model_validate_json(row["plan_json"])
        else:  # an F02 build: its examples are the plan
            plan = plan_from_examples(
                [AcceptanceExample.model_validate(e) for e in json.loads(row["acceptance_json"])]
            )
        return BuildRecord(
            build_id=row["build_id"],
            state=BuildState(row["state"]),
            goal=row["goal"],
            instructions=row["instructions"],
            plan=plan,
            route_id=row["route_id"],
            harness=row["harness"],
            budget=BuildBudget.model_validate_json(row["budget_json"]),
            brief_ref=row["brief_ref"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            finished_at=row["finished_at"],
            terminal_reason=row["terminal_reason"],
            failure_category=row["failure_category"],
            attempts=[
                AttemptRecord(
                    attempt_id=a["attempt_id"],
                    number=int(a["number"]),
                    status=a["status"],
                    failure_category=a["failure_category"],
                    workspace_ref=a["workspace_ref"],
                    started_at=a["started_at"],
                    finished_at=a["finished_at"],
                    usage=json.loads(a["usage_json"]) if a["usage_json"] else None,
                    harness_exit=json.loads(a["harness_exit_json"])
                    if a["harness_exit_json"]
                    else None,
                    report_ref=a["report_ref"],
                )
                for a in attempts
            ],
            candidate=json.loads(row["candidate_json"]) if row["candidate_json"] else None,
            validation=json.loads(row["validation_json"]) if row["validation_json"] else None,
            seed_package=row["seed_package"],
            app_id=row["app_id"],
            latest_sequence=int(row["latest_sequence"]),
        )
