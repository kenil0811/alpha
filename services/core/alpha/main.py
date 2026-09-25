"""Core entry point. Launched by the native host with an allowlisted environment.

Binds loopback only on an OS-assigned port, reconciles durable state, then announces readiness
on stdout as one line: ALPHA_CORE_READY {"port": N, ...}. SIGTERM/SIGINT trigger a graceful
shutdown that terminates every worker process tree and marks their runs interrupted.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import sys
import threading
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import FrameType

import uvicorn
from fastapi import FastAPI

from alpha import __version__
from alpha.api.app import create_app, shutting_down
from alpha.assistant.service import AssistantService
from alpha.builds.service import BuildService
from alpha.config import ConfigError, CoreSettings
from alpha.execution.coordinator import RunCoordinator
from alpha.execution.supervisor import WorkerSupervisor
from alpha.models.gateway import ModelGateway
from alpha.models.structured import StructuredInference
from alpha.storage.control_store import ControlStore
from alpha.storage.lock import DataDirectoryBusy, DataDirectoryLock

log = logging.getLogger("alpha.main")


def build(
    settings: CoreSettings,
) -> tuple[FastAPI, ControlStore, RunCoordinator, BuildService]:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.scratch_root.mkdir(parents=True, exist_ok=True)
    store = ControlStore(settings.control_db_path)
    supervisor = WorkerSupervisor(
        python=settings.worker_python,
        scratch_root=settings.scratch_root,
        grace_seconds=settings.worker_grace_seconds,
    )
    coordinator = RunCoordinator(
        store,
        supervisor,
        workspace_id=settings.workspace_id,
        default_timeout_seconds=settings.default_timeout_seconds,
    )
    gateway = ModelGateway(
        store,
        settings.enabled_model_routes,
        max_attempt_seconds=settings.build_max_attempt_seconds,
    )
    builds = BuildService(
        store,
        supervisor,
        gateway,
        builds_root=settings.builds_root,
        platform_python=settings.worker_python,
        builder_path=settings.builder_path,
        builder_home=settings.builder_home,
        instance_id=coordinator.instance_id,
    )
    report = coordinator.reconcile_on_startup()
    if report:
        log.warning("reconciled %d interrupted run(s) on startup: %s", len(report), report)
    build_report = builds.reconcile_on_startup()
    if build_report:
        log.warning(
            "reconciled %d interrupted build(s) on startup: %s", len(build_report), build_report
        )
    inference = StructuredInference(
        gateway,
        claude_binary="claude",
        tool_path=settings.builder_path,
        home=settings.builder_home,
    )
    assistant = AssistantService(store, gateway, inference, default_route=settings.assistant_route)
    app = create_app(settings, store, coordinator, builds, gateway, assistant)
    return app, store, coordinator, builds


class CoreServer(uvicorn.Server):
    """uvicorn server whose exit path stops worker trees first.

    A graceful HTTP shutdown waits for open connections, and the shell keeps a long-lived SSE
    stream open, so worker cleanup cannot wait for the lifespan shutdown: it runs the moment an
    exit is requested (signal or lost host), and the stream generators observe the same flag."""

    def __init__(
        self, config: uvicorn.Config, coordinator: RunCoordinator, builds: BuildService
    ) -> None:
        super().__init__(config)
        self._coordinator = coordinator
        self._builds = builds
        self._stopping = threading.Lock()
        self._stopped = False

    def stop_workers_once(self, reason: str) -> None:
        with self._stopping:
            if self._stopped:
                return
            self._stopped = True
        shutting_down.set()
        interrupted = self._coordinator.shutdown(reason)
        interrupted_builds = self._builds.shutdown(reason)
        log.info(
            "exit requested (%s): interrupted runs %s, builds %s",
            reason,
            interrupted,
            interrupted_builds,
        )

    def handle_exit(self, sig: int, frame: FrameType | None) -> None:
        self.stop_workers_once("runtime_quit")
        super().handle_exit(sig, frame)


def watch_parent(server: CoreServer, parent_pid: int, interval: float = 1.0) -> None:
    """Stop serving when the launching host process disappears. A dead host cannot quit Core,
    so Core quits itself (graceful path: workers terminated, runs marked interrupted)."""
    while not server.should_exit:
        if os.getppid() != parent_pid:
            log.warning("host process %s is gone; shutting down", parent_pid)
            server.stop_workers_once("runtime_quit")
            server.should_exit = True
            return
        time.sleep(interval)


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr, format="%(name)s %(levelname)s %(message)s"
    )
    try:
        settings = CoreSettings.from_env()
    except ConfigError as exc:
        print(f"ALPHA_CORE_ERROR {json.dumps({'error': str(exc)})}", flush=True)
        return 2
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    lock = DataDirectoryLock(settings.data_dir / "runtime.lock")
    try:
        lock.acquire()
    except DataDirectoryBusy as exc:
        print(f"ALPHA_CORE_ERROR {json.dumps({'error': str(exc)})}", flush=True)
        return 3
    app, store, coordinator, builds = build(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            interrupted = coordinator.shutdown("runtime_quit")
            builds.shutdown("runtime_quit")
            log.info("shutdown: interrupted runs %s", interrupted)
            store.close()
            lock.release()

    app.router.lifespan_context = lifespan

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((settings.host, settings.port))
    sock.listen(128)
    port = sock.getsockname()[1]
    ready = {
        "port": port,
        "host": settings.host,
        "core_version": __version__,
        "core_instance_id": coordinator.instance_id,
        "pid": os.getpid(),
        "python_executable": sys.executable,
        "data_dir": str(settings.data_dir),
        "enabled_model_routes": sorted(settings.enabled_model_routes),
    }
    print(f"ALPHA_CORE_READY {json.dumps(ready)}", flush=True)
    config = uvicorn.Config(
        app, log_level="warning", access_log=False, lifespan="on", timeout_graceful_shutdown=2
    )
    server = CoreServer(config, coordinator, builds)
    if os.environ.get("ALPHA_WATCH_PARENT", "1") == "1":
        watcher = threading.Thread(
            target=watch_parent, args=(server, os.getppid()), daemon=True, name="parent-watch"
        )
        watcher.start()
    server.run(sockets=[sock])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
