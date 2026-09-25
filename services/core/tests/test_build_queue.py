"""The one-builder queue survives a fault inside Core: the failing build is marked failed with
the platform as the cause, and the next queued build still starts."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any, cast

import pytest
from alpha.builds.service import BuildPipeline, BuildService
from alpha.builds.store import AcceptanceExample, plan_from_examples
from alpha.execution.supervisor import WorkerSupervisor
from alpha.models.gateway import ModelGateway
from alpha.storage.control_store import ControlStore
from alpha_contracts.builds import BuildState

PLAN = plan_from_examples([AcceptanceExample(action_id="a", input={}, expected={})])


def test_a_platform_fault_fails_one_build_and_the_queue_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = ControlStore(tmp_path / "control.sqlite")
    service = BuildService(
        control,
        WorkerSupervisor(Path(sys.executable), tmp_path / "scratch", 1.0),
        ModelGateway(control, frozenset({"fake"})),
        cast(BuildPipeline, None),  # never reached: the attempt itself is replaced below
        builds_root=tmp_path / "builds",
        builder_path="/usr/bin:/bin",
        builder_home=None,
        instance_id="core_test",
    )
    started: list[str] = []
    second_started = threading.Event()

    def run_build(item: Any) -> None:
        started.append(item.build_id)
        if len(started) == 1:
            raise RuntimeError("store unavailable")
        second_started.set()

    monkeypatch.setattr(service, "_run_build", run_build)
    first = service.submit(goal="one", plan=PLAN)
    second = service.submit(goal="two", plan=PLAN)
    assert second_started.wait(5.0), "the queue stalled after a fault"
    assert started == [first.build_id, second.build_id]

    failed = service.get(first.build_id)
    assert failed.state is BuildState.FAILED
    assert failed.terminal_reason == "platform_error"
    assert failed.failure_category == "platform_error"
    event = service.events(first.build_id)[-1]
    assert event.kind == "build.failed" and "store unavailable" in event.payload["error"]
    service.shutdown()
