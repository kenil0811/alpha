"""`POST /api/modules/import` accepts either `{data_base64}` or a local `{path}` (desktop): a
path must end in `.alphamodule`, exist, and be under 10 MB, otherwise it fails the same way the
base64 branch does — before the bytes ever reach `import_module`.

No TestClient here (httpx isn't installed in this environment): the route function is a plain
sync callable registered on the FastAPI app, so it is pulled off `app.routes` and called directly
with the same Pydantic request model FastAPI would build for it — same code path, no HTTP layer.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alpha.api.apps_routes import ModuleImportRequest, register
from alpha.solutions.module_export import export_module
from fastapi import FastAPI, HTTPException
from test_module_export import FakeRegistry, FakeVersion, _make_sealed_dir, _source


def _import_endpoint(registry: Any):
    app = FastAPI()
    platform = type("Platform", (), {"registry": registry})()
    register(app, platform)
    route = next(r for r in app.routes if getattr(r, "path", None) == "/api/modules/import")
    return route.endpoint


def _exported_bytes(tmp_path: Path) -> bytes:
    sealed = _make_sealed_dir(tmp_path)
    registry = FakeRegistry()
    registry.add(FakeVersion("demo_module", "ver_1", "rel_1", sealed, _source()))
    return export_module(registry, "demo_module")


def test_import_by_path_round_trips_into_the_registry(tmp_path: Path) -> None:
    data = _exported_bytes(tmp_path)
    module_file = tmp_path / "demo.alphamodule"
    module_file.write_bytes(data)

    registry = FakeRegistry()
    endpoint = _import_endpoint(registry)

    result = endpoint(ModuleImportRequest(path=str(module_file)))

    assert result["app_id"] == "demo_module"
    assert result["name"] == "Demo Module"
    assert registry.installed == [{"has_source": True, "has_index": False, "has_records": False}]


def test_import_by_path_rejects_wrong_suffix(tmp_path: Path) -> None:
    # Valid module bytes under the wrong extension: only the suffix check can catch this —
    # if it were missing, this would import cleanly.
    data = _exported_bytes(tmp_path)
    other = tmp_path / "demo.zip"
    other.write_bytes(data)

    endpoint = _import_endpoint(FakeRegistry())
    with pytest.raises(HTTPException) as excinfo:
        endpoint(ModuleImportRequest(path=str(other)))
    assert excinfo.value.status_code == 422
    assert "Alpha module file" in excinfo.value.detail["message"]


def test_import_by_path_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.alphamodule"
    assert not missing.exists()

    endpoint = _import_endpoint(FakeRegistry())
    with pytest.raises(HTTPException) as excinfo:
        endpoint(ModuleImportRequest(path=str(missing)))
    assert excinfo.value.status_code == 422
    assert "Alpha module file" in excinfo.value.detail["message"]


def test_import_by_path_rejects_oversize_file(tmp_path: Path) -> None:
    huge = tmp_path / "huge.alphamodule"
    with huge.open("wb") as f:
        f.seek(10 * 1024 * 1024 + 1)
        f.write(b"\0")

    endpoint = _import_endpoint(FakeRegistry())
    with pytest.raises(HTTPException) as excinfo:
        endpoint(ModuleImportRequest(path=str(huge)))
    assert excinfo.value.status_code == 422
    assert "larger than 10 MB" in excinfo.value.detail["message"]
