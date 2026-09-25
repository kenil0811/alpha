"""F01.C02 (control portion): worker success, error, crash, timeout and cancellation produce
honest durable state, and process-group termination removes descendants."""

from __future__ import annotations

import pytest

from tests.integration.conftest import CoreProcess, pid_alive, wait_until_dead

pytestmark = pytest.mark.integration


def _child_pid(core: CoreProcess, run_id: str) -> int:
    return core.child_pid(run_id)


def test_successful_run_streams_events_and_stores_output(core: CoreProcess) -> None:
    created = core.submit(text="hello alpha", steps=2)
    assert created["state"] == "queued"
    assert created["owner"]["kind"] == "task"
    assert created["owner"]["plan_ref"] == "worker-profile:synthetic"
    assert created["snapshot"]["worker_profile"] == "synthetic"
    assert created["snapshot"]["input_digest"].startswith("sha256:")

    final = core.wait_for_state(created["run_id"], {"succeeded", "failed"})
    assert final["state"] == "succeeded", final
    assert final["output"]["upper"] == "HELLO ALPHA"
    assert final["output"]["words"] == 2
    assert final["started_at"] and final["finished_at"]

    kinds = [e["kind"] for e in core.events(created["run_id"])]
    assert kinds[:2] == ["run.queued", "run.started"]
    assert "worker.result" in kinds
    assert kinds[-1] == "run.succeeded"
    sequences = [e["sequence"] for e in core.events(created["run_id"])]
    assert sequences == list(range(1, len(sequences) + 1))
    assert final["latest_sequence"] == sequences[-1]


def test_descendant_does_not_keep_finished_run_alive_and_is_terminated(core: CoreProcess) -> None:
    created = core.submit(text="with child", spawn_child=True)
    child = _child_pid(core, created["run_id"])
    final = core.wait_for_state(created["run_id"], {"succeeded", "failed"})
    assert final["state"] == "succeeded"
    assert wait_until_dead(child), "descendant survived run completion"
    exited = core.wait_for_event(created["run_id"], "worker.exited")
    assert exited["payload"]["exit_code"] == 0


def test_worker_error_yields_failed_run_with_reason(core: CoreProcess) -> None:
    created = core.submit(text="x", mode="fail")
    final = core.wait_for_state(created["run_id"], {"succeeded", "failed"})
    assert final["state"] == "failed"
    assert final["terminal_reason"] == "worker_error"
    assert final["output"] is None
    failed = core.wait_for_event(created["run_id"], "run.failed")
    assert failed["payload"]["exit_code"] == 3
    assert failed["payload"]["error"]["code"] == "synthetic_fail"


def test_worker_crash_without_output_is_failed_not_succeeded(core: CoreProcess) -> None:
    created = core.submit(text="x", mode="crash")
    final = core.wait_for_state(created["run_id"], {"succeeded", "failed"})
    assert final["state"] == "failed"
    assert final["terminal_reason"] == "worker_exit_nonzero"


def test_clean_exit_without_result_is_not_success(core: CoreProcess) -> None:
    created = core.submit(text="x", mode="exit_without_result")
    final = core.wait_for_state(created["run_id"], {"succeeded", "failed"})
    assert final["state"] == "failed"
    assert final["terminal_reason"] == "worker_exit_without_result"


def test_cancel_terminates_worker_and_descendants(core: CoreProcess) -> None:
    created = core.submit(text="x", mode="hang", spawn_child=True)
    run_id = created["run_id"]
    child = _child_pid(core, run_id)
    started = core.wait_for_event(run_id, "run.started")
    worker_pid = int(started["payload"]["worker_pid"])
    assert pid_alive(worker_pid) and pid_alive(child)

    with core.client() as client:
        response = client.post(f"/api/runs/{run_id}/cancel")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "cancelled"
    assert body["terminal_reason"] == "cancelled_by_user"
    termination = core.wait_for_event(run_id, "run.cancelled")["payload"]["termination"]
    assert termination["worker_running"] is True
    assert termination["sigterm_sent"] is True

    assert wait_until_dead(worker_pid), "worker leader survived cancel"
    assert wait_until_dead(child), "descendant survived cancel"

    # Terminal state is never rewritten by the worker exit path.
    core.wait_for_event(run_id, "worker.exited")
    assert core.run(run_id)["state"] == "cancelled"
    with core.client() as client:
        assert client.post(f"/api/runs/{run_id}/cancel").status_code == 409


def test_timeout_terminates_hung_worker(core: CoreProcess) -> None:
    created = core.submit(text="x", mode="hang", timeout_seconds=1)
    final = core.wait_for_state(created["run_id"], {"succeeded", "failed", "cancelled"}, timeout=15)
    assert final["state"] == "failed"
    assert final["terminal_reason"] == "timeout_exceeded"
    kinds = [e["kind"] for e in core.events(created["run_id"])]
    assert kinds.index("worker.timeout") < kinds.index("run.failed")


def test_invalid_payload_rejected_before_any_run_exists(core: CoreProcess) -> None:
    with core.client() as client:
        assert client.post("/api/runs", json={"mode": "rm -rf"}).status_code == 422
        assert client.post("/api/runs", json={"text": "x", "grants": ["all"]}).status_code == 422
        assert client.get("/api/runs/run_missing").status_code == 404
        assert client.post("/api/runs/run_missing/cancel").status_code == 404


def test_sse_stream_resumes_from_cursor(core: CoreProcess) -> None:
    created = core.submit(text="stream me", steps=1)
    core.wait_for_state(created["run_id"], {"succeeded"})
    seen: list[dict[str, object]] = []
    with (
        core.client() as client,
        client.stream("GET", "/api/events/stream", params={"after": 0}) as response,
    ):
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        current_id: int | None = None
        for line in response.iter_lines():
            if line.startswith("id: "):
                current_id = int(line[4:])
            elif line.startswith("data: "):
                import json

                payload = json.loads(line[6:])
                seen.append({"cursor": current_id, **payload["event"]})
                if payload["event"]["kind"] == "run.succeeded":
                    break
    assert seen[0]["cursor"] == 1
    assert [e["kind"] for e in seen][0] == "run.queued"
    assert seen[-1]["kind"] == "run.succeeded"


def test_sse_stream_delivers_every_event_in_order(core: CoreProcess) -> None:
    """A consumer connected before the run must receive the complete event sequence."""
    import json
    import threading

    received: list[tuple[int, int, str]] = []
    stop = threading.Event()

    def consume() -> None:
        with (
            core.client() as client,
            client.stream("GET", "/api/events/stream", params={"after": 0}) as response,
        ):
            current_id = 0
            for line in response.iter_lines():
                if line.startswith("id: "):
                    current_id = int(line[4:])
                elif line.startswith("data: "):
                    event = json.loads(line[6:])["event"]
                    received.append((current_id, event["sequence"], event["kind"]))
                    if event["kind"] == "run.succeeded":
                        stop.set()
                        return

    consumer = threading.Thread(target=consume, daemon=True)
    consumer.start()
    created = core.submit(text="every event", steps=3, spawn_child=True)
    core.wait_for_state(created["run_id"], {"succeeded"})
    assert stop.wait(10), "stream did not deliver run.succeeded"
    stored = [(e["sequence"], e["kind"]) for e in core.events(created["run_id"])]
    assert [(s, k) for _, s, k in received] == stored
    cursors = [c for c, _, _ in received]
    assert cursors == sorted(cursors) and len(set(cursors)) == len(cursors)


def test_idle_sse_stream_sends_keepalives(core: CoreProcess) -> None:
    import time as _time

    seen_keepalive = False
    deadline = _time.monotonic() + 4
    with (
        core.client() as client,
        client.stream("GET", "/api/events/stream", params={"after": 0}) as response,
    ):
        for line in response.iter_lines():
            if line.startswith(": keepalive"):
                seen_keepalive = True
                break
            if _time.monotonic() > deadline:
                break
    assert seen_keepalive, "idle stream sent no keepalive within 4 s"
