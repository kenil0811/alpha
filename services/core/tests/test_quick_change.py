"""Quick changes: a small edit to a module is made directly from the person's words, with the
platform's identity lines kept and the package still validating, in about a minute."""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from alpha.assistant.prompts import fake_triage, triage_prompt
from alpha.solutions.creation import (
    CreationRoutes,
    CreationService,
    apply_edits,
    keep_identity,
    read_package_files,
)
from alpha.storage.control_store import ControlStore

APP_YAML = """contract_version: "0.2"
app_id: notes-list-1a2b3c
name: Notes list
description: Short notes you keep.
runtime_profile: pyprof-old
sdk_version: 0.1.0
"""


def version_dir(tmp_path: Path) -> Path:
    root = tmp_path / "versions" / "ver_1"
    (root / "src" / "app_code").mkdir(parents=True)
    (root / "dependencies").mkdir()
    (root / "app.yaml").write_text(APP_YAML)
    (root / "src" / "app_code" / "handlers.py").write_text("def add(ctx):\n    return {}\n")
    (root / "src" / "app_code" / "__init__.py").write_text("")
    (root / "package.index.json").write_text("{}")
    (root / "dependencies" / "x.txt").write_text("sealed")
    return root


def test_the_files_a_change_may_see_and_edit(tmp_path: Path) -> None:
    files = read_package_files(version_dir(tmp_path))
    assert sorted(files) == ["app.yaml", "src/app_code/__init__.py", "src/app_code/handlers.py"]
    source = SimpleNamespace(
        app_id="notes-list-1a2b3c", runtime_profile="pyprof-old", sdk_version="0.1.0"
    )
    package = tmp_path / "package"
    package.mkdir()
    changed = APP_YAML.replace("Short notes you keep.", "Notes and moods.").replace(
        "app_id: notes-list-1a2b3c", "app_id: sneaky"
    )
    assert (
        apply_edits(package, {"app.yaml": changed, "src/app_code/new.py": "x = 1\n"}, source)
        is None
    )
    written = (package / "app.yaml").read_text()
    assert "app_id: notes-list-1a2b3c" in written and "Notes and moods." in written
    assert (package / "src" / "app_code" / "new.py").read_text() == "x = 1\n"
    assert (
        apply_edits(package, {"../escape.py": ""}, source)
        == "../escape.py is not a path inside the package"
    )
    assert (
        apply_edits(package, {"dist/x.js": ""}, source)
        == "dist/x.js is outside app.yaml, src/ and tests/"
    )
    assert (
        apply_edits(package, {"src/app_code/a.sh": ""}, source)
        == "src/app_code/a.sh is not a file kind a change may write"
    )
    assert "runtime_profile: pyprof-old" in keep_identity("runtime_profile: other\n", source)


def test_triage_sends_small_edits_the_quick_way() -> None:
    assert fake_triage(triage_prompt("Remove the log food box", "Name: Diet"))["path"] == "quick"
    assert (
        fake_triage(triage_prompt("Also track water intake per day", "Name: Diet"))["path"]
        == "full"
    )


class Registry:
    def __init__(self, location: Path) -> None:
        self.location = location
        self.installed: list[tuple[Path, Any]] = []
        self.source = SimpleNamespace(
            app_id="notes-list-1a2b3c",
            name="Notes list",
            runtime_profile="pyprof-old",
            sdk_version="0.1.0",
            actions=[SimpleNamespace(id="add")],
            ui=None,
            has_screen=lambda: True,
        )

    def current(self, app_id: str) -> Any:
        return SimpleNamespace(
            app_id=app_id,
            release_id="rel_1",
            location=self.location,
            origin="created",
            source=self.source,
        )

    def install(self, package: Path, activation: Any) -> Any:
        self.installed.append(((package / "app.yaml").read_text(), activation))
        return SimpleNamespace(
            app_id="notes-list-1a2b3c", release_id="rel_2", version_id="ver_2", source=self.source
        )


class Inference:
    def call(self, route: Any, *, fake: Any, **_: Any) -> Any:
        return SimpleNamespace(
            output=fake("prompt"), model="fake", usage=SimpleNamespace(model_dump=lambda mode: {})
        )


def test_a_quick_change_edits_the_module_and_switches_it_on(tmp_path: Path) -> None:
    registry = Registry(version_dir(tmp_path))
    turns = [SimpleNamespace(role="user", content={"text": "Remove the log food box"})]
    conversation = SimpleNamespace(
        conversation_id="conv_1",
        state="briefed",
        quick_change=True,
        change_of="notes-list-1a2b3c",
        current_brief=None,
        turns=turns,
    )
    svc = CreationService(
        ControlStore(tmp_path / "control.sqlite"),
        SimpleNamespace(get=lambda _cid: conversation),  # type: ignore[arg-type]
        SimpleNamespace(get=lambda _b: None, events=lambda _b: []),  # type: ignore[arg-type]
        SimpleNamespace(),  # type: ignore[arg-type]
        SimpleNamespace(route=lambda route_id, **_: SimpleNamespace(route_id=route_id)),  # type: ignore[arg-type]
        CreationRoutes(planner="fake", builder="fake"),
        poll_seconds=0.01,
        registry=registry,  # type: ignore[arg-type]
        inference=Inference(),
    )
    creation = svc.start("conv_1")
    assert creation.state in {"building", "checking", "activating", "active"}
    for thread in threading.enumerate():
        if thread.name == f"creation-{creation.creation_id}":
            thread.join(timeout=10)
    final = svc.get(creation.creation_id)
    assert final.state == "active", final.failure
    assert final.change_of == "notes-list-1a2b3c" and final.release_id == "rel_2"
    assert final.result is not None
    assert final.result["changed_files"] == ["app.yaml"] and final.result["checks_passed"] == 3
    written, activation = registry.installed[0]
    assert "Changed: Remove the log food box" in written
    assert "app_id: notes-list-1a2b3c" in written and "runtime_profile: pyprof-old" in written
    assert activation.expected_release_id == "rel_1" and activation.kind == "quick_change"
    assert [h["stage"] for h in final.history][:3] == ["building", "checking", "activating"]
