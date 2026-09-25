"""Integration fixtures: a real Core subprocess, real SQLite, real worker processes."""

from __future__ import annotations

import json
import os
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_ORIGIN = "http://localhost:1420"


@dataclass
class CoreProcess:
    process: subprocess.Popen[str]
    port: int
    token: str
    data_dir: Path
    ready: dict[str, Any]
    stderr_path: Path
    allowed_origin: str = ALLOWED_ORIGIN
    _stderr_cache: str = field(default="", repr=False)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def client(self, *, token: str | None = None, origin: str | None = None) -> httpx.Client:
        headers: dict[str, str] = {}
        headers["Authorization"] = f"Bearer {self.token if token is None else token}"
        if origin is not None:
            headers["Origin"] = origin
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=10.0)

    def submit(self, **payload: Any) -> dict[str, Any]:
        with self.client() as c:
            response = c.post("/api/runs", json=payload)
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    def run(self, run_id: str) -> dict[str, Any]:
        with self.client() as c:
            response = c.get(f"/api/runs/{run_id}")
            response.raise_for_status()
            data: dict[str, Any] = response.json()
            return data

    def events(self, run_id: str) -> list[dict[str, Any]]:
        with self.client() as c:
            response = c.get(f"/api/runs/{run_id}/events")
            response.raise_for_status()
            events: list[dict[str, Any]] = response.json()["events"]
            return events

    def wait_for_state(
        self, run_id: str, states: set[str], timeout: float = 15.0
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.run(run_id)
            if last["state"] in states:
                return last
            time.sleep(0.05)
        raise AssertionError(f"run {run_id} stayed {last.get('state')}; expected {states}")

    def wait_for_event(
        self, run_id: str, kind: str, timeout: float = 10.0, stage: str | None = None
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for event in self.events(run_id):
                if event["kind"] == kind and (
                    stage is None or event["payload"].get("stage") == stage
                ):
                    return event
            time.sleep(0.05)
        raise AssertionError(f"no {kind} event (stage={stage}) for {run_id}")

    def child_pid(self, run_id: str) -> int:
        event = self.wait_for_event(run_id, "worker.progress", stage="child_spawned")
        return int(event["payload"]["child_pid"])

    def stop(self, sig: int = signal.SIGTERM, timeout: float = 10.0) -> int:
        if self.process.poll() is None:
            self.process.send_signal(sig)
            try:
                self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        return self.process.returncode or 0

    def stderr(self) -> str:
        return self.stderr_path.read_text(encoding="utf-8", errors="replace")


def start_core(
    data_dir: Path,
    *,
    token: str | None = None,
    allowed_origin: str = ALLOWED_ORIGIN,
    grace: float = 0.5,
) -> CoreProcess:
    token = token or secrets.token_hex(32)
    env = {
        "ALPHA_DATA_DIR": str(data_dir),
        "ALPHA_SESSION_TOKEN": token,
        "ALPHA_ALLOWED_ORIGINS": allowed_origin,
        "ALPHA_WORKER_GRACE_SECONDS": str(grace),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    stderr_path = data_dir.parent / f"core-{secrets.token_hex(4)}.stderr"
    stderr_file = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "alpha.main"],
        stdout=subprocess.PIPE,
        stderr=stderr_file,
        env=env,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert process.stdout is not None
    deadline = time.monotonic() + 20
    ready: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            break
        if line.startswith("ALPHA_CORE_READY "):
            ready = json.loads(line[len("ALPHA_CORE_READY ") :])
            break
        if line.startswith("ALPHA_CORE_ERROR "):
            raise AssertionError(line)
    if ready is None:
        process.kill()
        raise AssertionError(f"core did not become ready; stderr: {stderr_path.read_text()}")
    return CoreProcess(
        process=process,
        port=int(ready["port"]),
        token=token,
        data_dir=data_dir,
        ready=ready,
        stderr_path=stderr_path,
        allowed_origin=allowed_origin,
    )


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    path = tmp_path / "alpha-data"
    path.mkdir()
    return path


@pytest.fixture
def core(data_dir: Path) -> Iterator[CoreProcess]:
    proc = start_core(data_dir)
    try:
        yield proc
    finally:
        proc.stop()


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_until_dead(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    return not pid_alive(pid)
