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
import shutil
import stat
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_contracts.briefs import Delivery, SolutionBrief
from alpha_contracts.builds import TERMINAL_BUILD_STATES, BuildState
from pydantic import BaseModel

from alpha.assistant.service import AssistantService
from alpha.builds.quick_edit import (
    QUICK_CHANGE_SYSTEM,
    QUICK_MAX_BYTES,
    apply_edits,
    fake_quick_change,
    quick_change_prompt,
    quick_change_schema,
    read_package_files,
)
from alpha.builds.service import BuildNotReady, BuildService
from alpha.builds.store import BuildRecord
from alpha.capabilities.errors import OperationFailed
from alpha.models.gateway import ModelGateway
from alpha.solutions.conventions import DEFAULT_CONVENTIONS
from alpha.solutions.planner import AcceptancePlanner, PlanningFailed, app_slug, wants_ui
from alpha.solutions.registry import SEALED_ARTEFACTS, Activation, AppRegistry
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
    updated_at TEXT NOT NULL,
    change_of TEXT,
    result_json TEXT
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
    # Set when this creation changes an App that already exists (rebuilt in place, data kept).
    change_of: str | None = None
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


CHANGE_NOTE = (
    "THIS IS A CHANGE to an App the person already uses. package/ is a writable copy of its "
    "current version, not the template. Keep everything that already works: every collection "
    "and field (same names and kinds; any field you add must be optional), every action id, the "
    "declared screen and schedules. Change only what the goal and PLAN.md ask for, and make "
    "sure records saved by the current version still load and display."
)


def build_instructions(
    brief: SolutionBrief, *, with_ui: bool, app_name: str, change: bool = False
) -> str:
    """What the builder is told about the person's goal, in the brief's own words."""
    lines = [
        f"App name for the person: {app_name}",
        "",
        f"What success looks like: {brief.success_summary}",
    ]
    if change:
        lines = [CHANGE_NOTE, ""] + lines
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
    if brief.recurrence is not None:
        lines += [
            "",
            f"It runs on its own ({brief.recurrence.type}): {brief.recurrence.description}",
            "Declare this in app.yaml under schedules: (every_minutes or daily_at) calling an "
            "action whose invocable_from includes trigger, and list the schedules capability. "
            "Alpha runs it while it is open and shows the last and next run with an on/off "
            "switch; do not build your own timer or run history.",
        ]
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
        "Declare the App's screen in app.yaml (screen: tabs of blocks) using the labels PLAN.md "
        "names: the quick entry's placeholder, column titles and tab names are what the person "
        "sees. Lay the tabs and blocks out by the MODULE CONVENTIONS below: the data first, a "
        "quick entry above it only when typing a line is the main way in, forms after, then "
        "metrics and a trend. Write a custom ui/src/main.tsx only if no block can express the "
        "main interaction."
        if with_ui
        else "This App needs no screen of its own: leave screen and ui out of app.yaml. Alpha "
        "shows one form for primary_action, the action the person runs to get the result; set "
        "it, give it a clear title and description, mark pasted or long text inputs multiline: "
        "true, and return readable data (lists of entries become tables). Keep helper steps "
        "internal: do not list an action as manual if it needs another step's output.",
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
        registry: AppRegistry | None = None,
        inference: Any | None = None,
        contract_reference: Path | None = None,
        sdk_reference: Path | None = None,
    ) -> None:
        self._store = store
        self._assistant = assistant
        self._builds = builds
        self._planner = planner
        self._gateway = gateway
        self._routes = routes
        self._poll = poll_seconds
        self._registry = registry  # where a changed App's current version comes from
        # The quick path: one structured model call edits the module's files directly.
        self._inference = inference
        self._contract_reference = contract_reference
        self._sdk_reference = sdk_reference
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()
        store.execute_script(_SCHEMA)
        store.add_missing_columns("creations", {"change_of": "TEXT", "result_json": "TEXT"})

    # ----- public ------------------------------------------------------------------------

    def start(self, conversation_id: str, *, builder_hint: str | None = None) -> CreationRecord:
        conversation = self._assistant.get(conversation_id)
        if getattr(conversation, "quick_change", False) and conversation.state == "briefed":
            return self._start_quick(conversation)
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
        change_of: str | None = getattr(conversation, "change_of", None)
        if change_of is not None:
            if self._registry is None:
                raise CreationRefused("changing a module is not available on this host")
            try:
                self._registry.current(change_of)
            except OperationFailed as exc:
                raise CreationRefused(f"the module to change is not installed: {exc}") from exc
        creation_id = new_id("create")
        now = _now()
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO creations(creation_id, conversation_id, brief_id, brief_revision,
                   state, history_json, created_at, updated_at, change_of)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    creation_id,
                    conversation_id,
                    brief.id,
                    brief.revision,
                    "planning",
                    "[]",
                    now,
                    now,
                    change_of,
                ),
            )
        self._note(creation_id, "planning", "Writing the checks it must pass")
        threading.Thread(
            target=self._run,
            args=(creation_id, brief, builder_hint, change_of),
            name=f"creation-{creation_id}",
            daemon=True,
        ).start()
        return self.get(creation_id)

    def _look_rules(self) -> str:
        """The person's own rules for how modules should look, from Settings, as a trailing
        section for the builder."""
        prefs = getattr(self._gateway, "preferences", None)
        rules = str(prefs.get("look.rules") or "").strip() if prefs is not None else ""
        rules = rules or DEFAULT_CONVENTIONS.strip()
        return (
            "\n\nMODULE CONVENTIONS (Alpha's defaults as the person has set them in Settings; "
            "they decide layout, wording and behaviour, follow them in every module):\n" + rules
        )

    def _start_quick(self, conversation: Any) -> CreationRecord:
        app_id = conversation.change_of
        for existing in self.list_for_conversation(conversation.conversation_id):
            if existing.state not in TERMINAL:
                return existing
        if self._registry is None or self._inference is None:
            raise CreationRefused("quick changes are not available on this host")
        try:
            current = self._registry.current(app_id)
        except OperationFailed as exc:
            raise CreationRefused(f"the module to change is not installed: {exc}") from exc
        request = next((t.content.get("text") for t in conversation.turns if t.role == "user"), "")
        creation_id = new_id("create")
        now = _now()
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO creations(creation_id, conversation_id, brief_id, brief_revision,
                   app_id, app_name, state, plan_source, history_json, created_at, updated_at,
                   change_of) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    creation_id,
                    conversation.conversation_id,
                    "quick",
                    0,
                    app_id,
                    current.source.name,
                    "building",
                    "quick",
                    "[]",
                    now,
                    now,
                    app_id,
                ),
            )
        self._note(creation_id, "building", "Making the change")
        threading.Thread(
            target=self._run_quick,
            args=(creation_id, app_id, str(request or "")),
            name=f"creation-{creation_id}",
            daemon=True,
        ).start()
        return self.get(creation_id)

    def _run_quick(self, creation_id: str, app_id: str, request: str) -> None:
        try:
            self._quick_change(creation_id, app_id, request)
        except Exception as exc:
            log.exception("quick change %s failed inside Core", creation_id)
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

    def _quick_change(self, creation_id: str, app_id: str, request: str) -> None:
        """Edit the module's files directly from the person's words: one model call returns the
        changed files, the package must still validate and its handlers bind, then it becomes
        the current version. One repair round when the first edit is refused."""
        assert self._registry is not None and self._inference is not None
        current = self._registry.current(app_id)
        files = read_package_files(current.location)
        if sum(len(v) for v in files.values()) > QUICK_MAX_BYTES:
            self._finish(
                creation_id,
                "failed",
                None,
                {
                    "reason": "needs_full_build",
                    "message": "This module is too large to edit in one go; ask for the change "
                    "again and say 'full rebuild'.",
                    "next_step": "revise",
                },
            )
            return
        references = ""
        for label, path in (
            ("APP CONTRACT", self._contract_reference),
            ("SDK REFERENCE", self._sdk_reference),
        ):
            if path is not None and path.is_file():
                references += f"\n\n===== {label} =====\n{path.read_text(encoding='utf-8')}"
        route = self._gateway.route(self._routes.builder, stage="builder_change")
        feedback = ""
        for attempt in (1, 2):
            if self._stopped(creation_id):
                return
            prompt = quick_change_prompt(request + self._look_rules(), files, references, feedback)
            try:
                result = self._inference.call(
                    route,
                    system=QUICK_CHANGE_SYSTEM,
                    prompt=prompt,
                    schema=quick_change_schema(),
                    scope_kind="quick_change",
                    scope_ref=creation_id,
                    fake=lambda _p: fake_quick_change(request, files),
                )
            except Exception as exc:
                self._finish(
                    creation_id,
                    "failed",
                    None,
                    {
                        "reason": "model_unavailable",
                        "message": f"The model service could not make the edit: {exc}",
                        "next_step": "retry",
                    },
                )
                return
            output = result.output if isinstance(result.output, dict) else {}
            if output.get("needs_full_build"):
                self._finish(
                    creation_id,
                    "failed",
                    None,
                    {
                        "reason": "needs_full_build",
                        "message": "This change is bigger than a quick edit: "
                        f"{output.get('reason') or 'it adds new behaviour'}. Ask for it again "
                        "and say 'full rebuild' to do it the long way.",
                        "next_step": "revise",
                    },
                )
                return
            edits = {
                str(f.get("path")): str(f.get("content"))
                for f in output.get("files") or []
                if isinstance(f, dict) and f.get("path")
            }
            if not edits:
                feedback = "You returned no files. Return every file you change, in full."
                continue
            self._note(creation_id, "checking", "Checking it still holds together")
            staging = Path(tempfile.mkdtemp(prefix="alpha-quick-"))
            version = None
            try:
                package = staging / "package"
                shutil.copytree(current.location, package, ignore=SEALED_ARTEFACTS, symlinks=False)
                for path in [package, *package.rglob("*")]:
                    path.chmod(path.stat().st_mode | stat.S_IWUSR)
                problem = apply_edits(package, edits, current.source)
                if problem is None:
                    if not self._claim_activation(creation_id):
                        return
                    self._note(creation_id, "activating", "Switching it on")
                    version = self._registry.install(
                        package,
                        Activation(
                            kind="quick_change",
                            origin=current.origin,
                            expected_release_id=current.release_id,
                            creation_id=creation_id,
                        ),
                    )
            except OperationFailed as exc:
                problem = exc.message
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            if problem is None and version is not None:
                self._finish(
                    creation_id,
                    "active",
                    {
                        "release_id": version.release_id,
                        "version_id": version.version_id,
                        "app_id": version.app_id,
                    },
                    None,
                    result={
                        "app_id": version.app_id,
                        "name": version.source.name,
                        "actions": [a.id for a in version.source.actions],
                        "has_ui": version.source.has_screen() or version.source.ui is not None,
                        "checks_passed": 3,
                        "preview_images": [],
                        "attempts": attempt,
                        "summary": str(output.get("summary") or "")[:400],
                        "changed_files": sorted(edits),
                    },
                )
                return
            feedback = (
                f"Your previous edit was rejected: {problem}. Fix it and return the files again."
            )
        self._finish(
            creation_id,
            "failed",
            None,
            {
                "reason": "edit_rejected",
                "message": f"The edit did not hold together: {feedback[:300]}",
                "next_step": "retry",
            },
        )

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

    def conversations_for_app(self, app_id: str, limit: int = 50) -> list[Any]:
        """A module's own thread: the request that made it and every change asked since,
        newest first (the assistant panel shows this when opened from the module)."""
        rows = self._store.query(
            """SELECT conversation_id, MAX(created_at) AS at FROM (
                   SELECT conversation_id, created_at FROM creations WHERE app_id = ?
                   UNION ALL
                   SELECT conversation_id, created_at FROM conversations WHERE change_of = ?
               ) GROUP BY conversation_id ORDER BY at DESC LIMIT ?""",
            (app_id, app_id, limit),
        )
        found = []
        for row in rows:
            try:
                found.append(self._assistant.get(row["conversation_id"]))
            except Exception:  # a conversation missing from the store is not the module's fault
                continue
        return found

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

    def _run(
        self,
        creation_id: str,
        brief: SolutionBrief,
        builder_hint: str | None,
        change_of: str | None = None,
    ) -> None:
        try:
            self._create(creation_id, brief, builder_hint, change_of)
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

    def _create(
        self,
        creation_id: str,
        brief: SolutionBrief,
        builder_hint: str | None,
        change_of: str | None = None,
    ) -> None:
        # A change keeps the App's identity and name, starts the build from its current
        # version and only switches on if that version is still current when it finishes.
        current = None
        if change_of is not None:
            assert self._registry is not None
            current = self._registry.current(change_of)
        try:
            planned = self._planner.plan(
                brief, self._gateway.route(self._routes.planner, stage="planner"), creation_id
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
        if current is not None:
            app_id, app_name = current.app_id, current.source.name
        else:
            app_id = app_slug(planned.app_name, creation_id.removeprefix("create_")[:6])
            app_name = planned.app_name
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE creations SET app_id = ?, app_name = ?, plan_json = ?, plan_source = ?,
                   updated_at = ? WHERE creation_id = ?""",
                (
                    app_id,
                    app_name,
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
                brief, with_ui=wants_ui(brief), app_name=app_name, change=current is not None
            )
            + self._look_rules(),
            route_id=self._routes.builder,
            app_id=app_id,
            base_package=current.location if current is not None else None,
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
                final.build_id,
                expected_release_id=current.release_id if current is not None else None,
                creation_id=creation_id,
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
        elif reason == "plan_defect":
            message = (
                "Alpha's own checks for this request were faulty, so what was built could not "
                "be judged fairly. Nothing was changed; try again."
            )
            next_step = "retry"
        elif reason in ("repair_limit_reached", "total_deadline_exceeded", "cost_limit_reached"):
            tries = "once" if len(build.attempts) == 1 else f"{len(build.attempts)} times"
            message = (
                f"It was built {tries} but didn't pass its checks, so nothing was switched on."
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
        result: dict[str, Any] | None = None,
    ) -> None:
        with self._store.transaction() as conn:
            self._finish_locked(conn, creation_id, state, activated, failure)
            if result is not None:
                conn.execute(
                    "UPDATE creations SET result_json = ? WHERE creation_id = ?",
                    (json.dumps(result), creation_id),
                )

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
        if result is None and row["result_json"]:
            result = json.loads(row["result_json"])
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
            change_of=row["change_of"],
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
