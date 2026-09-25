"""F02 control checks with the deterministic fake harness: lifecycle, validation, failure
classification, cancellation with descendants, restart behaviour, usage retention.
The fake harness proves controls only; generation quality is proven by the live route."""

from __future__ import annotations

import json
import signal
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from tests.integration.conftest import CoreProcess, pid_alive, start_core, wait_until_dead

pytestmark = pytest.mark.integration

SUMMARIZE_EXAMPLES = [
    {
        "action_id": "summarize",
        "input": {"text": "one two three"},
        "expected": {"words": 3, "characters": 13},
    },
    {"action_id": "summarize", "input": {"text": ""}, "expected": {"words": 0, "characters": 0}},
]


def submit(
    core: CoreProcess, goal: str, examples: list[dict[str, Any]] | None = None, **extra: Any
) -> dict[str, Any]:
    body = {
        "goal": goal,
        "acceptance_examples": examples or SUMMARIZE_EXAMPLES,
        "route_id": "fake",
        **extra,
    }
    with core.client() as client:
        response = client.post("/api/builds", json=body)
        assert response.status_code == 201, response.text
        data: dict[str, Any] = response.json()
        return data


def get_build(core: CoreProcess, build_id: str) -> dict[str, Any]:
    with core.client() as client:
        response = client.get(f"/api/builds/{build_id}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data


def build_events(core: CoreProcess, build_id: str) -> list[dict[str, Any]]:
    with core.client() as client:
        response = client.get(f"/api/builds/{build_id}/events")
        response.raise_for_status()
        events: list[dict[str, Any]] = response.json()["events"]
        return events


def wait_for_build(
    core: CoreProcess, build_id: str, states: set[str], timeout: float = 30.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = get_build(core, build_id)
        if last["state"] in states:
            return last
        time.sleep(0.1)
    raise AssertionError(f"build {build_id} stayed {last.get('state')}; expected {states}")


def wait_for_build_event(
    core: CoreProcess, build_id: str, kind: str, timeout: float = 15.0
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for event in build_events(core, build_id):
            if event["kind"] == kind:
                return event
        time.sleep(0.1)
    raise AssertionError(f"no {kind} event for build {build_id}")


def builder_pids() -> list[int]:
    out = subprocess.run(["pgrep", "-f", "alpha.workers.builder"], capture_output=True, text=True)
    return [int(p) for p in out.stdout.split()]


def test_fake_build_is_validated_sealed_and_invocable(core: CoreProcess, data_dir: Path) -> None:
    created = submit(core, "fake:succeed count words")
    assert created["state"] in ("queued", "building")
    assert created["harness"] == "fake" and created["route_id"] == "fake"
    final = wait_for_build(core, created["build_id"], {"ready", "failed", "cancelled"})
    assert final["state"] == "ready", final
    candidate = final["candidate"]
    assert candidate["actions"] == ["summarize"]
    assert candidate["source_digest"].startswith("sha256:")
    assert final["validation"]["passed"] is True
    assert final["attempts"][0]["status"] == "candidate"
    assert final["attempts"][0]["usage"]["cost_basis"] == "unavailable"

    workspace = data_dir / "builds" / final["attempts"][0]["workspace_ref"]
    assert (workspace / "package.index.json").is_file()
    index = json.loads((workspace / "package.index.json").read_text())
    assert [f["path"] for f in index["files"]] == ["app.yaml", "src/word_stats.py"]
    assert not (workspace / "package" / "src" / "__pycache__").exists()
    normalized = [
        e for e in build_events(core, created["build_id"]) if e["kind"] == "validation.normalized"
    ]
    assert (
        normalized
        and "src/__pycache__/word_stats.cpython-313.pyc" in normalized[0]["payload"]["removed"]
    )
    assert (workspace / "validation.report.json").is_file()
    assert (data_dir / "builds" / created["build_id"] / "brief.r1.json").is_file()

    kinds = [e["kind"] for e in build_events(core, created["build_id"])]
    assert kinds[:2] == ["build.queued", "build.attempt_started"]
    assert "harness.harness.file_written" in kinds
    assert "build.validating" in kinds and kinds[-1] == "build.ready"
    checks = [
        e["payload"]
        for e in build_events(core, created["build_id"])
        if e["kind"] == "validation.check"
    ]
    assert all(c["passed"] for c in checks) and len(checks) >= 5

    with core.client() as client:
        response = client.post(
            f"/api/builds/{created['build_id']}/invoke",
            json={"action_id": "summarize", "input": {"text": "alpha beta"}},
        )
    assert response.status_code == 200, response.text
    assert response.json()["output"]["calls"][0]["output"] == {"words": 2, "characters": 10}

    # usage row retained in the control store
    conn = sqlite3.connect(data_dir / "control.sqlite")
    rows = conn.execute("SELECT route_id, cost_basis FROM model_usage").fetchall()
    conn.close()
    assert rows == [("fake", "unavailable")]


def test_builder_stderr_is_drained_while_it_runs(core: CoreProcess) -> None:
    created = submit(core, "fake:noisy count words")
    final = wait_for_build(core, created["build_id"], {"ready", "failed", "cancelled"})
    assert final["state"] == "ready", final
    exited = wait_for_build_event(core, created["build_id"], "builder.exited")
    tail = exited["payload"]["stderr_tail"]
    assert len(tail) == 2000 and tail.endswith("noisy-end\n")


def test_harness_failure_never_becomes_a_candidate(core: CoreProcess) -> None:
    created = submit(core, "fake:fail")
    final = wait_for_build(core, created["build_id"], {"ready", "failed", "cancelled"})
    assert final["state"] == "failed"
    assert final["failure_category"] == "harness_error"
    assert final["terminal_reason"] == "harness_failed"
    assert final["candidate"] is None
    assert final["attempts"][0]["status"] == "failed"


def test_claimed_success_without_package_is_rejected(core: CoreProcess) -> None:
    created = submit(core, "fake:claims_success")
    final = wait_for_build(core, created["build_id"], {"ready", "failed", "cancelled"})
    assert final["state"] == "failed"
    assert final["failure_category"] == "no_package"
    assert final["validation"]["checks"][0] == {
        "check": "package_present",
        "passed": False,
        "detail": None,
    }


def test_missing_handler_is_caught_by_real_binding(core: CoreProcess) -> None:
    created = submit(core, "fake:broken_package")
    final = wait_for_build(core, created["build_id"], {"ready", "failed", "cancelled"})
    assert final["state"] == "failed"
    assert final["failure_category"] == "validation_failed"
    binding = next(
        c for c in final["validation"]["checks"] if c["check"] == "acceptance:summarize:binding"
    )
    assert binding["passed"] is False
    assert "has no attribute 'summarize'" in binding["detail"]["message"]


def test_independent_expected_outputs_govern_validation(core: CoreProcess) -> None:
    wrong = [
        {
            "action_id": "summarize",
            "input": {"text": "one two"},
            "expected": {"words": 99, "characters": 7},
        }
    ]
    created = submit(core, "fake:succeed", wrong)
    final = wait_for_build(core, created["build_id"], {"ready", "failed", "cancelled"})
    assert final["state"] == "failed"
    assert final["failure_category"] == "validation_failed"
    check = next(c for c in final["validation"]["checks"] if c["check"] == "acceptance:summarize:0")
    assert check["passed"] is False
    assert check["detail"]["observed"] == {"words": 2, "characters": 7}
    with core.client() as client:
        assert (
            client.post(
                f"/api/builds/{created['build_id']}/invoke",
                json={"action_id": "summarize", "input": {}},
            ).status_code
            == 409
        )


def test_cancel_terminates_builder_and_descendants(core: CoreProcess) -> None:
    created = submit(core, "fake:hang")
    tool_use = wait_for_build_event(core, created["build_id"], "harness.harness.tool_use")
    child_pid = int(tool_use["payload"]["child_pid"])
    pids = builder_pids()
    assert pids and pid_alive(child_pid)
    with core.client() as client:
        response = client.post(f"/api/builds/{created['build_id']}/cancel")
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"
    assert wait_until_dead(child_pid), "descendant survived cancel"
    for pid in pids:
        assert wait_until_dead(pid), f"builder {pid} survived cancel"
    final = wait_for_build(core, created["build_id"], {"cancelled"})
    assert final["terminal_reason"] == "cancelled_by_user"
    time.sleep(0.5)
    assert get_build(core, created["build_id"])["attempts"][0]["status"] == "cancelled"
    with core.client() as client:
        assert client.post(f"/api/builds/{created['build_id']}/cancel").status_code == 409


def test_one_builder_at_a_time_and_waiting_builds_queue(core: CoreProcess) -> None:
    running = submit(core, "fake:hang")
    wait_for_build_event(core, running["build_id"], "harness.harness.tool_use")
    waiting = submit(core, "fake:succeed count words")
    later = submit(core, "fake:succeed count words")
    queued = {
        b["build_id"]: next(
            e for e in build_events(core, b["build_id"]) if e["kind"] == "build.queued"
        )
        for b in (waiting, later)
    }
    assert queued[waiting["build_id"]]["payload"]["ahead"] == 1
    assert queued[later["build_id"]]["payload"]["ahead"] == 2

    # While the first build holds the builder, the others wait without an attempt or process.
    time.sleep(1.0)
    for build in (waiting, later):
        record = get_build(core, build["build_id"])
        assert record["state"] == "queued" and record["attempts"] == [], record

    # A waiting build can be cancelled and never builds.
    with core.client() as client:
        response = client.post(f"/api/builds/{waiting['build_id']}/cancel")
    assert response.status_code == 200 and response.json()["state"] == "cancelled"

    # Ending the running build hands the builder to the next waiting one.
    with core.client() as client:
        assert client.post(f"/api/builds/{running['build_id']}/cancel").status_code == 200
    final = wait_for_build(core, later["build_id"], {"ready", "failed", "cancelled"})
    assert final["state"] == "ready", final
    cancelled = get_build(core, waiting["build_id"])
    assert cancelled["state"] == "cancelled" and cancelled["attempts"] == []
    # The next attempt starts only after the previous builder process tree is gone.
    first_end = get_build(core, running["build_id"])["attempts"][0]["finished_at"]
    assert final["attempts"][0]["started_at"] >= first_end


def test_attempt_deadline_is_enforced_outside_the_harness(data_dir: Path) -> None:
    core = start_core(data_dir, extra_env={"ALPHA_BUILD_MAX_ATTEMPT_SECONDS": "2"})
    try:
        created = submit(core, "fake:hang")
        final = wait_for_build(
            core, created["build_id"], {"ready", "failed", "cancelled"}, timeout=20
        )
        assert final["state"] == "failed"
        assert final["failure_category"] == "harness_timeout"
        assert final["terminal_reason"] == "attempt_deadline_exceeded"
        assert builder_pids() == []
    finally:
        core.stop()


def test_restart_interrupts_running_build_and_does_not_revive_it(data_dir: Path) -> None:
    first = start_core(data_dir)
    created = submit(first, "fake:hang")
    tool_use = wait_for_build_event(first, created["build_id"], "harness.harness.tool_use")
    child_pid = int(tool_use["payload"]["child_pid"])
    pids = builder_pids()
    waiting = submit(first, "fake:succeed count words")
    first.stop(sig=signal.SIGKILL)
    assert not wait_until_dead(child_pid, timeout=0.5), (
        "orphaned builder tree should still be alive"
    )

    second = start_core(data_dir, token=first.token)
    try:
        record = get_build(second, created["build_id"])
        assert record["state"] == "failed"
        assert record["terminal_reason"] == "core_restarted_builder_orphaned"
        assert record["attempts"][0]["status"] == "interrupted"
        assert wait_until_dead(child_pid) and all(wait_until_dead(p) for p in pids)
        time.sleep(1.0)
        assert len(get_build(second, created["build_id"])["attempts"]) == 1, (
            "obsolete build was revived"
        )
        # A build that was waiting for the builder is not started after the restart either.
        stranded = get_build(second, waiting["build_id"])
        assert stranded["state"] == "failed" and stranded["attempts"] == []
        assert stranded["terminal_reason"] == "core_restarted_while_queued"
        assert stranded["failure_category"] == "interrupted"
        assert builder_pids() == []
    finally:
        second.stop()


def test_disabled_live_route_is_refused(core: CoreProcess) -> None:
    with core.client() as client:
        response = client.post(
            "/api/builds",
            json={
                "goal": "anything",
                "acceptance_examples": SUMMARIZE_EXAMPLES,
                "route_id": "claude-code-cli",
            },
        )
        assert response.status_code == 409
        assert "not enabled" in response.json()["detail"]
        assert (
            client.post(
                "/api/builds",
                json={"goal": "x", "acceptance_examples": SUMMARIZE_EXAMPLES, "route_id": "nope"},
            ).status_code
            == 409
        )
        routes = client.get("/api/model-routes").json()["routes"]
    by_id = {r["route_id"]: r for r in routes}
    assert by_id["fake"]["enabled"] is True and by_id["claude-code-cli"]["enabled"] is False
    assert by_id["claude-code-cli"]["cost_basis"] == "subscription_unmetered"


def test_build_requests_are_validated(core: CoreProcess) -> None:
    with core.client() as client:
        assert (
            client.post(
                "/api/builds", json={"goal": "", "acceptance_examples": SUMMARIZE_EXAMPLES}
            ).status_code
            == 422
        )
        assert (
            client.post("/api/builds", json={"goal": "x", "acceptance_examples": []}).status_code
            == 422
        )
        assert (
            client.post(
                "/api/builds",
                json={"goal": "x", "acceptance_examples": SUMMARIZE_EXAMPLES, "api_key": "sk"},
            ).status_code
            == 422
        )
        assert client.get("/api/builds/build_missing").status_code == 404
    assert httpx.get(f"{core.base_url}/api/builds", timeout=5).status_code == 401
