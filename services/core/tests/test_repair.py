"""Self-healing: a failed run is diagnosed (whose fault it is, in plain words), a fault in the
module's own code is fixed through the quick path and the action runs again, faults elsewhere
are named not "fixed", one attempt per cause per version, and the loop's fix step reports what
happened."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from alpha.assistant.acting import ActService
from alpha.assistant.sessions import SessionService
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.solutions.creation import CreationRoutes, CreationService
from alpha.solutions.repair import MODULE_CODE, OUTSIDE, PLATFORM, REFUSAL, RepairService, evidence
from alpha.storage.control_store import ControlStore
from alpha_contracts.runs import AppOwner, ExecutionSnapshot, RunLimits, RunOrigin, RunState
from test_acting import Records, Runs  # noqa: I001
from test_acting import Registry as ActRegistry
from test_quick_change import Inference, version_dir  # noqa: I001
from test_quick_change import Registry as QuickRegistry

VERSION_DIR = "/Users/x/Library/Application Support/com.alpha.desktop/versions/ver_1/src/app_code"
TRACEBACK = (
    "Traceback (most recent call last):\n"
    '  File "/runtime/site-packages/alpha_app_worker/runner.py", line 168, in run_invoke\n'
    "    result = function(context, **payload)\n"
    f'  File "{VERSION_DIR}/handlers.py", line 551, in search_new_listings\n'
    "    record = ctx.records.create(\n"
    '  File "/runtime/site-packages/alpha_sdk/records.py", line 104, in _estimated\n'
    '    raise TypeError("estimated values must map a field to the ModelResult it came from")\n'
    "TypeError: estimated values must map a field to the ModelResult it came from\n"
)


def failed_run(
    store: ControlStore,
    *,
    app_id: str = "jobs",
    action_id: str = "search_new_listings",
    code: str = "handler_exception",
    exception: str | None = "TypeError",
    technical: str = "TypeError: estimated values must map a field to the ModelResult it came from",
    traceback: str = TRACEBACK,
    payload: dict[str, Any] | None = None,
) -> str:
    run = store.create_run(
        workspace_id="ws",
        owner=AppOwner(app_id=app_id, release_id="rel_1", action_id=action_id),
        origin=RunOrigin.TRIGGER,
        snapshot=ExecutionSnapshot(
            worker_profile="app",
            input_digest="sha256:" + "0" * 64,
            limits=RunLimits(timeout_seconds=60),
            version_id="ver_1",
        ),
        input_payload=payload or {"target_role": "backend"},
    )
    store.transition(
        run.run_id,
        expected_states={RunState.QUEUED},
        new_state=RunState.RUNNING,
        event_kind="run.started",
        payload={},
    )
    error = {"code": code, "message": "plain", "technical": technical, "traceback": traceback}
    if exception:
        error["exception"] = exception
    store.transition(
        run.run_id,
        expected_states={RunState.RUNNING},
        new_state=RunState.FAILED,
        event_kind="run.failed",
        payload={"error": error, "reason": code},
        terminal_reason=code,
    )
    return run.run_id


class Source:
    name = "Job tracker"

    def action(self, action_id: str) -> Any:
        if action_id != "search_new_listings":
            return None
        return SimpleNamespace(
            id=action_id, title="Search new listings", invocable_from=["trigger", "manual"]
        )


class Registry:
    def current(self, app_id: str) -> Any:
        return SimpleNamespace(source=Source(), location=Path("/nowhere"))


class Creations:
    """A creation service that finishes as told, so the repair logic is tested on its own."""

    def __init__(self, outcome: str = "active") -> None:
        self.outcome = outcome
        self.started: list[tuple[str, str, str]] = []
        self.records: dict[str, Any] = {}

    def start_repair(self, app_id: str, evidence: str, *, run_id: str) -> Any:
        creation_id = f"create_{len(self.started) + 1}"
        self.started.append((app_id, evidence, run_id))
        self.records[creation_id] = SimpleNamespace(
            creation_id=creation_id,
            state=self.outcome,
            result={"summary": "passed the model result as the estimate source"},
            failure=(
                {"message": "the edit did not hold together"} if self.outcome == "failed" else None
            ),
        )
        return self.records[creation_id]

    def get(self, creation_id: str) -> Any:
        return self.records[creation_id]


class RerunRuns:
    """Invoking the action again produces a run that ends as told."""

    def __init__(self, store: ControlStore, state: RunState = RunState.SUCCEEDED) -> None:
        self.store = store
        self.state = state
        self.invoked: list[tuple[str, str, dict[str, Any], RunOrigin]] = []

    def invoke(
        self, app_id: str, action_id: str, payload: dict[str, Any], *, origin: RunOrigin
    ) -> Any:
        self.invoked.append((app_id, action_id, payload, origin))
        run = self.store.create_run(
            workspace_id="ws",
            owner=AppOwner(app_id=app_id, release_id="rel_2", action_id=action_id),
            origin=origin,
            snapshot=ExecutionSnapshot(
                worker_profile="app",
                input_digest="sha256:" + "1" * 64,
                limits=RunLimits(timeout_seconds=60),
                version_id="ver_2",
            ),
            input_payload=payload,
        )
        self.store.transition(
            run.run_id,
            expected_states={RunState.QUEUED},
            new_state=RunState.RUNNING,
            event_kind="run.started",
            payload={},
        )
        if self.state is RunState.SUCCEEDED:
            self.store.transition(
                run.run_id,
                expected_states={RunState.RUNNING},
                new_state=RunState.SUCCEEDED,
                event_kind="run.succeeded",
                payload={},
                output={"added": 12, "message": "Added 12 new listing(s) from LinkedIn as New."},
            )
        else:
            self.store.transition(
                run.run_id,
                expected_states={RunState.RUNNING},
                new_state=RunState.FAILED,
                event_kind="run.failed",
                payload={
                    "error": {  # the same cause again: the fix did not hold
                        "code": "handler_exception",
                        "exception": "TypeError",
                        "technical": "TypeError: estimated values must map a field",
                        "traceback": TRACEBACK,
                    }
                },
                terminal_reason="handler_exception",
            )
        return run


Built = tuple[RepairService, ControlStore, Any, RerunRuns]


def service(
    tmp_path: Path, creations: Any | None = None, rerun_state: RunState = RunState.SUCCEEDED
) -> Built:
    store = ControlStore(tmp_path / "control.sqlite")
    creations = creations or Creations()
    runs = RerunRuns(store, rerun_state)
    svc = RepairService(
        store, registry=Registry(), creations=creations, runs=runs, names=lambda _a: "Job tracker"
    )
    return svc, store, creations, runs


def test_a_crash_in_the_modules_code_is_diagnosed_in_plain_words(tmp_path: Path) -> None:
    svc, store, _, _ = service(tmp_path)
    run_id = failed_run(store)
    diagnosis = svc.diagnose(run_id)
    assert diagnosis is not None and diagnosis.kind == MODULE_CODE
    assert diagnosis.where == "handlers.py line 551"
    assert diagnosis.cause == "search_new_listings:TypeError:handlers.py line 551"
    assert diagnosis.said == (
        "Search new listings stopped in the module's own code (handlers.py line 551): "
        "TypeError: estimated values must map a field to the ModelResult it came from."
    )
    text = evidence(diagnosis, "Search new listings")
    assert 'INPUT: {"target_role": "backend"}' in text and "line 551" in text
    assert "run again with the same input" in text


def test_faults_outside_the_module_are_named_never_fixed(tmp_path: Path) -> None:
    svc, store, creations, _ = service(tmp_path)
    platform = failed_run(
        store,
        technical="TypeError: Web.get() got an unexpected keyword argument 'rendered'",
        traceback=TRACEBACK.replace(
            f"{VERSION_DIR}/handlers.py", "/runtime/site-packages/alpha_sdk/web.py"
        ),
    )
    assert svc.diagnose(platform).kind == PLATFORM
    refused = failed_run(store, exception="ValueError", technical="ValueError: a title is needed")
    assert svc.diagnose(refused).kind == REFUSAL
    outside = failed_run(store, code="timed_out", exception=None, technical="", traceback="")
    assert svc.diagnose(outside).kind == OUTSIDE
    for run_id in (platform, refused, outside):
        result = svc.repair(run_id)
        assert result["state"] == "skipped" and result["message"]
    assert creations.started == []
    assert "not the module's fault" in svc.diagnose(platform).said


def test_a_fix_goes_live_and_the_action_runs_again(tmp_path: Path) -> None:
    svc, store, creations, runs = service(tmp_path)
    run_id = failed_run(store)
    result = svc.repair(run_id)
    assert result["state"] == "fixed", result
    assert creations.started[0][0] == "jobs" and creations.started[0][2] == run_id
    assert runs.invoked == [
        ("jobs", "search_new_listings", {"target_role": "backend"}, RunOrigin.TRIGGER)
    ]
    assert result["message"] == (
        "Alpha fixed it (passed the model result as the estimate source) and ran Search new "
        "listings again: Added 12 new listing(s) from LinkedIn as New."
    )
    repairs = svc.list_repairs("jobs")
    assert len(repairs) == 1 and repairs[0]["state"] == "fixed" and repairs[0]["rerun_run_id"]
    # The failure now carries what Alpha did, for the module's Activity and the loop's facts.
    entry = svc.recent("jobs")[0]
    assert entry["run_id"] == run_id and entry["repair"]["state"] == "fixed"
    facts = svc.facts(["jobs"])
    assert facts[0].startswith("FAILED ") and "Alpha fixed it" in facts[0]


def test_one_attempt_per_cause_then_it_says_so(tmp_path: Path) -> None:
    svc, store, creations, _ = service(tmp_path, rerun_state=RunState.FAILED)
    run_id = failed_run(store)
    first = svc.repair(run_id)
    assert first["state"] == "not_fixed" and "still did not go through" in first["message"]
    second = svc.repair(run_id)
    assert second["state"] == "already_tried" and len(creations.started) == 1
    assert "Ask for a change" in second["message"]
    # The same cause on the rerun (a later run) counts as tried too: no loop.
    later = svc.recent("jobs")[0]
    assert later["repair"] is not None and later["repair"]["state"] == "not_fixed"


def test_an_edit_that_does_not_hold_is_reported(tmp_path: Path) -> None:
    svc, store, _, runs = service(tmp_path, creations=Creations(outcome="failed"))
    run_id = failed_run(store)
    result = svc.repair(run_id)
    assert result["state"] == "not_fixed"
    assert result["message"] == "Alpha could not fix this: the edit did not hold together"
    assert runs.invoked == []


def test_a_failure_is_looked_at_on_its_own(tmp_path: Path) -> None:
    svc, store, creations, runs = service(tmp_path)
    run_id = failed_run(store)
    svc.consider(run_id)
    for thread in threading.enumerate():
        if thread.name.startswith("repair-"):
            thread.join(timeout=10)
    assert len(creations.started) == 1 and len(runs.invoked) == 1
    svc.consider(run_id)  # already tried: nothing starts again
    assert len(creations.started) == 1
    ok = failed_run(store, exception="ValueError", technical="ValueError: no")
    svc.consider(ok)
    assert len(creations.started) == 1


def test_the_real_quick_path_repairs_from_evidence(tmp_path: Path) -> None:
    """Through CreationService.start_repair on the fake route: the evidence reaches the edit
    call, the package is edited, validated and switched on with the release guarded."""
    registry = QuickRegistry(version_dir(tmp_path))
    creations = CreationService(
        ControlStore(tmp_path / "control.sqlite"),
        SimpleNamespace(get=lambda _cid: None),  # type: ignore[arg-type]
        SimpleNamespace(get=lambda _b: None, events=lambda _b: []),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(route=lambda route_id, **_: SimpleNamespace(route_id=route_id)),  # type: ignore[arg-type]
        CreationRoutes(planner="fake", builder="fake"),
        poll_seconds=0.01,
        registry=registry,  # type: ignore[arg-type]
        inference=Inference(),
    )
    creation = creations.start_repair(
        "notes-list-1a2b3c", "ERROR: TypeError at line 5", run_id="run_9"
    )
    for thread in threading.enumerate():
        if thread.name == f"creation-{creation.creation_id}":
            thread.join(timeout=10)
    final = creations.get(creation.creation_id)
    assert final.state == "active", final.failure
    assert final.plan_source == "repair" and final.conversation_id == "repair:run_9"
    written, activation = registry.installed[0]
    assert "Changed: ERROR: TypeError at line 5" in written
    assert activation.kind == "repair" and activation.expected_release_id == "rel_1"
    assert [h["label"] for h in final.history][0] == "Fixing it"


def test_the_loop_takes_a_fix_step_from_the_facts(tmp_path: Path) -> None:
    svc, store, creations, rerun = service(tmp_path)
    run_id = failed_run(store, app_id="notes")
    gateway = ModelGateway(store, frozenset({"fake"}))
    runs = Runs()
    acting = ActService(
        store,
        gateway,
        StructuredInference(gateway),
        registry=ActRegistry(),
        runs=runs,
        records=Records(),
        assistant=None,
        sessions=SessionService(store),
        default_route="fake",
        run_lookup=runs.lookup,
        repair=svc,
        today=lambda: "2026-09-29",
    )
    facts = acting._facts({"notes": "Notes (fixture)"})
    assert any(f.startswith("FAILED ") and "Alpha can fix this" in f for f in facts)
    turn = acting.act(f"fake:fix notes {run_id}")
    assert turn.kind == "fix"
    assert turn.reply.startswith("Alpha fixed it (")
    assert "ran Search new listings again" in turn.reply
    assert turn.outcome == "fixed the module's code in Notes (fixture) and ran the action again"
    assert len(creations.started) == 1 and len(rerun.invoked) == 1
