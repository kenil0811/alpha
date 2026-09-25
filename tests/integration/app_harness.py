"""Helpers for F05 integration tests: a real published App runtime profile, rendered fixture
Apps and a real Core with both configured. Nothing here is mocked; workers run in the profile's
own interpreter and talk to Core over their pipes."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from tests.integration.conftest import REPO_ROOT, CoreProcess, start_core

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "apps"
TIMEZONE = "Asia/Kolkata"
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}


@dataclass(frozen=True)
class PublishedProfile:
    root: Path
    profile_id: str
    manifest_sha256: str
    path: Path


def build_profile(root: Path) -> PublishedProfile:
    """Run the trusted build path exactly as `just bundle-core` does."""
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "build_app_profile.py"), "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"profile build failed: {result.stdout}\n{result.stderr}")
    data = json.loads(result.stdout.strip().splitlines()[-1])
    return PublishedProfile(
        root=root,
        profile_id=data["profile_id"],
        manifest_sha256=data["manifest_sha256"],
        path=Path(data["path"]),
    )


def render_fixtures(target: Path, profile_id: str) -> Path:
    """Copy the fixture Apps and substitute the exact runtime profile ID."""
    for name in ("items_app", "tally_app"):
        source = FIXTURES / name
        dest = target / name
        shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__"))
        template = dest / "app.yaml.template"
        text = template.read_text(encoding="utf-8").replace("{{RUNTIME_PROFILE}}", profile_id)
        (dest / "app.yaml").write_text(text, encoding="utf-8")
        template.unlink()
    return target


def start_app_core(data_dir: Path, profile: PublishedProfile, fixtures: Path) -> CoreProcess:
    return start_core(
        data_dir,
        extra_env={
            "ALPHA_PROFILES_DIR": str(profile.root),
            "ALPHA_DEV_FIXTURE_APPS_DIR": str(fixtures),
            "ALPHA_TIMEZONE": TIMEZONE,
            "ALPHA_APP_MODEL_ROUTE": "fake",
        },
    )


def install(core: CoreProcess, name: str) -> dict[str, Any]:
    with core.client() as client:
        response = client.post(f"/api/dev/fixture-apps/{name}/install", timeout=60)
    if response.status_code != 200:
        raise AssertionError(f"install {name} failed: {response.status_code} {response.text}")
    data: dict[str, Any] = response.json()
    return data


def start_action(
    core: CoreProcess, app_id: str, action_id: str, payload: dict[str, Any], origin: str = "user"
) -> httpx.Response:
    with core.client() as client:
        return client.post(
            f"/api/apps/{app_id}/actions/{action_id}/runs",
            json={"input": payload, "origin": origin},
            timeout=30,
        )


def wait_run(core: CoreProcess, run_id: str, timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = core.run(run_id)
        if last["state"] in TERMINAL:
            return last
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} stayed {last.get('state')}")


def act(
    core: CoreProcess,
    app_id: str,
    action_id: str,
    payload: dict[str, Any] | None = None,
    *,
    origin: str = "user",
    expect: str = "succeeded",
) -> dict[str, Any]:
    """Invoke an action, wait for the run and assert its terminal state."""
    response = start_action(core, app_id, action_id, payload or {}, origin)
    assert response.status_code == 202, response.text
    run = wait_run(core, response.json()["run_id"])
    if run["state"] != expect:
        events = core.events(run["run_id"])
        raise AssertionError(
            f"{app_id}.{action_id} ended {run['state']} ({run.get('terminal_reason')}); "
            f"events: {json.dumps(events)[-3000:]}"
        )
    return run


def output(
    core: CoreProcess,
    app_id: str,
    action_id: str,
    payload: dict[str, Any] | None = None,
    *,
    origin: str = "user",
) -> dict[str, Any]:
    run = act(core, app_id, action_id, payload, origin=origin)
    result: dict[str, Any] = run["output"]
    return result


def shell_query(core: CoreProcess, app_id: str, body: dict[str, Any]) -> httpx.Response:
    with core.client() as client:
        return client.post(f"/api/apps/{app_id}/records/query", json=body)


def record_evidence(name: str, data: Any) -> None:
    """When ALPHA_EVIDENCE_DIR is set (evidence runs), write observed values for the report."""
    target = os.environ.get("ALPHA_EVIDENCE_DIR")
    if not target:
        return
    path = Path(target)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"{name}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
