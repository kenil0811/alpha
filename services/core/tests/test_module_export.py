"""A `.alphamodule` export carries only the module's source — never a record, a memory, a
secret or a run — and import rejects anything tampered with or malformed, otherwise installing
through the normal build pipeline."""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.capabilities.errors import OperationFailed
from alpha.solutions.module_export import (
    MANIFEST_NAME,
    export_module,
    import_module,
)


@dataclass
class FakeVersion:
    app_id: str
    version_id: str
    release_id: str
    location: Path
    source: Any


class FakeRegistry:
    """Just enough of `AppRegistry` for export/import: a current version by id, and an install
    call that records what it was given instead of running the real build pipeline."""

    def __init__(self) -> None:
        self._current: dict[str, FakeVersion] = {}
        # Snapshots taken *during* install (the temp dir is gone once import_module returns).
        self.installed: list[dict[str, bool]] = []
        self.install_result: FakeVersion | None = None

    def add(self, version: FakeVersion) -> None:
        self._current[version.app_id] = version

    def current(self, app_id: str) -> FakeVersion:
        if app_id not in self._current:
            raise OperationFailed("not_found", f"no App {app_id!r} is installed")
        return self._current[app_id]

    def install(self, package_dir: Path, activation: Any = None) -> FakeVersion:
        # A stand-in for what a real build would produce: read the (possibly rewritten) app_id
        # back off app.yaml, like the real pipeline does. Snapshot presence checks now — the
        # caller's temp dir is removed once `import_module` returns.
        import yaml

        doc = yaml.safe_load((package_dir / "app.yaml").read_text(encoding="utf-8"))
        self.installed.append(
            {
                "has_source": (package_dir / "src" / "app.py").is_file(),
                "has_index": (package_dir / "package.index.json").exists(),
                "has_records": (package_dir / "records.db").exists(),
            }
        )
        result = self.install_result or FakeVersion(
            app_id=doc["app_id"],
            version_id="ver_fake",
            release_id="rel_fake",
            location=package_dir,
            source=SimpleNamespace(name=doc.get("name", doc["app_id"]), ui=None),
        )
        self._current[result.app_id] = result
        return result


def _make_sealed_dir(tmp_path: Path, app_id: str = "demo_module") -> Path:
    """A sealed Version directory the way `alpha.data.packages.seal` leaves one: source files
    plus platform-produced control files and (crucially, for the exclusion test) a stray data
    file that must never leave in an export."""
    root = tmp_path / "sealed"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("def run():\n    return 'ok'\n", encoding="utf-8")
    (root / "app.yaml").write_text(f"app_id: {app_id}\nname: Demo Module\n", encoding="utf-8")
    (root / "README.md").write_text("# Demo\n", encoding="utf-8")
    # Platform-produced files a sealed Version also carries — never part of the reusable source.
    (root / "package.index.json").write_text("{}", encoding="utf-8")
    (root / "dependency.manifest.json").write_text("{}", encoding="utf-8")
    (root / "dependencies" / "python").mkdir(parents=True)
    (root / "dependencies" / "python" / "lock.txt").write_text("pin", encoding="utf-8")
    # Simulated personal data that must never be exportable, even by accident.
    (root / "records.db").write_text("personal data", encoding="utf-8")
    return root


def _source(ui: bool = False) -> Any:
    return SimpleNamespace(name="Demo Module", ui=SimpleNamespace(entry="main.tsx") if ui else None)


def test_export_excludes_platform_and_personal_data(tmp_path: Path) -> None:
    sealed = _make_sealed_dir(tmp_path)
    registry = FakeRegistry()
    registry.add(FakeVersion("demo_module", "ver_1", "rel_1", sealed, _source()))

    data = export_module(registry, "demo_module")
    zf = zipfile.ZipFile(BytesIO(data))
    names = set(zf.namelist())

    assert "src/app.py" in names
    assert "app.yaml" in names
    assert "README.md" in names
    assert MANIFEST_NAME in names
    # Never the platform's own control files, the dependency provenance, or stray data.
    for forbidden in ("package.index.json", "dependency.manifest.json", "records.db"):
        assert forbidden not in names
    assert not any(name.startswith("dependencies/") for name in names)

    manifest = json.loads(zf.read(MANIFEST_NAME))
    assert manifest["app_id"] == "demo_module"
    assert manifest["format_version"] == 1
    assert "alpha_core_version" in manifest
    assert set(manifest["files"]) == {"src/app.py", "app.yaml", "README.md"}


def test_round_trip_import_installs_the_module(tmp_path: Path) -> None:
    sealed = _make_sealed_dir(tmp_path)
    exporter = FakeRegistry()
    exporter.add(FakeVersion("demo_module", "ver_1", "rel_1", sealed, _source()))
    data = export_module(exporter, "demo_module")

    # A different Alpha (or the same one after removing it) that doesn't have it installed yet.
    registry = FakeRegistry()
    imported = import_module(registry, data)

    assert imported.app_id == "demo_module"
    assert imported.name == "Demo Module"
    assert registry.installed == [{"has_source": True, "has_index": False, "has_records": False}]


def test_import_gives_a_new_id_on_collision(tmp_path: Path) -> None:
    sealed = _make_sealed_dir(tmp_path)
    registry = FakeRegistry()
    registry.add(FakeVersion("demo_module", "ver_1", "rel_1", sealed, _source()))
    data = export_module(registry, "demo_module")

    # The module is already installed under this id (as if built locally); importing the same
    # export must not silently overwrite it.
    imported = import_module(registry, data)
    assert imported.app_id == "demo_module-2"


def test_tampered_file_is_rejected(tmp_path: Path) -> None:
    sealed = _make_sealed_dir(tmp_path)
    registry = FakeRegistry()
    registry.add(FakeVersion("demo_module", "ver_1", "rel_1", sealed, _source()))
    data = export_module(registry, "demo_module")

    # Flip the module's code after export, without updating the manifest's recorded hash.
    buf = BytesIO(data)
    zf = zipfile.ZipFile(buf)
    entries = {name: zf.read(name) for name in zf.namelist()}
    entries["src/app.py"] = b"def run():\n    return 'tampered'\n"
    tampered = BytesIO()
    with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as out:
        for name, content in entries.items():
            out.writestr(name, content)

    with pytest.raises(OperationFailed) as excinfo:
        import_module(registry, tampered.getvalue())
    assert excinfo.value.code == "conflict"
    assert not registry.installed


def test_import_rejects_missing_manifest() -> None:
    registry = FakeRegistry()
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("app.yaml", "app_id: x\n")
    with pytest.raises(OperationFailed):
        import_module(registry, buf.getvalue())


def test_import_rejects_undeclared_extra_file() -> None:
    registry = FakeRegistry()
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("app.yaml", "app_id: x\nname: X\n")
        zf.writestr(
            MANIFEST_NAME,
            json.dumps({"format_version": 1, "app_id": "x", "files": {"app.yaml": "deadbeef"}}),
        )
        zf.writestr("secrets.env", "TOKEN=abc")
    with pytest.raises(OperationFailed):
        import_module(registry, buf.getvalue())


def test_import_rejects_forbidden_file_name() -> None:
    registry = FakeRegistry()
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("app.yaml", "app_id: x\nname: X\n")
        zf.writestr(".env", "TOKEN=abc")
        zf.writestr(
            MANIFEST_NAME,
            json.dumps(
                {
                    "format_version": 1,
                    "app_id": "x",
                    "files": {"app.yaml": "deadbeef", ".env": "deadbeef"},
                }
            ),
        )
    with pytest.raises(OperationFailed):
        import_module(registry, buf.getvalue())
