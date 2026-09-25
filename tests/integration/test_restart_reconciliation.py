"""F01.C04 (control portion): Core/worker interruption is visible after restart; explicit quit
terminates descendants and records interrupted runs; durable results survive restart."""

from __future__ import annotations

import os
import signal
from pathlib import Path

import pytest

from tests.integration.conftest import start_core, wait_until_dead

pytestmark = pytest.mark.integration


def test_results_survive_restart(data_dir: Path) -> None:
    first = start_core(data_dir)
    try:
        created = first.submit(text="durable", steps=1)
        first.wait_for_state(created["run_id"], {"succeeded"})
    finally:
        first.stop()
    second = start_core(data_dir, token=first.token)
    try:
        reopened = second.run(created["run_id"])
        assert reopened["state"] == "succeeded"
        assert reopened["output"]["upper"] == "DURABLE"
        assert [e["kind"] for e in second.events(created["run_id"])][-1] == "run.succeeded"
        assert second.ready["core_instance_id"] != first.ready["core_instance_id"]
    finally:
        second.stop()


def test_hard_kill_of_core_is_reconciled_as_interrupted_on_restart(data_dir: Path) -> None:
    first = start_core(data_dir)
    created = first.submit(text="x", mode="hang", spawn_child=True)
    run_id = created["run_id"]
    started = first.wait_for_event(run_id, "run.started")
    worker_pid = int(started["payload"]["worker_pid"])
    child_pid = first.child_pid(run_id)
    first.wait_for_event(run_id, "worker.progress", stage="hanging")
    # Simulate a crash: no graceful shutdown, worker tree is orphaned and idle.
    first.stop(sig=signal.SIGKILL)
    assert not wait_until_dead(worker_pid, timeout=0.5), "orphaned worker should still be alive"

    second = start_core(data_dir, token=first.token)
    try:
        run = second.run(run_id)
        assert run["state"] == "interrupted"
        assert run["terminal_reason"] == "core_restarted_worker_orphaned"
        interrupted = second.wait_for_event(run_id, "run.interrupted")
        assert interrupted["payload"]["lease"]["alive"] is True
        assert wait_until_dead(worker_pid), "orphaned worker not terminated on reconciliation"
        assert wait_until_dead(child_pid), "orphaned descendant not terminated"
        assert second.ready["core_instance_id"] != first.ready["core_instance_id"]
        with second.client() as client:
            assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409
    finally:
        second.stop()


def test_explicit_quit_terminates_workers_and_marks_runs_interrupted(data_dir: Path) -> None:
    first = start_core(data_dir)
    created = first.submit(text="x", mode="hang", spawn_child=True)
    run_id = created["run_id"]
    started = first.wait_for_event(run_id, "run.started")
    worker_pid = int(started["payload"]["worker_pid"])
    child_pid = first.child_pid(run_id)
    first.stop(sig=signal.SIGTERM)
    assert wait_until_dead(worker_pid), "worker survived explicit quit"
    assert wait_until_dead(child_pid), "descendant survived explicit quit"

    second = start_core(data_dir, token=first.token)
    try:
        run = second.run(run_id)
        assert run["state"] == "interrupted"
        assert run["terminal_reason"] == "runtime_quit"
        assert [e["kind"] for e in second.events(run_id)][-1] == "run.interrupted"
        # No lease remained for reconciliation to act on.
        assert "reconciled" not in second.stderr()
    finally:
        second.stop()


def test_hard_kill_with_dead_worker_is_reconciled_as_lost(data_dir: Path) -> None:
    first = start_core(data_dir)
    created = first.submit(text="x", mode="hang")
    run_id = created["run_id"]
    started = first.wait_for_event(run_id, "run.started")
    worker_pid = int(started["payload"]["worker_pid"])
    first.stop(sig=signal.SIGKILL)
    os.kill(worker_pid, signal.SIGKILL)
    assert wait_until_dead(worker_pid)

    second = start_core(data_dir, token=first.token)
    try:
        run = second.run(run_id)
        assert run["state"] == "interrupted"
        assert run["terminal_reason"] == "core_restarted_worker_lost"
        interrupted = second.wait_for_event(run_id, "run.interrupted")
        assert interrupted["payload"]["lease"]["alive"] is False
        assert "termination" not in interrupted["payload"]
    finally:
        second.stop()
