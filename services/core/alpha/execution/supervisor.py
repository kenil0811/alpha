"""WorkerSupervisor: launches registered worker profiles as separate process groups with an
allowlisted environment and private scratch, and terminates whole process trees.

Registered profiles are typed records. Nothing here accepts a shell command string.
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO


@dataclass(frozen=True)
class WorkerProfile:
    """A registered worker definition. `module` is executed with the platform interpreter."""

    name: str
    module: str
    description: str


SYNTHETIC_PROFILE = WorkerProfile(
    name="synthetic",
    module="alpha.workers.synthetic",
    description="F01 transport fixture: echoes a payload through a supervised subprocess.",
)
BUILDER_PROFILE = WorkerProfile(
    name="builder",
    module="alpha.workers.builder",
    description="Runs a builder harness in a leased workspace; emits normalized events.",
)
CANDIDATE_RUNNER_PROFILE = WorkerProfile(
    name="candidate_runner",
    module="alpha.workers.candidate_runner",
    description="Disposable process that resolves and executes a candidate action handler.",
)
APP_PROFILE = WorkerProfile(
    name="app",
    module="alpha_app_worker",
    description=(
        "Generated App computation: runs a sealed Version's handler with the SDK context, using "
        "the exact interpreter of the Version's installed runtime profile (never Core's)."
    ),
)


@dataclass
class WorkerHandle:
    profile: WorkerProfile
    process: subprocess.Popen[str]
    pgid: int
    scratch_dir: Path

    @property
    def pid(self) -> int:
        return self.process.pid

    @property
    def stdout(self) -> IO[str]:
        assert self.process.stdout is not None
        return self.process.stdout


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    # A zombie still answers kill(0); check its state via waitpid without blocking.
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            return False
    except ChildProcessError:
        pass
    return True


def terminate_group(pgid: int, grace_seconds: float) -> dict[str, object]:
    """SIGTERM a process group, wait up to `grace_seconds`, then SIGKILL survivors.

    Returns an evidence record describing what was observed."""
    record: dict[str, object] = {"pgid": pgid, "grace_seconds": grace_seconds}
    try:
        os.killpg(pgid, signal.SIGTERM)
        record["sigterm_sent"] = True
    except ProcessLookupError:
        record["sigterm_sent"] = False
        record["already_gone"] = True
        return record
    except PermissionError:
        record["sigterm_sent"] = False
        record["sigterm_permission_denied"] = True
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _group_alive(pgid):
            record["sigkill_sent"] = False
            return record
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
        record["sigkill_sent"] = True
    except ProcessLookupError:
        record["sigkill_sent"] = False
    except PermissionError:
        # macOS reports EPERM for a group whose only members are zombies awaiting reaping.
        record["sigkill_sent"] = False
        record["sigkill_permission_denied"] = True
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and _group_alive(pgid):
        time.sleep(0.05)
    record["group_alive_after"] = _group_alive(pgid)
    return record


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class WorkerSupervisor:
    def __init__(self, python: Path, scratch_root: Path, grace_seconds: float) -> None:
        self._python = python
        self._scratch_root = scratch_root
        self._grace = grace_seconds
        self._profiles: dict[str, WorkerProfile] = {
            p.name: p
            for p in (SYNTHETIC_PROFILE, BUILDER_PROFILE, CANDIDATE_RUNNER_PROFILE, APP_PROFILE)
        }

    @property
    def python(self) -> Path:
        return self._python

    def profiles(self) -> dict[str, WorkerProfile]:
        return dict(self._profiles)

    def profile(self, name: str) -> WorkerProfile:
        try:
            return self._profiles[name]
        except KeyError as exc:
            raise KeyError(f"unregistered worker profile: {name}") from exc

    def launch(
        self,
        profile_name: str,
        job_id: str,
        *,
        extra_env: dict[str, str] | None = None,
        python: Path | None = None,
    ) -> WorkerHandle:
        """Launch a registered profile. `python` selects a runtime profile's exact interpreter
        (App workers); platform workers use Core's own interpreter."""
        profile = self.profile(profile_name)
        scratch = self._scratch_root / job_id
        scratch.mkdir(parents=True, exist_ok=False)
        env = {
            "ALPHA_RUN_ID": job_id,
            "ALPHA_SCRATCH_DIR": str(scratch),
            "ALPHA_WORKER_PROFILE": profile.name,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "LC_ALL": "C.UTF-8",
            "HOME": str(scratch),
            "TMPDIR": str(scratch),
        }
        if extra_env:
            env.update(extra_env)
        process = subprocess.Popen(
            [str(python or self._python), "-I", "-B", "-m", profile.module],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(scratch),
            env=env,
            text=True,
            encoding="utf-8",
            start_new_session=True,
        )
        pgid = os.getpgid(process.pid)
        return WorkerHandle(profile=profile, process=process, pgid=pgid, scratch_dir=scratch)

    def terminate(self, handle: WorkerHandle) -> dict[str, object]:
        record = terminate_group(handle.pgid, self._grace)
        try:
            handle.process.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            record["leader_wait_timeout"] = True
        return record

    def terminate_orphan(self, pgid: int) -> dict[str, object]:
        return terminate_group(pgid, self._grace)
