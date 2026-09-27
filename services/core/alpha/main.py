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
from typing import Any

import uvicorn
from alpha_contracts.apps import ScheduleSpec
from fastapi import FastAPI

from alpha import __version__
from alpha.api.app import create_app, shutting_down
from alpha.api.apps_routes import AppPlatform
from alpha.artifacts.service import ArtifactService
from alpha.assistant.service import AssistantService
from alpha.builds.preview import PreviewDeps
from alpha.builds.service import BuildPipeline, BuildService
from alpha.builds.toolchain import PlatformResources, UiToolchain
from alpha.builds.ui_check import UiRenderCheck
from alpha.builds.verify import CandidateVerifier
from alpha.capabilities.browser import BrowserService
from alpha.capabilities.errors import OperationFailed
from alpha.capabilities.web import WebService
from alpha.config import ConfigError, CoreSettings
from alpha.data.store import RecordService
from alpha.execution.app_runs import AppRunService, HandlerBinder
from alpha.execution.broker import CapabilityBroker
from alpha.execution.coordinator import RunCoordinator
from alpha.execution.profiles import ProfileInventory
from alpha.execution.scheduler import Scheduler
from alpha.execution.supervisor import WorkerSupervisor
from alpha.models.gateway import ModelGateway
from alpha.models.preferences import Preferences
from alpha.models.runtime import AppModelService
from alpha.models.structured import StructuredInference
from alpha.solutions.creation import CreationRoutes, CreationService
from alpha.solutions.describe import module_summary
from alpha.solutions.planner import AcceptancePlanner
from alpha.solutions.registry import AppRegistry
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
    report = coordinator.reconcile_on_startup()
    if report:
        log.warning("reconciled %d interrupted run(s) on startup: %s", len(report), report)
    gateway = ModelGateway(
        store,
        settings.enabled_model_routes,
        max_attempt_seconds=settings.build_max_attempt_seconds,
        max_total_seconds=settings.build_max_total_seconds,
        preferences=Preferences(store),
    )
    inference = StructuredInference(
        gateway,
        claude_binary="claude",
        tool_path=settings.builder_path,
        home=settings.builder_home,
    )
    toolchain = ui_toolchain(settings)
    platform = build_app_platform(
        settings, store, coordinator, supervisor, gateway, inference, toolchain
    )
    builds = BuildService(
        store,
        supervisor,
        gateway,
        build_pipeline(settings, platform, supervisor, gateway, inference, toolchain),
        builds_root=settings.builds_root,
        builder_path=settings.builder_path,
        builder_home=settings.builder_home,
        instance_id=coordinator.instance_id,
        custom_ui=settings.custom_ui,
    )
    build_report = builds.reconcile_on_startup()
    if build_report:
        log.warning(
            "reconciled %d interrupted build(s) on startup: %s", len(build_report), build_report
        )
    resources = (
        PlatformResources(settings.platform_resources) if settings.platform_resources else None
    )
    assistant = AssistantService(
        store,
        gateway,
        inference,
        default_route=settings.assistant_route,
        app_model_route=settings.app_model_route,
        describe_app=lambda app_id: _describe_app(platform.registry, app_id),
    )
    creations = CreationService(
        store,
        assistant,
        builds,
        AcceptancePlanner(inference),
        gateway,
        CreationRoutes(planner=settings.assistant_route, builder=settings.builder_route),
        poll_seconds=settings.creation_poll_seconds,
        registry=platform.registry,
        inference=inference,
        contract_reference=resources.app_contract_reference if resources else None,
        sdk_reference=resources.sdk_reference if resources else None,
    )
    assistant.on_quick_change = creations.start
    stalled = assistant.reconcile_on_startup()
    if stalled:
        log.warning(
            "marked %d conversation turn(s) interrupted by restart: %s", len(stalled), stalled
        )
    interrupted = creations.reconcile_on_startup()
    if interrupted:
        log.warning("marked %d unfinished creation(s) interrupted", len(interrupted))
    moved = _move_apps_to_current_runtime(platform.registry, platform.inventory)
    if moved:
        log.info("moved %d App(s) to the current runtime profile: %s", len(moved), moved)
    platform.scheduler = Scheduler(
        store,
        active_apps=lambda: _scheduled_apps(platform.registry),
        invoke=lambda app_id, action_id, payload, origin: (
            platform.runs.invoke(app_id, action_id, payload, origin=origin).run_id
        ),
        timezone=settings.timezone,
    )
    platform.scheduler.start()
    app = create_app(settings, store, coordinator, builds, gateway, assistant, platform, creations)
    return app, store, coordinator, builds


def _move_apps_to_current_runtime(registry: AppRegistry, inventory: ProfileInventory) -> list[str]:
    """Every active App runs on the newest runtime profile (the one carrying the current SDK),
    so a platform improvement reaches modules already made. An App whose handlers do not bind
    on it keeps its version and says so in the log."""
    profile = inventory.default_app_profile()
    if profile is None:
        return []
    moved: list[str] = []
    for entry in registry.list_apps():
        if entry.get("state") != "active" or not entry.get("current_version_id"):
            continue
        app_id = entry["app_id"]
        try:
            if registry.current(app_id).runtime_profile_id == profile.profile_id:
                continue
            registry.move_to_profile(app_id, profile)
            moved.append(app_id)
        except Exception:
            log.exception(
                "%s could not move to %s; it keeps its version", app_id, profile.profile_id
            )
    return moved


def _describe_app(registry: AppRegistry, app_id: str) -> str | None:
    """A plain summary of an installed App for the assistant, or None when there is none."""
    try:
        return module_summary(registry.current(app_id).source)
    except OperationFailed:
        return None


def _scheduled_apps(registry: AppRegistry) -> list[tuple[str, list[ScheduleSpec]]]:
    """Every active App with at least one declared schedule."""
    found: list[tuple[str, list[ScheduleSpec]]] = []
    for entry in registry.list_apps():
        if entry.get("state") != "active" or not entry.get("current_version_id"):
            continue
        try:
            source = registry.current(entry["app_id"]).source
        except OperationFailed:
            continue
        if source.schedules:
            found.append((entry["app_id"], list(source.schedules)))
    return found


def _append(store: ControlStore, run_id: str, kind: str, payload: dict[str, Any]) -> None:
    store.append_event(run_id, kind, payload)


def ui_toolchain(settings: CoreSettings) -> UiToolchain | None:
    """The trusted UI tools, when the host configured Node and the platform resources."""
    if settings.node_binary is None or settings.platform_resources is None:
        return None
    return UiToolchain(
        node=settings.node_binary,
        resources=PlatformResources(settings.platform_resources),
        browser=settings.ui_browser,
    )


def build_app_platform(
    settings: CoreSettings,
    store: ControlStore,
    coordinator: RunCoordinator,
    supervisor: WorkerSupervisor,
    gateway: ModelGateway,
    inference: StructuredInference,
    toolchain: UiToolchain | None = None,
) -> AppPlatform:
    """F05 services: profile inventory, App records/artifacts/models, broker and App runs."""
    inventory = ProfileInventory(store, settings.profiles_dir)
    profile_report = inventory.scan()
    log.info("runtime profiles: %s", profile_report)
    records = RecordService(settings.apps_root)
    artifacts = ArtifactService(store, settings.artifacts_root)
    artifact_report = artifacts.reconcile_on_startup()
    if any(artifact_report.values()):
        log.warning("artifact reconciliation: %s", artifact_report)
    models = AppModelService(store, gateway, inference, settings.app_model_route)
    browser = BrowserService(
        store,
        node=settings.node_binary,
        script=(
            PlatformResources(settings.platform_resources).browser_worker
            if settings.platform_resources
            else None
        ),
        root=settings.data_dir / "browser",
        preferences=gateway.preferences,
    )
    broker = CapabilityBroker(
        store,
        records,
        artifacts,
        models,
        on_event=lambda run_id, kind, payload: _append(store, run_id, kind, payload),
        web=WebService(),
        browser=browser,
    )
    revoked = broker.revoke_all_on_startup()
    if revoked:
        log.info("revoked %d workload token(s) left by a previous Core", revoked)
    binder = HandlerBinder(supervisor)
    registry = AppRegistry(
        store,
        inventory,
        records,
        settings.versions_root,
        validator=binder.validate_handlers,
        ui_builder=toolchain.build_ui if toolchain else None,
    )
    registry.reconcile_on_startup()
    runs = AppRunService(
        coordinator, supervisor, registry, inventory, broker, timezone=settings.timezone
    )
    return AppPlatform(
        inventory=inventory,
        records=records,
        artifacts=artifacts,
        models=models,
        broker=broker,
        registry=registry,
        runs=runs,
        binder=binder,
        fixture_apps_dir=settings.dev_fixture_apps_dir,
        browser=browser,
    )


def build_pipeline(
    settings: CoreSettings,
    platform: AppPlatform,
    supervisor: WorkerSupervisor,
    gateway: ModelGateway,
    inference: StructuredInference,
    toolchain: UiToolchain | None,
) -> BuildPipeline:
    """F07: verify candidates in isolated previews on the exact profiles, then activate."""
    preview = PreviewDeps(
        supervisor=supervisor,
        inventory=platform.inventory,
        handler_validator=platform.binder.validate_handlers,
        models=lambda store: AppModelService(store, gateway, inference, settings.app_model_route),
        timezone=settings.timezone,
    )
    verifier = CandidateVerifier(
        platform.registry,
        platform.binder,
        preview,
        UiRenderCheck(supervisor, platform.inventory, toolchain) if toolchain else None,
        toolchain.build_ui if toolchain else None,
    )
    return BuildPipeline(
        inventory=platform.inventory,
        registry=platform.registry,
        verifier=verifier,
        preview=preview,
        resources=PlatformResources(settings.platform_resources or settings.data_dir / "missing"),
        fake_packages_dir=settings.fake_builder_packages,
        seed_packages_dir=settings.dev_seed_packages_dir,
    )


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
            platform = getattr(app.state, "platform", None)
            if platform is not None:
                platform.close()
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
