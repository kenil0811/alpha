"""F05.C04: two App worker processes reuse the same exact installed SDK/runtime profile while
records, broker tokens, module globals and writable scratch stay distinct; restart uses the
pinned installation without any runtime install.

This is a functional check of the shared-profile design, not F20 containment qualification:
separate processes and a read-only installation are shown here; OS-level enforcement against a
hostile worker is F20's job."""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest
from alpha.execution.profiles import tree_digest

from tests.integration.app_harness import (
    build_profile,
    output,
    render_fixtures,
    start_action,
    start_app_core,
    wait_run,
)
from tests.integration.conftest import REPO_ROOT, AppCore, CoreProcess

pytestmark = pytest.mark.integration

ITEMS = "items-fixture"
TALLY = "tally-fixture"
WORKER_ENV = {
    "ALPHA_RUN_ID",
    "ALPHA_SCRATCH_DIR",
    "ALPHA_WORKER_PROFILE",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONUNBUFFERED",
    "LC_ALL",
    "HOME",
    "TMPDIR",
    "__CF_USER_TEXT_ENCODING",
}


def real(path: str | Path) -> str:
    return os.path.realpath(str(path))


def probe_both(core: CoreProcess, hold: float) -> tuple[dict[str, Any], dict[str, Any]]:
    a = start_action(core, ITEMS, "probe_isolation", {"hold_seconds": hold})
    b = start_action(core, TALLY, "probe_isolation", {"hold_seconds": hold})
    assert a.status_code == 202 and b.status_code == 202
    run_a = wait_run(core, a.json()["run_id"])
    run_b = wait_run(core, b.json()["run_id"])
    assert run_a["state"] == run_b["state"] == "succeeded", (run_a, run_b)
    return run_a, run_b


def profile_row(core: CoreProcess) -> dict[str, Any]:
    with core.client() as client:
        profiles = client.get("/api/runtime-profiles").json()["profiles"]
    assert len(profiles) == 1
    row: dict[str, Any] = profiles[0]
    return row


def test_two_apps_share_one_installed_profile_with_separate_state(app_core: AppCore) -> None:
    core, profile = app_core.core, app_core.profile
    row = profile_row(core)
    assert row["profile_id"] == profile.profile_id and row["state"] == "ready"
    assert row["manifest_sha256"] == profile.manifest_sha256
    items, tally = app_core.installs["items"], app_core.installs["tally"]
    assert items["runtime_profile_id"] == tally["runtime_profile_id"] == profile.profile_id
    # Same profile and SDK pins, so the per-Version dependency manifests are byte-identical.
    assert items["dependency_manifest_sha256"] == tally["dependency_manifest_sha256"]
    assert items["package_sha256"] != tally["package_sha256"]

    run_a, run_b = probe_both(core, hold=2.0)
    # They ran at the same time.
    assert run_a["started_at"] < run_b["finished_at"] and run_b["started_at"] < run_a["finished_at"]
    a, b = run_a["output"], run_b["output"]
    venv = profile.path / "venv"
    # One installation: the same interpreter, prefix and SDK files for both Apps.
    assert real(a["prefix"]) == real(b["prefix"]) == real(venv)
    assert a["python"] == b["python"] == real(venv / "bin" / "python")
    site = real(venv / "lib" / "python3.13" / "site-packages" / "alpha_sdk")
    assert real(Path(a["sdk_file"]).parent) == real(Path(b["sdk_file"]).parent) == site
    for snapshot in (run_a["snapshot"], run_b["snapshot"]):
        assert snapshot["runtime_profile_id"] == profile.profile_id
        assert snapshot["dependency_manifest_sha256"] == items["dependency_manifest_sha256"]
    # Separate processes, scratch, module globals and workload tokens.
    assert a["pid"] != b["pid"]
    assert a["scratch"] != b["scratch"]
    assert a["scratch_listing"] == ["items-scratch.txt"]
    assert b["scratch_listing"] == ["tally-scratch.txt"]
    assert a["marker_before"] is None and b["marker_before"] is None
    assert a["marker_after"] != b["marker_after"]
    assert a["token_digest"] != b["token_digest"]
    # The shared installation is read-only to workers and no bytecode is written into it.
    assert a["profile_write"] == "PermissionError"
    assert a["bytecode_dir_write"] == "PermissionError"
    assert a["dont_write_bytecode"] is True and a["flags_isolated"] == 1
    assert a["home"] == a["tmpdir"] == a["scratch"]
    assert set(a["env_keys"]) <= WORKER_ENV, set(a["env_keys"]) - WORKER_ENV
    # No platform source tree or editable link is importable: only the sealed Version's src/,
    # the base interpreter's standard library and the profile's own site-packages.
    sources = [str(REPO_ROOT / d) for d in ("packages", "services", "workers", "tools", "tests")]
    assert not any(entry.startswith(tuple(sources)) for entry in a["sys_path"]), a["sys_path"]
    assert a["sys_path"][0].endswith("/src") and "/versions/ver_" in a["sys_path"][0]
    assert not any(
        "site-packages" in entry and real(venv) not in real(entry) for entry in a["sys_path"]
    )

    # Records stay per App even with the same collection name.
    output(core, ITEMS, "add_item", {"title": "from items", "category": "work"})
    output(core, TALLY, "add", {"name": "from tally"})
    assert [r["values"]["name"] for r in output(core, TALLY, "list_all")["items"]] == ["from tally"]
    assert [r["values"]["title"] for r in output(core, ITEMS, "list_items")["items"]] == [
        "from items"
    ]


def test_restart_reuses_the_pinned_installation_without_installing(
    app_core: AppCore, data_dir: Path
) -> None:
    core, profile = app_core.core, app_core.profile
    before_tree = tree_digest(profile.path)
    before_listing = sorted(p.name for p in profile.root.iterdir())
    before_mtime = profile.path.stat().st_mtime_ns
    before_row = profile_row(core)
    first, _ = probe_both(core, hold=0)
    core.stop()

    # The harness starts Core with no PATH at all, so Core has no way to run uv or pip; the
    # profile must already be complete.
    restarted = start_app_core(data_dir, profile, app_core.fixtures)
    try:
        row = profile_row(restarted)
        assert row["state"] == "ready"
        assert row["installed_tree_sha256"] == before_row["installed_tree_sha256"]
        assert row["manifest_sha256"] == before_row["manifest_sha256"]
        again, _ = probe_both(restarted, hold=0)
        assert again["output"]["prefix"] == first["output"]["prefix"]
        assert again["output"]["python"] == first["output"]["python"]
        assert again["snapshot"]["runtime_profile_id"] == first["snapshot"]["runtime_profile_id"]
    finally:
        restarted.stop()
    assert tree_digest(profile.path) == before_tree
    assert sorted(p.name for p in profile.root.iterdir()) == before_listing
    assert profile.path.stat().st_mtime_ns == before_mtime
    with sqlite3.connect(data_dir / "control.sqlite") as conn:
        leases = conn.execute("SELECT COUNT(*) FROM worker_leases").fetchone()[0]
    assert leases == 0


def test_a_changed_installation_is_quarantined_not_used(tmp_path: Path, data_dir: Path) -> None:
    root = tmp_path / "profiles"
    profile = build_profile(root)
    victim = (
        profile.path / "venv" / "lib" / "python3.13" / "site-packages" / "alpha_sdk" / "records.py"
    )
    for path in (profile.path, victim.parent, victim):
        path.chmod(path.stat().st_mode | stat.S_IWUSR)
    victim.write_text(victim.read_text() + "\n# tampered\n")
    fixtures = render_fixtures(tmp_path / "fixture-apps", profile.profile_id)
    core = start_app_core(data_dir, profile, fixtures)
    try:
        row = profile_row(core)
        assert row["state"] == "quarantined"
        assert "installed files differ" in row["reason"]
        with core.client() as client:
            response = client.post("/api/dev/fixture-apps/items_app/install", timeout=60)
        assert response.status_code == 503
        assert "quarantined" in response.json()["detail"]["message"]
    finally:
        core.stop()
        for path in profile.path.rglob("*"):
            if not path.is_symlink():
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
        profile.path.chmod(profile.path.stat().st_mode | stat.S_IWUSR)
        shutil.rmtree(profile.path, ignore_errors=True)


def test_an_action_already_running_is_not_started_again(app_core: AppCore) -> None:
    """One run of an App's action at a time: a second press while the first is going is refused
    with a plain reason (two checks racing over the same records failed in the job hunt)."""
    core = app_core.core
    first = start_action(core, TALLY, "probe_isolation", {"hold_seconds": 3})
    assert first.status_code == 202, first.text
    second = start_action(core, TALLY, "probe_isolation", {"hold_seconds": 0})
    assert second.status_code == 409, second.text
    detail = second.json()["detail"]
    assert "already running" in detail["message"], detail
    assert detail["details"]["run_id"] == first.json()["run_id"]
    other = start_action(core, ITEMS, "probe_isolation", {"hold_seconds": 0})
    assert other.status_code == 202, "a different App's action is not held up"
    assert wait_run(core, first.json()["run_id"])["state"] == "succeeded"
    again = start_action(core, TALLY, "probe_isolation", {"hold_seconds": 0})
    assert again.status_code == 202, "once it finished, the action runs again"
    wait_run(core, again.json()["run_id"])
    wait_run(core, other.json()["run_id"])
