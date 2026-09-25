"""SQLite control store: runs, run events and worker leases.

State transitions and their event are appended in one transaction. Event `sequence` is
per run and monotonically increasing; the table rowid doubles as a global resume cursor
for the shell's SSE stream (an internal ordering aid, not a contract promise).
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from alpha_contracts.runs import (
    TERMINAL_RUN_STATES,
    ExecutionSnapshot,
    Run,
    RunEvent,
    RunOrigin,
    RunOwner,
    RunState,
)
from pydantic import TypeAdapter

_OWNER = TypeAdapter[RunOwner](RunOwner)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    owner_json TEXT NOT NULL,
    origin TEXT NOT NULL,
    state TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    input_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    output_json TEXT,
    terminal_reason TEXT,
    retry_of TEXT,
    latest_sequence INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS runs_state_idx ON runs(state);
CREATE TABLE IF NOT EXISTS run_events (
    cursor INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    sequence INTEGER NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    step_key TEXT,
    UNIQUE(run_id, sequence)
);
CREATE TABLE IF NOT EXISTS worker_leases (
    run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
    profile TEXT NOT NULL,
    pid INTEGER NOT NULL,
    pgid INTEGER NOT NULL,
    scratch_dir TEXT NOT NULL,
    core_instance_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class ConflictError(Exception):
    """A state transition was attempted from an incompatible current state."""


class NotFoundError(Exception):
    pass


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _dt(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _parse_dt(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value.replace("Z", "+00:00"))


class ControlStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO schema_meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            else:
                self._conn.execute("COMMIT")

    # ----- runs -------------------------------------------------------------------------

    def create_run(
        self,
        *,
        workspace_id: str,
        owner: RunOwner,
        origin: RunOrigin,
        snapshot: ExecutionSnapshot,
        input_payload: dict[str, Any],
        retry_of: str | None = None,
    ) -> Run:
        now = utc_now()
        run_id = new_id("run")
        with self.transaction() as conn:
            conn.execute(
                """INSERT INTO runs(run_id, workspace_id, owner_json, origin, state, snapshot_json,
                   input_json, created_at, updated_at, retry_of, latest_sequence)
                   VALUES (?,?,?,?,?,?,?,?,?,?,0)""",
                (
                    run_id,
                    workspace_id,
                    owner.model_dump_json(),
                    origin.value,
                    RunState.QUEUED.value,
                    snapshot.model_dump_json(),
                    json.dumps(input_payload, sort_keys=True),
                    _dt(now),
                    _dt(now),
                    retry_of,
                ),
            )
            self._append_event_locked(conn, run_id, "run.queued", {"origin": origin.value}, now)
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> Run:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(run_id)
        return self._row_to_run(row)

    def get_run_input(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            row = self._conn.execute(
                "SELECT input_json FROM runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(run_id)
        data: dict[str, Any] = json.loads(row["input_json"])
        return data

    def list_runs(self, limit: int = 100) -> list[Run]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def list_runs_in_states(self, states: set[RunState]) -> list[Run]:
        marks = ",".join("?" for _ in states)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT * FROM runs WHERE state IN ({marks})", [s.value for s in states]
            ).fetchall()
        return [self._row_to_run(r) for r in rows]

    def transition(
        self,
        run_id: str,
        *,
        expected_states: set[RunState],
        new_state: RunState,
        event_kind: str,
        payload: dict[str, Any],
        output: dict[str, Any] | None = None,
        terminal_reason: str | None = None,
    ) -> Run:
        """Atomically move a run between states and append the corresponding event.

        Raises ConflictError if the run is not in one of `expected_states`. Terminal runs are
        never mutated into another state (specification section 6)."""
        now = utc_now()
        with self.transaction() as conn:
            row = conn.execute("SELECT state FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise NotFoundError(run_id)
            current = RunState(row["state"])
            if current in TERMINAL_RUN_STATES or current not in expected_states:
                raise ConflictError(f"run {run_id} is {current.value}, expected {expected_states}")
            sets = ["state = ?", "updated_at = ?"]
            params: list[Any] = [new_state.value, _dt(now)]
            if new_state == RunState.RUNNING and current == RunState.QUEUED:
                sets.append("started_at = ?")
                params.append(_dt(now))
            if new_state in TERMINAL_RUN_STATES:
                sets.append("finished_at = ?")
                params.append(_dt(now))
                sets.append("terminal_reason = ?")
                params.append(terminal_reason)
            if output is not None:
                sets.append("output_json = ?")
                params.append(json.dumps(output, sort_keys=True))
            params.append(run_id)
            conn.execute(f"UPDATE runs SET {', '.join(sets)} WHERE run_id = ?", params)
            self._append_event_locked(conn, run_id, event_kind, payload, now)
        return self.get_run(run_id)

    def append_event(self, run_id: str, kind: str, payload: dict[str, Any]) -> RunEvent:
        now = utc_now()
        with self.transaction() as conn:
            if conn.execute("SELECT 1 FROM runs WHERE run_id = ?", (run_id,)).fetchone() is None:
                raise NotFoundError(run_id)
            event = self._append_event_locked(conn, run_id, kind, payload, now)
        return event

    def _append_event_locked(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        kind: str,
        payload: dict[str, Any],
        occurred_at: datetime,
    ) -> RunEvent:
        row = conn.execute(
            "SELECT latest_sequence FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        sequence = int(row["latest_sequence"]) + 1
        event = RunEvent(
            event_id=new_id("evt"),
            run_id=run_id,
            sequence=sequence,
            kind=kind,
            occurred_at=occurred_at,
            payload=payload,
        )
        conn.execute(
            """INSERT INTO run_events(event_id, run_id, sequence, kind, occurred_at, payload_json)
               VALUES (?,?,?,?,?,?)""",
            (
                event.event_id,
                run_id,
                sequence,
                kind,
                _dt(occurred_at),
                json.dumps(payload, sort_keys=True),
            ),
        )
        conn.execute(
            "UPDATE runs SET latest_sequence = ?, updated_at = ? WHERE run_id = ?",
            (sequence, _dt(occurred_at), run_id),
        )
        return event

    def get_events(self, run_id: str, after_sequence: int = 0, limit: int = 500) -> list[RunEvent]:
        with self._lock:
            rows = self._conn.execute(
                """SELECT * FROM run_events WHERE run_id = ? AND sequence > ?
                   ORDER BY sequence LIMIT ?""",
                (run_id, after_sequence, limit),
            ).fetchall()
        return [self._row_to_event(r) for r in rows]

    def events_after_cursor(self, cursor: int, limit: int = 500) -> list[tuple[int, RunEvent]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM run_events WHERE cursor > ? ORDER BY cursor LIMIT ?",
                (cursor, limit),
            ).fetchall()
        return [(int(r["cursor"]), self._row_to_event(r)) for r in rows]

    def latest_cursor(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT MAX(cursor) AS c FROM run_events").fetchone()
        return int(row["c"] or 0)

    # ----- leases -----------------------------------------------------------------------

    def record_lease(
        self,
        *,
        run_id: str,
        profile: str,
        pid: int,
        pgid: int,
        scratch_dir: Path,
        core_instance_id: str,
    ) -> None:
        with self.transaction() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO worker_leases(run_id, profile, pid, pgid, scratch_dir,
                   core_instance_id, created_at) VALUES (?,?,?,?,?,?,?)""",
                (run_id, profile, pid, pgid, str(scratch_dir), core_instance_id, _dt(utc_now())),
            )

    def release_lease(self, run_id: str) -> None:
        with self.transaction() as conn:
            conn.execute("DELETE FROM worker_leases WHERE run_id = ?", (run_id,))

    def list_leases(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM worker_leases").fetchall()
        return [dict(r) for r in rows]

    # ----- mapping ----------------------------------------------------------------------

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> Run:
        return Run(
            run_id=row["run_id"],
            workspace_id=row["workspace_id"],
            owner=_OWNER.validate_json(row["owner_json"]),
            origin=RunOrigin(row["origin"]),
            state=RunState(row["state"]),
            snapshot=ExecutionSnapshot.model_validate_json(row["snapshot_json"]),
            created_at=_parse_dt(row["created_at"]) or utc_now(),
            updated_at=_parse_dt(row["updated_at"]) or utc_now(),
            started_at=_parse_dt(row["started_at"]),
            finished_at=_parse_dt(row["finished_at"]),
            output=json.loads(row["output_json"]) if row["output_json"] else None,
            terminal_reason=row["terminal_reason"],
            retry_of=row["retry_of"],
            latest_sequence=int(row["latest_sequence"]),
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> RunEvent:
        return RunEvent(
            event_id=row["event_id"],
            run_id=row["run_id"],
            sequence=int(row["sequence"]),
            kind=row["kind"],
            occurred_at=_parse_dt(row["occurred_at"]) or utc_now(),
            payload=json.loads(row["payload_json"]),
            step_key=row["step_key"],
        )
