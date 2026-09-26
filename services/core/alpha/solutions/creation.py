"""Creating a result (UX specification §4; Prototype_Scope_and_Acceptance F08).

A creation joins the pieces a person experiences as one step:

    brief (conversation) → acceptance plan → build → checks → activation → App in My workflows

Identities stay stable and separate: the brief keeps its id and revision, the App its
platform-assigned `app_id` (the builder must use it), the build its attempts and reports, the
Version its sealed bytes, the Release its activation record, and the records their own store.
For a local tool with no expanded permissions the creation request itself authorizes building,
checking and activating (UX §4): activation still rechecks bytes, profiles and the expected
current release, but asks for no redundant confirmation.

Only Core changes a creation's state. Nothing about an unfinished creation survives a restart;
it is marked interrupted and the person can start it again.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from alpha_contracts.briefs import Delivery, SolutionBrief
from alpha_contracts.builds import TERMINAL_BUILD_STATES, BuildState
from pydantic import BaseModel

from alpha.assistant.service import AssistantService
from alpha.builds.service import BuildNotReady, BuildService
from alpha.builds.store import BuildRecord
from alpha.capabilities.errors import OperationFailed
from alpha.models.gateway import ModelGateway
from alpha.solutions.planner import AcceptancePlanner, PlanningFailed, app_slug, wants_ui
from alpha.storage.control_store import ControlStore, new_id, utc_now

log = logging.getLogger("alpha.creations")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS creations (
    creation_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    brief_id TEXT NOT NULL,
    brief_revision INTEGER NOT NULL,
    app_id TEXT,
    app_name TEXT,
    state TEXT NOT NULL,
    plan_json TEXT,
    plan_source TEXT,
    build_id TEXT,
    release_id TEXT,
    version_id TEXT,
    failure_json TEXT,
    history_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

TERMINAL = {"active", "failed", "cancelled"}

# Plain-language stage for each build state (UX §4: understanding, building, checking, ready,
# or needs your input).
_BUILD_STAGE = {
    BuildState.QUEUED: ("building", "Waiting for the builder"),
    BuildState.BUILDING: ("building", "Building it"),
    BuildState.VALIDATING: ("checking", "Checking that it works"),
    BuildState.REPAIRING: ("building", "Fixing what the checks found"),
    BuildState.READY: ("activating", "Getting it ready to use"),
}


class CreationRecord(BaseModel):
    creation_id: str
    conversation_id: str
    brief_id: str
    brief_revision: int
    app_id: str | None
    app_name: str | None
    state: str
    stage: str
    label: str
    detail: str | None
    build_id: str | None
    release_id: str | None
    version_id: str | None
    plan_source: str | None
    progress: dict[str, Any]
    result: dict[str, Any] | None
    failure: dict[str, Any] | None
    history: list[dict[str, Any]]
    created_at: str
    updated_at: str


class CreationRefused(Exception):
    pass


@dataclass(frozen=True)
class CreationRoutes:
    planner: str
    builder: str


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def build_instructions(brief: SolutionBrief, *, with_ui: bool, app_name: str) -> str:
    """What the builder is told about the person's goal, in the brief's own words."""
    lines = [
        f"App name for the person: {app_name}",
        "",
        f"What success looks like: {brief.success_summary}",
    ]
    if brief.primary_journey:
        lines += ["", "How the person will use it:"]
        lines += [f"- {s.action} -> {s.expected_result}" for s in brief.primary_journey]
    if brief.data_needs:
        lines += ["", "What it keeps:"]
        for need in brief.data_needs:
            fields = ", ".join(
                f"{f.name} ({f.kind}{', required' if f.required else ''})" for f in need.fields
            )
            lines.append(f"- collection {need.collection}: {need.purpose}. Fields: {fields}")
    if brief.actions:
        lines += ["", "What it does:"]
        for action in brief.actions:
            inputs = ", ".join(action.inputs) or "none"
            outputs = ", ".join(action.outputs) or "none"
            lines.append(
                f"- action {action.id}: {action.description} (inputs: {inputs}; outputs: {outputs})"
            )
    if brief.constraints:
        lines += ["", "Constraints:"] + [f"- {c}" for c in brief.constraints]
    if brief.assumptions:
        lines += ["", "Agreed assumptions:"] + [f"- {a.text}" for a in brief.assumptions]
    if brief.unavailable_capabilities:
        lines += [
            "",
            "Not available on this Mac yet (do not attempt these; where the person would "
            "expect them, say plainly in the App that they are not connected): "
            + ", ".join(brief.unavailable_capabilities),
        ]
    lines += [
        "",
        "PLAN.md is what Alpha will check. Where it names an action, input, collection, field "
        "or label differently from the notes above, use PLAN.md's name.",
        "",
        "Build a screen for this App (ui/src/main.tsx) using the labels PLAN.md names."
        if with_ui
        else "This App has no custom screen: leave ui out of app.yaml. Alpha shows one form for "
        "primary_action, the action the person runs to get the result; set it, give it a clear "
        "title and description, mark pasted or long text inputs multiline: true, and return "
        "readable data (lists of entries become tables). Keep helper steps internal: do not list "
        "an action as manual if it needs another step's output.",
    ]
    return "\n".join(lines)


class CreationService:
    def __init__(
        self,
        store: ControlStore,
        assistant: AssistantService,
        builds: BuildService,
        planner: AcceptancePlanner,
        gateway: ModelGateway,
        routes: CreationRoutes,
        *,
        poll_seconds: float = 0.5,
    ) -> None:
        self._store = store
        self._assistant = assistant
        self._builds = builds
        self._planner = planner
        self._gateway = gateway
        self._routes = routes
        self._poll = poll_seconds
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()
        store.execute_script(_SCHEMA)

    # ----- public ------------------------------------------------------------------------

    def start(self, conversation_id: str, *, builder_hint: str | None = None) -> CreationRecord:
        conversation = self._assistant.get(conversation_id)
        brief = conversation.current_brief
        if conversation.state != "briefed" or brief is None:
            raise CreationRefused(
                "the request is not ready to build yet: answer the open questions first"
            )
        if brief.delivery is not Delivery.APP:
            raise CreationRefused(
                "only reusable Apps can be created here; one-off Tasks arrive in a later release"
            )
        for existing in self.list_for_conversation(conversation_id):
            if existing.state not in TERMINAL and existing.brief_revision == brief.revision:
                return existing  # already being created from this brief revision
        creation_id = new_id("create")
        now = _now()
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO creations(creation_id, conversation_id, brief_id, brief_revision,
                   state, history_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    creation_id,
                    conversation_id,
                    brief.id,
                    brief.revision,
                    "planning",
                    "[]",
                    now,
                    now,
                ),
            )
        self._note(creation_id, "planning", "Writing the checks it must pass")
        threading.Thread(
            target=self._run,
            args=(creation_id, brief, builder_hint),
            name=f"creation-{creation_id}",
            daemon=True,
        ).start()
        return self.get(creation_id)

    def get(self, creation_id: str) -> CreationRecord:
        rows = self._store.query("SELECT * FROM creations WHERE creation_id = ?", (creation_id,))
        if not rows:
            raise OperationFailed("not_found", f"no creation {creation_id!r}")
        return self._record(rows[0])

    def list_for_conversation(self, conversation_id: str) -> list[CreationRecord]:
        rows = self._store.query(
            "SELECT * FROM creations WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        return [self._record(r) for r in rows]

    def list_recent(self, limit: int = 50) -> list[CreationRecord]:
        rows = self._store.query(
            "SELECT * FROM creations ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._record(r) for r in rows]

    def cancel(self, creation_id: str) -> CreationRecord:
        """Stop a creation. Accepted only before it starts switching on, and decided in the same
        transaction that reads the state, so an accepted Stop always prevents a new release.
        Once switching on has begun the creation completes or fails, and says which (F13)."""
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT state, build_id FROM creations WHERE creation_id = ?", (creation_id,)
            ).fetchone()
            if row is None:
                raise OperationFailed("not_found", f"no creation {creation_id!r}")
            if row["state"] in TERMINAL:
                raise OperationFailed("conflict", f"the creation is already {row['state']}")
            if row["state"] == "activating":
                raise OperationFailed(
                    "conflict", "it is already being switched on and can no longer be stopped"
                )
            self._finish_locked(
                conn, creation_id, "cancelled", None, {"reason": "cancelled_by_user"}
            )
            build_id = row["build_id"]
        with self._lock:
            self._cancelled.add(creation_id)
        if build_id:
            try:
                self._builds.cancel(build_id)
            except Exception:
                pass  # already finished; nothing of it is switched on
        return self.get(creation_id)

    def reconcile_on_startup(self) -> list[str]:
        """Unfinished creations cannot continue after a restart (their builds were interrupted
        too); mark them so the person can start again."""
        rows = self._store.query(
            "SELECT creation_id FROM creations WHERE state NOT IN ('active','failed','cancelled')"
        )
        for row in rows:
            self._finish(
                row["creation_id"],
                "failed",
                None,
                {
                    "reason": "core_restarted",
                    "message": "Alpha restarted while this was being made. Start it again.",
                    "next_step": "retry",
                },
            )
        return [r["creation_id"] for r in rows]

    # ----- the creation itself ----------------------------------------------------------

    def _run(self, creation_id: str, brief: SolutionBrief, builder_hint: str | None) -> None:
        try:
            self._create(creation_id, brief, builder_hint)
        except Exception as exc:  # never leave a creation stuck
            log.exception("creation %s failed inside Core", creation_id)
            self._finish(
                creation_id,
                "failed",
                None,
                {
                    "reason": "platform_error",
                    "message": "Something went wrong inside Alpha. Try again.",
                    "error": f"{type(exc).__name__}: {exc}"[:300],
                    "next_step": "retry",
                },
            )

    def _create(self, creation_id: str, brief: SolutionBrief, builder_hint: str | None) -> None:
        try:
            planned = self._planner.plan(
                brief, self._gateway.route(self._routes.planner), creation_id
            )
        except PlanningFailed as exc:
            self._finish(
                creation_id,
                "failed",
                None,
                {
                    "reason": "plan_unavailable",
                    "message": "Alpha couldn't work out how to check this request, so nothing "
                    "was made.",
                    "failed_checks": exc.problems or [str(exc)],
                    "next_step": "retry",
                },
            )
            return
        if self._stopped(creation_id):
            return
        app_id = app_slug(planned.app_name, creation_id.removeprefix("create_")[:6])
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE creations SET app_id = ?, app_name = ?, plan_json = ?, plan_source = ?,
                   updated_at = ? WHERE creation_id = ?""",
                (
                    app_id,
                    planned.app_name,
                    planned.plan.model_dump_json(),
                    planned.source,
                    _now(),
                    creation_id,
                ),
            )
        goal = brief.goal
        if builder_hint and self._routes.builder == "fake":
            goal = f"fake:{builder_hint}"  # control fixture only
        build = self._builds.submit(
            goal=goal,
            plan=planned.plan,
            instructions=build_instructions(
                brief, with_ui=wants_ui(brief), app_name=planned.app_name
            ),
            route_id=self._routes.builder,
            app_id=app_id,
        )
        with self._store.transaction() as conn:
            moved = conn.execute(
                "UPDATE creations SET build_id = ?, state = ?, updated_at = ?"
                " WHERE creation_id = ? AND state NOT IN ('active', 'failed', 'cancelled')",
                (build.build_id, "building", _now(), creation_id),
            ).rowcount
            if not moved:  # stopped while the build was being submitted
                conn.execute(
                    "UPDATE creations SET build_id = ? WHERE creation_id = ?",
                    (build.build_id, creation_id),
                )
        if not moved:
            try:
                self._builds.cancel(build.build_id)
            except Exception:
                pass
            return
        self._note(creation_id, "building", "Building it")
        final = self._wait_for_build(creation_id, build.build_id)
        if final is None:
            return  # cancelled
        if final.state is not BuildState.READY:
            self._finish(creation_id, "failed", None, self._build_failure(final))
            return
        if not self._claim_activation(creation_id):
            return  # stopped before switching on: nothing is switched on
        try:
            activated = self._builds.activate(
                final.build_id, expected_release_id=None, creation_id=creation_id
            )
        except (OperationFailed, BuildNotReady) as exc:
            message = exc.message if isinstance(exc, OperationFailed) else str(exc)
            self._finish(
                creation_id,
                "failed",
                None,
                {
                    "reason": "activation_refused",
                    "message": f"It passed its checks but could not be switched on: {message}",
                    "next_step": "retry",
                },
            )
            return
        self._finish(creation_id, "active", activated, None)

    def _wait_for_build(self, creation_id: str, build_id: str) -> BuildRecord | None:
        last_state: BuildState | None = None
        while True:
            if self._stopped(creation_id):
                return None
            build = self._builds.get(build_id)
            if build.state is not last_state:
                last_state = build.state
                stage, label = _BUILD_STAGE.get(build.state, ("building", "Building it"))
                if build.state not in TERMINAL_BUILD_STATES:
                    self._note(creation_id, stage, label)
            if build.state in TERMINAL_BUILD_STATES:
                return build
            time.sleep(self._poll)

    @staticmethod
    def _build_failure(build: BuildRecord) -> dict[str, Any]:
        """What went wrong, in words the person can act on (UX §4: answer, retry within
        budget, revise scope or keep the current version)."""
        reason = build.terminal_reason or "failed"
        # A required check that did not pass (failed, or could not run) blocks readiness.
        failed_checks = [
            c.get("summary", "")
            for c in (build.validation or {}).get("checks", [])
            if c.get("required", True) and c.get("status") != "passed"
        ][:3]
        if build.failure_category == "dependency_unsupported":
            message = (
                "It needs a software package Alpha does not have yet, so it was not made. "
                "Try describing it without that part."
            )
            next_step = "revise"
        elif reason in ("repair_limit_reached", "total_deadline_exceeded", "cost_limit_reached"):
            message = (
                f"It was built {len(build.attempts)} time(s) but did not pass its checks within "
                "the limits."
            )
            next_step = "revise"
        elif build.state is BuildState.CANCELLED:
            message = "The build was cancelled."
            next_step = "retry"
        else:
            message = "The builder could not finish. Try again in a moment."
            next_step = "retry"
        return {
            "reason": reason,
            "category": build.failure_category,
            "message": message,
            "failed_checks": failed_checks,
            "next_step": next_step,
            "attempts": len(build.attempts),
        }

    # ----- bookkeeping --------------------------------------------------------------------

    def _stopped(self, creation_id: str) -> bool:
        with self._lock:
            return creation_id in self._cancelled

    def _note(self, creation_id: str, stage: str, label: str) -> None:
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT state, history_json FROM creations WHERE creation_id = ?", (creation_id,)
            ).fetchone()
            if row is None or row["state"] in TERMINAL:
                return
            history = json.loads(row["history_json"])
            if history and history[-1]["stage"] == stage and history[-1]["label"] == label:
                return
            history.append({"stage": stage, "label": label, "at": _now()})
            conn.execute(
                """UPDATE creations SET state = ?, history_json = ?, updated_at = ?
                   WHERE creation_id = ?""",
                (stage, json.dumps(history), _now(), creation_id),
            )

    def _claim_activation(self, creation_id: str) -> bool:
        """Move to `activating` unless the creation was stopped. The same transaction boundary
        as `cancel` decides which one wins."""
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT state, history_json FROM creations WHERE creation_id = ?", (creation_id,)
            ).fetchone()
            if row is None or row["state"] in TERMINAL or row["state"] == "activating":
                return False
            history = json.loads(row["history_json"])
            history.append(
                {"stage": "activating", "label": "Getting it ready to use", "at": _now()}
            )
            conn.execute(
                """UPDATE creations SET state = 'activating', history_json = ?, updated_at = ?
                   WHERE creation_id = ?""",
                (json.dumps(history), _now(), creation_id),
            )
            return True

    def _finish(
        self,
        creation_id: str,
        state: str,
        activated: dict[str, Any] | None,
        failure: dict[str, Any] | None,
    ) -> None:
        with self._store.transaction() as conn:
            self._finish_locked(conn, creation_id, state, activated, failure)

    def _finish_locked(
        self,
        conn: Any,
        creation_id: str,
        state: str,
        activated: dict[str, Any] | None,
        failure: dict[str, Any] | None,
    ) -> None:
        row = conn.execute(
            "SELECT state, history_json FROM creations WHERE creation_id = ?", (creation_id,)
        ).fetchone()
        if row is None or row["state"] in TERMINAL:
            return
        history = json.loads(row["history_json"])
        label = {"active": "Ready to use", "failed": "Not made", "cancelled": "Cancelled"}[state]
        history.append({"stage": state, "label": label, "at": _now()})
        conn.execute(
            """UPDATE creations SET state = ?, release_id = ?, version_id = ?,
               failure_json = ?, history_json = ?, updated_at = ? WHERE creation_id = ?""",
            (
                state,
                activated["release_id"] if activated else None,
                activated["version_id"] if activated else None,
                json.dumps(failure) if failure else None,
                json.dumps(history),
                _now(),
                creation_id,
            ),
        )

    def _record(self, row: Any) -> CreationRecord:
        history = json.loads(row["history_json"])
        latest = history[-1] if history else {"stage": row["state"], "label": row["state"]}
        progress: dict[str, Any] = {}
        result: dict[str, Any] | None = None
        build: BuildRecord | None = None
        if row["build_id"]:
            try:
                build = self._builds.get(row["build_id"])
            except Exception:
                build = None
        if build is not None:
            checks = [
                e.payload
                for e in self._builds.events(build.build_id)
                if e.kind == "validation.check"
            ]
            current = [c for c in checks if c.get("status") != "skipped"]
            progress = {
                "attempt": len(build.attempts),
                "max_attempts": 1 + build.budget.max_repair_attempts,
                "checks_run": len(current),
                "checks_failed": sum(1 for c in current if c.get("status") == "failed"),
            }
            if row["state"] == "active" and build.candidate:
                report = build.validation or {}
                required = [c for c in report.get("checks", []) if c.get("required")]
                result = {
                    "app_id": row["app_id"],
                    "name": build.candidate.get("name"),
                    "actions": build.candidate.get("actions"),
                    "has_ui": build.candidate.get("has_ui"),
                    "checks_passed": sum(1 for c in required if c.get("status") == "passed"),
                    # Screenshots the checks took with sample data: a labelled preview, never
                    # the person's own records.
                    "preview_images": _preview_images(build, report),
                    "attempts": len(build.attempts),
                }
        detail = None
        if row["state"] == "building" and progress.get("attempt", 0) > 1:
            detail = f"Attempt {progress['attempt']} of {progress['max_attempts']}"
        return CreationRecord(
            creation_id=row["creation_id"],
            conversation_id=row["conversation_id"],
            brief_id=row["brief_id"],
            brief_revision=int(row["brief_revision"]),
            app_id=row["app_id"],
            app_name=row["app_name"],
            state=row["state"],
            stage=latest["stage"],
            label=latest["label"],
            detail=detail,
            build_id=row["build_id"],
            release_id=row["release_id"],
            version_id=row["version_id"],
            plan_source=row["plan_source"],
            progress=progress,
            result=result,
            failure=json.loads(row["failure_json"]) if row["failure_json"] else None,
            history=history,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _preview_images(build: BuildRecord, report: dict[str, Any]) -> list[dict[str, str]]:
    candidate = build.candidate or {}
    attempt = candidate.get("attempt_number")
    wanted = ("primary-1280", "populated-1280", "populated-768", "error-save")
    found = {
        evidence.rsplit("/", 1)[-1].removesuffix(".png"): evidence
        for check in report.get("checks", [])
        if check.get("stage") == "ui"
        for evidence in check.get("evidence", [])
    }
    return [
        {
            "name": name,
            "url": f"/api/builds/{build.build_id}/attempts/{attempt}/{found[name]}",
        }
        for name in wanted
        if name in found and attempt
    ]
