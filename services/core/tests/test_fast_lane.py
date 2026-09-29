"""The fast lane: a module that only keeps records is switched on after its structural checks,
its behaviour checks run right after, and the person is told where they stand.
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml
from alpha.builds.verify import fast_eligible
from alpha.solutions.creation import CreationRoutes, CreationService
from alpha.storage.control_store import ControlStore
from alpha_contracts.apps import AppSource
from alpha_contracts.builds import BuildState
from test_creation_cancel import BRIEF, Builds, service

FIXTURE = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "builds" / "notes_ok"


def notes_source(**changes: Any) -> AppSource:
    text = re.sub(r"\{\{[A-Z_]+\}\}", "x", (FIXTURE / "app.yaml.template").read_text())
    data = yaml.safe_load(text)
    data.pop("ui")
    data.update(changes)
    if "schedules" in changes:  # a scheduled action must also be invocable from a trigger
        data["actions"][1]["invocable_from"].append("trigger")
    return AppSource.model_validate(data)


def test_every_module_alpha_draws_takes_the_fast_lane() -> None:
    """Web, model, browser and scheduled modules are switched on after their structural
    checks too; only a custom compiled screen waits for the full checks."""
    assert fast_eligible(notes_source()) is True
    assert fast_eligible(notes_source(capabilities=["records", "http"])) is True
    assert fast_eligible(notes_source(capabilities=["records", "browser", "models"])) is True
    with_schedule = notes_source(
        capabilities=["records", "schedules"],
        schedules=[
            {"id": "nightly", "title": "Nightly", "action": "count_notes", "daily_at": "07:00"}
        ],
    )
    assert fast_eligible(with_schedule) is True
    text = re.sub(r"\{\{[A-Z_]+\}\}", "x", (FIXTURE / "app.yaml.template").read_text())
    custom = AppSource.model_validate(yaml.safe_load(text))
    assert custom.ui is not None and custom.ui.entry is not None
    assert fast_eligible(custom) is False


class FastBuilds(Builds):
    """Ready with behaviour checks still owed; `check_deferred` settles them."""

    def __init__(self) -> None:
        super().__init__()
        self.submitted: dict[str, Any] = {}
        self.checks: dict[str, Any] = {"status": "pending"}
        self.deferred: list[str] = []
        self.release = threading.Event()

    def submit(self, **kwargs: Any) -> Any:
        self.submitted = kwargs
        return SimpleNamespace(build_id="build_1")

    def get(self, build_id: str) -> Any:
        record = super().get(build_id)
        record.candidate = {"name": "Notes list", "actions": ["add_note"], "checks": self.checks}
        record.validation = {"checks": []}
        record.state = BuildState.READY
        return record

    def check_deferred(self, build_id: str) -> dict[str, Any]:
        self.deferred.append(build_id)
        self.release.wait(5)
        self.checks = {"status": "failed", "failed_checks": ["the count was wrong"]}
        return self.checks


def finished(svc: CreationService, creation_id: str) -> None:
    for thread in threading.enumerate():
        if thread.name == f"creation-{creation_id}":
            thread.join(timeout=10)


def test_a_fast_lane_module_is_active_while_its_behaviour_checks_run(tmp_path: Path) -> None:
    builds = FastBuilds()
    svc = service(tmp_path, builds)
    creation = svc.start("conv_1")
    finished(svc, creation.creation_id)
    assert builds.submitted["fast_lane"] is True
    final = svc.get(creation.creation_id)
    assert final.state == "active", final
    assert final.result is not None and final.result["checks"] == {"status": "pending"}
    deadline = time.monotonic() + 5
    while not builds.deferred and time.monotonic() < deadline:
        time.sleep(0.01)
    assert builds.deferred == ["build_1"], "the owed checks start once it is switched on"
    standing = svc.checks_for_app(final.app_id or "")
    assert standing is not None and standing["status"] == "pending"
    assert standing["creation_id"] == creation.creation_id and standing["change_of"] is None

    builds.release.set()
    for thread in threading.enumerate():
        if thread.name == f"checks-{creation.creation_id}":
            thread.join(timeout=10)
    standing = svc.checks_for_app(final.app_id or "")
    assert standing is not None and standing["status"] == "failed"
    assert standing["failed_checks"] == ["the count was wrong"]
    assert svc.get(creation.creation_id).state == "active", "it stays on; going back is a click"


def test_the_fast_lane_can_be_switched_off_in_settings(tmp_path: Path) -> None:
    builds = FastBuilds()
    builds.checks = {}
    svc = service(tmp_path, builds)
    prefs = SimpleNamespace(get=lambda key: "off" if key == "build.fast_lane" else "")
    svc._gateway = SimpleNamespace(  # type: ignore[assignment]
        route=lambda route_id, **_: SimpleNamespace(route_id=route_id), preferences=prefs
    )
    creation = svc.start("conv_1")
    finished(svc, creation.creation_id)
    assert builds.submitted["fast_lane"] is False
    assert builds.deferred == []


def test_a_module_without_a_fast_lane_reports_no_checks(tmp_path: Path) -> None:
    builds = Builds()
    svc = service(tmp_path, builds)
    creation = svc.start("conv_1")
    finished(svc, creation.creation_id)
    assert svc.get(creation.creation_id).state == "active"
    assert svc.checks_for_app("notes-list-x") is None


def test_routes_are_unchanged_for_the_fake_builder(tmp_path: Path) -> None:
    assert CreationRoutes(planner="fake", builder="fake").builder == "fake"
    assert BRIEF.goal == "Keep a notes list"
    assert isinstance(ControlStore(tmp_path / "c.sqlite"), ControlStore)
