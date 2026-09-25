"""One Core per data directory: a second runtime must refuse to start, and the first keeps
serving. Without this, the second Core would reconcile the first one's live workers as orphans."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import CoreProcess, start_core

pytestmark = pytest.mark.integration


def test_second_core_on_same_data_dir_refuses_to_start(core: CoreProcess, data_dir: Path) -> None:
    created = core.submit(text="x", mode="hang", spawn_child=True)
    worker_pid = int(core.wait_for_event(created["run_id"], "run.started")["payload"]["worker_pid"])

    with pytest.raises(AssertionError) as refused:
        start_core(data_dir, token=core.token)
    assert "ALPHA_CORE_ERROR" in str(refused.value)
    assert "already using this data directory" in str(refused.value)
    assert f"holder pid {core.process.pid}" in str(refused.value)

    # The first runtime and its worker are untouched.
    assert core.run(created["run_id"])["state"] == "running"
    import os

    os.kill(worker_pid, 0)
    with core.client() as client:
        assert client.post(f"/api/runs/{created['run_id']}/cancel").status_code == 200


def test_lock_is_released_on_clean_exit(data_dir: Path) -> None:
    first = start_core(data_dir)
    first.stop()
    second = start_core(data_dir, token=first.token)
    try:
        assert second.ready["port"] > 0
    finally:
        second.stop()
