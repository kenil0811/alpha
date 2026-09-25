"""F01.C04 (control portion): a host process that dies without quitting cannot orphan Core.
Core notices its parent is gone, terminates worker trees and marks runs interrupted."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.integration.conftest import (
    REPO_ROOT,
    CoreProcess,
    hold_stream_open,
    pid_alive,
    start_core,
    wait_until_dead,
)

pytestmark = pytest.mark.integration

LAUNCHER = """
import os, subprocess, sys, json
env = dict(os.environ)
child = subprocess.Popen(
    [sys.executable, "-m", "alpha.main"], env=env, stdout=subprocess.PIPE, text=True
)
line = child.stdout.readline()
info = {"launcher_pid": os.getpid(), "core_pid": child.pid, "ready": line.strip()}
print(json.dumps(info), flush=True)
child.stdout.close()
import time
while True:
    time.sleep(1)
"""


def test_core_exits_when_host_process_dies(data_dir: Path) -> None:
    token = "h" * 64
    env = {
        "ALPHA_DATA_DIR": str(data_dir),
        "ALPHA_SESSION_TOKEN": token,
        "ALPHA_ALLOWED_ORIGINS": "http://localhost:1420",
        "ALPHA_WORKER_GRACE_SECONDS": "0.5",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    launcher = subprocess.Popen(
        [sys.executable, "-c", LAUNCHER],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert launcher.stdout is not None
    info = json.loads(launcher.stdout.readline())
    ready = json.loads(info["ready"].removeprefix("ALPHA_CORE_READY "))
    core_pid = int(info["core_pid"])
    core = CoreProcess(
        process=launcher,  # only used for base_url/token helpers below
        port=int(ready["port"]),
        token=token,
        data_dir=data_dir,
        ready=ready,
        stderr_path=data_dir / "unused",
    )
    try:
        assert hold_stream_open(core).wait(5), "stream did not connect"
        created = core.submit(text="x", mode="hang", spawn_child=True)
        run_id = created["run_id"]
        worker_pid = int(core.wait_for_event(run_id, "run.started")["payload"]["worker_pid"])
        child_pid = core.child_pid(run_id)
        core.wait_for_event(run_id, "worker.progress", stage="hanging")
        assert pid_alive(core_pid) and pid_alive(worker_pid) and pid_alive(child_pid)

        os.kill(launcher.pid, signal.SIGKILL)
        launcher.wait(timeout=5)

        assert wait_until_dead(core_pid, timeout=10), "core outlived its dead host"
        assert wait_until_dead(worker_pid), "worker outlived its dead host"
        assert wait_until_dead(child_pid), "descendant outlived its dead host"
    finally:
        if pid_alive(core_pid):
            os.kill(core_pid, signal.SIGKILL)

    # Durable state is honest after the fact.
    time.sleep(0.2)
    second = start_core(data_dir, token=token)
    try:
        run = second.run(run_id)
        assert run["state"] == "interrupted"
        assert run["terminal_reason"] == "runtime_quit"
    finally:
        second.stop()
