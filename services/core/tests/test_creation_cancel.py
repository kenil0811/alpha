"""M1 review finding F13: Stop and switching on are decided atomically.

The real CreationService on a real SQLite control store; the builds, planner and assistant are
controlled collaborators so each race window can be entered on purpose. The end-to-end version
with real builds is tests/integration/test_creations.py.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.capabilities.errors import OperationFailed
from alpha.solutions.creation import CreationRoutes, CreationService
from alpha.solutions.planner import AcceptancePlan, PlanningFailed
from alpha.storage.control_store import ControlStore
from alpha_contracts.briefs import SolutionBrief
from alpha_contracts.builds import BuildState
from alpha_contracts.verification import ValidationPlan

BRIEF = SolutionBrief.model_validate(
    {
        "id": "brief_1",
        "revision": 1,
        "conversation_id": "conv_1",
        "created_at": datetime.now(UTC).isoformat(),
        "goal": "Keep a notes list",
        "success_summary": "Notes are saved",
        "delivery": "app",
        "surfaces": ["conversation"],
        "inputs": [],
        "primary_journey": [],
        "data_needs": [],
        "actions": [],
        "recurrence": None,
        "constraints": [],
        "acceptance_examples": [],
        "assumptions": [],
        "open_questions": [],
        "unavailable_capabilities": [],
        "selected_context_snapshot_id": "conv_1.context.r1",
    }
)
PLAN = ValidationPlan.model_validate(
    {
        "scenarios": [
            {"id": "s", "description": "d", "steps": [{"kind": "invoke", "id": "a", "action": "x"}]}
        ]
    }
)


class Builds:
    """Controlled builds: `on_submit`, `on_ready` and `on_activate` run inside the creation."""

    def __init__(self) -> None:
        self.cancelled: list[str] = []
        self.activated: list[str] = []
        self.on_submit: Any = None
        self.on_ready: Any = None
        self.on_activate: Any = None
        self.reads = 0

    def submit(self, **_: Any) -> Any:
        if self.on_submit:
            self.on_submit()
        return SimpleNamespace(build_id="build_1")

    def get(self, build_id: str) -> Any:
        self.reads += 1
        if self.on_ready and self.reads == 1:
            self.on_ready()
        return SimpleNamespace(
            build_id=build_id,
            state=BuildState.READY,
            attempts=[],
            candidate=None,
            validation=None,
            terminal_reason=None,
            failure_category=None,
            budget=SimpleNamespace(max_repair_attempts=2),
        )

    def events(self, build_id: str) -> list[Any]:
        return []

    def cancel(self, build_id: str) -> None:
        self.cancelled.append(build_id)

    def activate(self, build_id: str, **_: Any) -> dict[str, Any]:
        if self.on_activate:
            self.on_activate()
        self.activated.append(build_id)
        return {"release_id": "rel_1", "version_id": "ver_1", "app_id": "notes-list-x"}


def service(tmp_path: Path, builds: Builds) -> CreationService:
    assistant = SimpleNamespace(
        get=lambda _cid: SimpleNamespace(state="briefed", current_brief=BRIEF)
    )
    planner = SimpleNamespace(
        plan=lambda *_a, **_k: AcceptancePlan("Notes list", PLAN, "model", [])
    )
    gateway = SimpleNamespace(route=lambda route_id, **_: SimpleNamespace(route_id=route_id))
    return CreationService(
        ControlStore(tmp_path / "control.sqlite"),
        assistant,  # type: ignore[arg-type]
        builds,  # type: ignore[arg-type]
        planner,  # type: ignore[arg-type]
        gateway,  # type: ignore[arg-type]
        CreationRoutes(planner="fake", builder="fake"),
        poll_seconds=0.01,
    )


def run_to_end(svc: CreationService) -> str:
    creation = svc.start("conv_1")
    for thread in threading.enumerate():
        if thread.name == f"creation-{creation.creation_id}":
            thread.join(timeout=10)
    return creation.creation_id


def test_stop_during_build_submission_cancels_the_new_build_and_switches_nothing_on(
    tmp_path: Path,
) -> None:
    builds = Builds()
    svc = service(tmp_path, builds)
    holder: dict[str, str] = {}
    builds.on_submit = lambda: svc.cancel(holder["id"])
    original_start = svc.start

    def start(cid: str) -> Any:
        record = original_start(cid)
        holder["id"] = record.creation_id
        return record

    # The creation thread may reach submit before start() returns; hold the planner until then.
    gate = threading.Event()
    svc._planner = SimpleNamespace(  # type: ignore[assignment]
        plan=lambda *_a, **_k: (gate.wait(5), AcceptancePlan("Notes list", PLAN, "model", []))[1]
    )
    svc.start = start  # type: ignore[method-assign]
    record = svc.start("conv_1")
    gate.set()
    for thread in threading.enumerate():
        if thread.name == f"creation-{record.creation_id}":
            thread.join(timeout=10)
    final = svc.get(record.creation_id)
    assert final.state == "cancelled"
    assert builds.cancelled == ["build_1"], "the build submitted during Stop is cancelled"
    assert builds.activated == []


def test_stop_at_the_ready_boundary_prevents_switching_on(tmp_path: Path) -> None:
    builds = Builds()
    svc = service(tmp_path, builds)
    holder: dict[str, str] = {}
    builds.on_ready = lambda: svc.cancel(holder["id"])
    gate = threading.Event()
    svc._planner = SimpleNamespace(  # type: ignore[assignment]
        plan=lambda *_a, **_k: (gate.wait(5), AcceptancePlan("Notes list", PLAN, "model", []))[1]
    )
    record = svc.start("conv_1")
    holder["id"] = record.creation_id
    gate.set()
    for thread in threading.enumerate():
        if thread.name == f"creation-{record.creation_id}":
            thread.join(timeout=10)
    final = svc.get(record.creation_id)
    assert final.state == "cancelled"
    assert builds.activated == [], "an accepted Stop leaves no new release"
    assert [h["stage"] for h in final.history][-1] == "cancelled"


def test_stop_after_switching_on_began_is_refused_and_the_outcome_is_completion(
    tmp_path: Path,
) -> None:
    builds = Builds()
    svc = service(tmp_path, builds)
    refused: list[str] = []
    holder: dict[str, str] = {}

    def stop_now() -> None:
        with pytest.raises(OperationFailed) as caught:
            svc.cancel(holder["id"])
        refused.append(caught.value.message)

    builds.on_activate = stop_now
    gate = threading.Event()
    svc._planner = SimpleNamespace(  # type: ignore[assignment]
        plan=lambda *_a, **_k: (gate.wait(5), AcceptancePlan("Notes list", PLAN, "model", []))[1]
    )
    record = svc.start("conv_1")
    holder["id"] = record.creation_id
    gate.set()
    for thread in threading.enumerate():
        if thread.name == f"creation-{record.creation_id}":
            thread.join(timeout=10)
    final = svc.get(record.creation_id)
    assert refused == ["it is already being switched on and can no longer be stopped"]
    assert final.state == "active"
    assert builds.activated == ["build_1"]


def test_stop_after_completion_is_refused_plainly(tmp_path: Path) -> None:
    builds = Builds()
    svc = service(tmp_path, builds)
    creation_id = run_to_end(svc)
    assert svc.get(creation_id).state == "active"
    with pytest.raises(OperationFailed, match="already active"):
        svc.cancel(creation_id)


def test_a_planning_failure_is_told_plainly_with_the_gaps_kept(tmp_path: Path) -> None:
    """Found in M1-R07: the person was shown "the checks are incomplete: the plan never reads
    what is stored in …". They get a plain sentence; the gaps stay under the checks' details."""
    svc = service(tmp_path, Builds())
    gap = "the plan never runs trends successfully"

    def refuse(*_a: object, **_k: object) -> AcceptancePlan:
        raise PlanningFailed("the checks are incomplete", [gap])

    svc._planner = SimpleNamespace(plan=refuse)  # type: ignore[assignment]
    failed = svc.get(run_to_end(svc))
    assert failed.state == "failed"
    assert failed.failure == {
        "reason": "plan_unavailable",
        "message": "Alpha couldn't work out how to check this request, so nothing was made.",
        "failed_checks": [gap],
        "next_step": "retry",
    }
