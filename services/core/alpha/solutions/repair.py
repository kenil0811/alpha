"""Self-healing: a failed run of a module is diagnosed, and when the fault is in the module's
own code Alpha fixes it (one edit call through the quick path, validated and switched on with
the data kept), runs the failed action again with the same input, and says in plain words what
happened. Triggered by the failure itself, or by the person asking in a session; the loop sees
the failures and their causes as facts either way.

Limits keep it honest: one attempt per cause per version, so a fix that does not hold is
reported rather than retried forever; faults outside the module (the platform, the web, the
model service, a refusal of bad input) are named, never "fixed".
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from alpha_contracts.apps import Invocable
from alpha_contracts.runs import TERMINAL_RUN_STATES, AppOwner, Run, RunOrigin, RunState

from alpha.capabilities.errors import OperationFailed
from alpha.storage.control_store import ControlStore, new_id, utc_now

log = logging.getLogger("alpha.repair")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS repairs (
    repair_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    version_id TEXT,
    run_id TEXT NOT NULL,
    action_id TEXT,
    cause TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL,
    creation_id TEXT,
    rerun_run_id TEXT,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS repairs_app ON repairs(app_id, created_at);
"""

# Where a failure comes from. Only module_code is Alpha's to fix.
MODULE_CODE = "module_code"
PLATFORM = "platform"
OUTSIDE = "outside"
REFUSAL = "refusal"
UNKNOWN = "unknown"

OUTSIDE_CODES = {"unavailable", "timed_out", "timeout_exceeded", "limit_exceeded", "forbidden"}
REFUSAL_EXCEPTIONS = {"ValueError", "InvalidValue"}
FIX_WAIT_SECONDS = 240.0
RERUN_WAIT_SECONDS = 90.0
RECENT_DAYS = 3


@dataclass(frozen=True)
class Diagnosis:
    run_id: str
    app_id: str
    action_id: str
    kind: str
    # A stable name for the fault: action, exception and where in the module's code.
    cause: str
    exception: str | None
    technical: str
    traceback: str
    where: str | None  # "handlers.py line 551"
    said: str  # what the person reads
    input: dict[str, Any]
    version_id: str | None
    at: str


class RepairService:
    def __init__(
        self,
        store: ControlStore,
        *,
        registry: Any,
        creations: Any,
        runs: Any,
        run_lookup: Callable[[str], Run] | None = None,
        names: Callable[[str], str | None] | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._creations = creations
        self._runs = runs
        self._run_lookup = run_lookup or store.get_run
        self._names = names or (lambda _app_id: None)
        self._lock = threading.Lock()
        self._busy: set[str] = set()
        store.execute_script(_SCHEMA)

    # ----- reading -----------------------------------------------------------------------

    def diagnose(self, run_id: str) -> Diagnosis | None:
        """What went wrong in a failed run, and whose fault it is. None for a run that did
        not fail (or is not a module's)."""
        try:
            run = self._run_lookup(run_id)
        except Exception:
            return None
        if run.state is not RunState.FAILED or not isinstance(run.owner, AppOwner):
            return None
        error = self._error_of(run)
        code = str(error.get("code") or run.terminal_reason or "")
        exception = error.get("exception")
        technical = str(error.get("technical") or error.get("message") or "")
        traceback = str(error.get("traceback") or "")
        where = _where(traceback)
        app_id, action_id = run.owner.app_id, run.owner.action_id
        if code == "handler_exception":
            if exception in REFUSAL_EXCEPTIONS:
                kind = REFUSAL
            elif where is not None:
                kind = MODULE_CODE
            else:
                kind = PLATFORM
        elif code in OUTSIDE_CODES:
            kind = OUTSIDE
        elif code in ("output_schema_violation",):
            kind = MODULE_CODE
        elif code:
            kind = PLATFORM
        else:
            kind = UNKNOWN
        cause = f"{action_id}:{exception or code}:{where or '?'}"
        try:
            payload = self._store.get_run_input(run_id)
        except Exception:
            payload = {}
        return Diagnosis(
            run_id=run_id,
            app_id=app_id,
            action_id=action_id,
            kind=kind,
            cause=cause,
            exception=str(exception) if exception else None,
            technical=technical[:600],
            traceback=traceback[-4000:],
            where=where,
            said=self._said(kind, action_id, app_id, where, exception, technical, code),
            input=payload if isinstance(payload, dict) else {},
            version_id=getattr(run.snapshot, "version_id", None),
            at=_dt(run.created_at),
        )

    def recent(self, app_id: str, limit: int = 5) -> list[dict[str, Any]]:
        """Recent failures of a module with their diagnosis and what Alpha did about them,
        newest first (for the loop's facts and the module's Activity)."""
        found: list[dict[str, Any]] = []
        cutoff = utc_now().timestamp() - RECENT_DAYS * 86400
        for run in self._store.list_runs(limit=300):
            if run.state is not RunState.FAILED or not isinstance(run.owner, AppOwner):
                continue
            if run.owner.app_id != app_id or run.created_at.timestamp() < cutoff:
                continue
            diagnosis = self.diagnose(run.run_id)
            if diagnosis is None:
                continue
            found.append(self._entry(diagnosis))
            if len(found) >= limit:
                break
        return found

    def list_repairs(self, app_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._store.query(
            "SELECT * FROM repairs WHERE app_id = ? ORDER BY created_at DESC LIMIT ?",
            (app_id, limit),
        )
        return [dict(r) for r in rows]

    def facts(self, app_ids: list[str], limit: int = 5) -> list[str]:
        """Lines for the loop: each recent failure, its cause in plain words, and where the
        fix stands, so "fix it" and "why did it fail" are answered from what happened."""
        lines: list[str] = []
        for app_id in app_ids:
            name = self._names(app_id) or app_id
            for entry in self.recent(app_id, limit=3):
                when = entry["at"][:16].replace("T", " ")
                line = f"FAILED {when} in {name} (run {entry['run_id']}): {entry['said']}"
                repair = entry.get("repair")
                if repair is None and entry["kind"] == MODULE_CODE:
                    line += " Alpha can fix this (a fix step)."
                elif repair is not None:
                    line += f" {repair['summary']}"
                lines.append(line)
                if len(lines) >= limit:
                    return lines
        return lines

    # ----- fixing ------------------------------------------------------------------------

    def consider(self, run_id: str) -> None:
        """A run just finished: if it failed in the module's own code and nothing has been
        tried for that cause on this version, fix it in the background."""
        diagnosis = self.diagnose(run_id)
        if diagnosis is None or diagnosis.kind != MODULE_CODE:
            return
        if self._tried(diagnosis) is not None:
            return
        threading.Thread(
            target=self._repair_quietly, args=(run_id,), name=f"repair-{run_id[-6:]}", daemon=True
        ).start()

    def _repair_quietly(self, run_id: str) -> None:
        try:
            self.repair(run_id)
        except Exception:
            log.exception("repair of %s failed inside Alpha", run_id)

    def repair(self, run_id: str) -> dict[str, Any]:
        """Fix the cause of a failed run, switch the fix on and run the action again. Blocks
        (bounded). Returns what happened in a form the loop and the person can read."""
        diagnosis = self.diagnose(run_id)
        if diagnosis is None:
            return {
                "state": "skipped",
                "message": "That run did not fail, so there is nothing to fix.",
            }
        name = self._names(diagnosis.app_id) or diagnosis.app_id
        if diagnosis.kind != MODULE_CODE:
            return {"state": "skipped", "kind": diagnosis.kind, "message": diagnosis.said}
        earlier = self._tried(diagnosis)
        if earlier is not None and earlier["state"] != "fixing":
            return {
                "state": "already_tried",
                "repair_id": earlier["repair_id"],
                "message": f"Alpha already tried this on the current version of {name}: "
                f"{earlier['summary']} Ask for a change if you want it done differently.",
            }
        with self._lock:
            if diagnosis.app_id in self._busy:
                return {"state": "busy", "message": f"A fix of {name} is already under way."}
            self._busy.add(diagnosis.app_id)
        try:
            return self._repair(diagnosis, name)
        finally:
            with self._lock:
                self._busy.discard(diagnosis.app_id)

    def _repair(self, diagnosis: Diagnosis, name: str) -> dict[str, Any]:
        repair_id = new_id("repair")
        now = _dt(utc_now())
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO repairs(repair_id, app_id, version_id, run_id, action_id, cause,
                   kind, state, summary, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    repair_id,
                    diagnosis.app_id,
                    diagnosis.version_id,
                    diagnosis.run_id,
                    diagnosis.action_id,
                    diagnosis.cause,
                    diagnosis.kind,
                    "fixing",
                    "Alpha is fixing this.",
                    now,
                    now,
                ),
            )
        try:
            creation = self._creations.start_repair(
                diagnosis.app_id,
                evidence(diagnosis, self._action_title(diagnosis)),
                run_id=diagnosis.run_id,
            )
        except Exception as exc:
            return self._settle(repair_id, "not_fixed", f"Alpha could not start a fix: {exc}")
        creation_id = str(creation.creation_id)
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE repairs SET creation_id = ? WHERE repair_id = ?", (creation_id, repair_id)
            )
        final = self._wait_creation(creation_id)
        if final is None:
            return self._settle(
                repair_id, "not_fixed", "The fix took too long; Alpha gave up on it."
            )
        if final.state != "active":
            why = str((final.failure or {}).get("message") or "the edit did not hold together")
            return self._settle(repair_id, "not_fixed", f"Alpha could not fix this: {why}")
        summary = str((final.result or {}).get("summary") or "the module's code was corrected")
        rerun = self._rerun(diagnosis)
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE repairs SET rerun_run_id = ? WHERE repair_id = ?",
                (rerun.get("run_id"), repair_id),
            )
        if rerun.get("state") == "succeeded":
            return self._settle(
                repair_id,
                "fixed",
                f"Alpha fixed it ({summary}) and ran {self._action_title(diagnosis)} again: "
                f"{rerun.get('said') or 'it succeeded'}",
                rerun=rerun,
                creation_id=creation_id,
            )
        return self._settle(
            repair_id,
            "not_fixed",
            f"Alpha changed the code ({summary}) but {self._action_title(diagnosis)} still did "
            f"not go through: {rerun.get('said') or rerun.get('state')}",
            rerun=rerun,
            creation_id=creation_id,
        )

    # ----- pieces ------------------------------------------------------------------------

    def _tried(self, diagnosis: Diagnosis) -> dict[str, Any] | None:
        rows = self._store.query(
            "SELECT * FROM repairs WHERE app_id = ? AND cause = ? AND version_id IS ?"
            " ORDER BY created_at DESC LIMIT 1",
            (diagnosis.app_id, diagnosis.cause, diagnosis.version_id),
        )
        if rows:
            return dict(rows[0])
        # A fix that went live changes the version; the same cause on the new version means
        # the fix did not hold, and that counts as tried too.
        rows = self._store.query(
            "SELECT * FROM repairs WHERE app_id = ? AND cause = ?"
            " AND state IN ('fixed', 'not_fixed') AND updated_at > ?"
            " ORDER BY created_at DESC LIMIT 1",
            (diagnosis.app_id, diagnosis.cause, diagnosis.at),
        )
        return dict(rows[0]) if rows else None

    def _settle(self, repair_id: str, state: str, summary: str, **extra: Any) -> dict[str, Any]:
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE repairs SET state = ?, summary = ?, updated_at = ? WHERE repair_id = ?",
                (state, summary[:600], _dt(utc_now()), repair_id),
            )
        log.info("repair %s: %s: %s", repair_id, state, summary)
        return {"state": state, "repair_id": repair_id, "message": summary, **extra}

    def _wait_creation(self, creation_id: str) -> Any:
        deadline = time.monotonic() + FIX_WAIT_SECONDS
        while time.monotonic() < deadline:
            record = self._creations.get(creation_id)
            if record.state in ("active", "failed", "cancelled"):
                return record
            time.sleep(0.5)
        return None

    def _rerun(self, diagnosis: Diagnosis) -> dict[str, Any]:
        """The failed action again, with the same input, on the fixed version."""
        try:
            source = self._registry.current(diagnosis.app_id).source
            action = source.action(diagnosis.action_id)
        except Exception:
            action = None
        if action is None:
            return {"state": "skipped", "said": "the action no longer exists"}
        origin = RunOrigin.TRIGGER if Invocable.TRIGGER in action.invocable_from else None
        if origin is None:
            for candidate, allowed in (
                (RunOrigin.ASSISTANT, Invocable.ASSISTANT),
                (RunOrigin.USER, Invocable.MANUAL),
                (RunOrigin.UI, Invocable.UI),
            ):
                if allowed in action.invocable_from:
                    origin = candidate
                    break
        if origin is None:
            return {"state": "skipped", "said": "the action cannot be started by Alpha"}
        try:
            run = self._runs.invoke(
                diagnosis.app_id, diagnosis.action_id, diagnosis.input, origin=origin
            )
        except OperationFailed as exc:
            return {"state": "failed", "said": exc.message}
        deadline = time.monotonic() + RERUN_WAIT_SECONDS
        while time.monotonic() < deadline:
            final = self._run_lookup(run.run_id)
            if final.state in TERMINAL_RUN_STATES:
                if final.state is RunState.SUCCEEDED:
                    return {
                        "state": "succeeded",
                        "run_id": run.run_id,
                        "said": _said_output(final.output),
                    }
                again = self.diagnose(run.run_id)
                return {
                    "state": "failed",
                    "run_id": run.run_id,
                    "said": again.said if again else final.state.value,
                }
            time.sleep(0.3)
        return {"state": "running", "run_id": run.run_id, "said": "it is still running"}

    def _error_of(self, run: Run) -> dict[str, Any]:
        try:
            events = self._store.get_events(run.run_id)
        except Exception:
            return {}
        for event in reversed(events):
            if event.kind == "run.failed":
                payload = event.payload or {}
                error = payload.get("error")
                if isinstance(error, dict):
                    return error
                return payload
        return {}

    def _action_title(self, diagnosis: Diagnosis) -> str:
        try:
            action = self._registry.current(diagnosis.app_id).source.action(diagnosis.action_id)
            return str(action.title) if action else diagnosis.action_id
        except Exception:
            return diagnosis.action_id

    def _said(
        self,
        kind: str,
        action_id: str,
        app_id: str,
        where: str | None,
        exception: Any,
        technical: str,
        code: str,
    ) -> str:
        title = action_id
        try:
            action = self._registry.current(app_id).source.action(action_id)
            title = str(action.title) if action else action_id
        except Exception:
            pass
        detail = technical.split("\n")[0][:220]
        if kind == MODULE_CODE:
            return f"{title} stopped in the module's own code ({where}): {detail}."
        if kind == REFUSAL:
            return f"{title} refused the input: {detail}."
        if kind == OUTSIDE:
            return (
                f"{title} could not finish because of something outside Alpha ({code}): "
                f"{detail or 'no detail'}."
            )
        if kind == PLATFORM:
            return (
                f"{title} hit a problem inside Alpha itself ({exception or code}): {detail}. "
                "This is not the module's fault."
            )
        return f"{title} failed ({code or 'unknown reason'}): {detail or 'no detail'}."

    def _entry(self, diagnosis: Diagnosis) -> dict[str, Any]:
        rows = self._store.query(
            "SELECT * FROM repairs WHERE run_id = ? ORDER BY created_at DESC LIMIT 1",
            (diagnosis.run_id,),
        )
        repair = dict(rows[0]) if rows else None
        if repair is None:
            tried = self._tried(diagnosis)
            if tried is not None:
                repair = tried
        return {
            "run_id": diagnosis.run_id,
            "app_id": diagnosis.app_id,
            "action_id": diagnosis.action_id,
            "at": diagnosis.at,
            "kind": diagnosis.kind,
            "where": diagnosis.where,
            "said": diagnosis.said,
            "repair": {
                "repair_id": repair["repair_id"],
                "state": repair["state"],
                "summary": repair["summary"],
            }
            if repair
            else None,
        }


def evidence(diagnosis: Diagnosis, action_title: str) -> str:
    """REPAIR.md for the edit call: what ran, with what, and exactly how it failed."""
    parts = [
        f"A real run of the action `{diagnosis.action_id}` ({action_title}) failed in this "
        "module's own code. Fix the cause with the smallest correct change; keep the module's "
        "behaviour otherwise as it is. The same action will be run again with the same input "
        "right after your fix, so the fix must make that run succeed.",
        "",
        f"INPUT: {json.dumps(diagnosis.input, default=str)[:1500]}",
        f"ERROR: {diagnosis.technical}",
        f"WHERE: {diagnosis.where or 'unknown'}",
    ]
    if diagnosis.traceback:
        parts += ["", "TRACEBACK (most recent call last):", diagnosis.traceback]
    return "\n".join(parts)


_FRAME = re.compile(r'File "([^"]+)", line (\d+)')


def _where(traceback: str) -> str | None:
    """The last frame inside the module's own code (under src/app_code), as a person reads it."""
    last: str | None = None
    for path, line in _FRAME.findall(traceback):
        if "/src/app_code/" in path or "/app_code/" in path:
            last = f"{path.rsplit('/', 1)[-1]} line {line}"
    return last


def _said_output(output: Any) -> str:
    if isinstance(output, dict):
        message = output.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()[:200]
        text = json.dumps(output, default=str)
        return text[:200]
    return "it succeeded"


def _dt(value: Any) -> str:
    try:
        return str(value.isoformat()).replace("+00:00", "Z")
    except AttributeError:
        return str(value)
