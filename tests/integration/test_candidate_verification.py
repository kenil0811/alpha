"""F07: candidate verification, bounded repair and sealed dependency identities.

Real Core, real App runtime and UI build profiles, the real UI build tool and the pinned
headless browser; only the builder is a deterministic fake that copies fixture packages. Each
defect variant differs from `notes_ok` by exactly one change (tests/integration/build_harness).

F07.C01  missing handler, false persistence, a broken primary action and contradictory
         builder/validator outcomes are rejected; repair is bounded and every attempt kept.
F07.C02  the screen's primary interaction, saved outputs and rendered states are exercised in a
         browser; a failing screen is withheld from ready.
F07.C04  undeclared dependencies, changed locks or artifacts, incompatible profiles and a
         substituted runtime fail validation or activation; sealed outputs carry exact pins and
         no local state; workers never install anything.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.integration.build_harness import (
    NOTES_PLAN,
    checks,
    events,
    failed,
    no_local_paths,
    report,
    start_build_core,
    submit,
    validator_browser,
    wait_build,
)
from tests.integration.conftest import BuildProfiles, CoreProcess

pytestmark = pytest.mark.integration

UI_STATES = ["empty-1280", "empty-768", "primary-1280", "populated-1280", "populated-768"]


@pytest.fixture
def once_core(
    data_dir: Path, build_profiles: BuildProfiles, build_packages: Path
) -> Iterator[CoreProcess]:
    """A Core whose total build budget allows no repair: each defect is judged on attempt 1."""
    proc = start_build_core(
        data_dir, build_profiles.root, build_packages, {"ALPHA_BUILD_MAX_TOTAL_SECONDS": "1"}
    )
    try:
        yield proc
    finally:
        proc.stop()


def build(core: CoreProcess, goal: str) -> tuple[dict[str, Any], dict[str, Any]]:
    created = submit(core, goal)
    final = wait_build(core, created["build_id"])
    return final, report(core, final)


def profile_rows(core: CoreProcess) -> dict[str, dict[str, Any]]:
    with core.client() as client:
        rows = client.get("/api/runtime-profiles").json()["profiles"]
    return {r["profile_id"]: r for r in rows}


def unseal(root: Path) -> None:
    for path in [root, *root.rglob("*")]:
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


@pytest.fixture
def private_profiles(tmp_path: Path, build_profiles: BuildProfiles) -> Iterator[Path]:
    """A private copy of the session's profiles, so a test may tamper with it."""
    root = tmp_path / "profiles-copy"
    shutil.copytree(build_profiles.root, root, symlinks=True)
    yield root
    unseal(root)


# ----- F07.C01 -------------------------------------------------------------------------


def test_a_verified_candidate_is_ready_with_a_complete_report(build_core: CoreProcess) -> None:
    final, rep = build(build_core, "fake:package notes_ok")
    assert final["state"] == "ready", failed(rep)
    assert rep["passed"] is True and rep["builder_status"] == "candidate"
    stages = {c["stage"] for c in rep["checks"]}
    assert stages == {"package", "deps", "seal", "handlers", "behavior", "ui"}
    assert all(c["status"] == "passed" for c in rep["checks"] if c["required"])
    assert rep["lineage"] == [final["attempts"][0]["attempt_id"]]
    assert rep["package_sha256"] == final["candidate"]["package_sha256"]
    for key in ("runtime_profile", "sdk", "ui_build_profile", "ui_browser", "ui_playwright"):
        assert rep["environment"].get(key), key
    # Candidate-authored tests ran, and are supplementary only.
    (tests,) = rep["supplementary"]
    assert tests["status"] == "passed" and tests["required"] is False
    # A ready candidate is a preview: nothing is installed until activation.
    assert final["candidate"]["activated"] is False and final["candidate"]["has_ui"] is True
    with build_core.client() as client:
        assert client.get("/api/apps").json()["apps"] == []


def test_a_missing_handler_is_rejected_by_real_binding(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package missing_handler")
    assert final["state"] == "failed" and final["candidate"] is None
    bind = checks(rep)["handlers.bind"]
    assert bind["status"] == "failed"
    assert "count_notes" in bind["summary"] and "count_all" in bind["summary"]
    # Nothing after binding counts as passed.
    assert {c["status"] for c in rep["checks"] if c["stage"] == "behavior"} == {"skipped"}


def test_false_persistence_is_caught_by_reading_storage(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package fake_persistence")
    assert final["state"] == "failed"
    found = checks(rep)
    # The action itself "succeeds" and returns an id: only storage tells the truth.
    assert found["behavior.add_and_count.add"]["status"] == "passed"
    stored = found["behavior.add_and_count.stored"]
    assert stored["status"] == "failed" and stored["detail"]["count"] == 0
    assert found["behavior.add_and_count.count"]["status"] == "skipped"


def test_a_broken_primary_action_is_rejected(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package broken_action")
    assert final["state"] == "failed"
    add = checks(rep)["behavior.add_and_count.add"]
    assert add["status"] == "failed" and "no collection 'note'" in add["summary"]
    assert add["detail"]["state"] == "failed"


def test_a_failed_builder_stays_failed_even_when_every_check_passes(
    build_core: CoreProcess,
) -> None:
    final, rep = build(build_core, "fake:package notes_ok --claim-failed")
    assert final["state"] == "failed" and final["candidate"] is None
    assert final["terminal_reason"] == "harness_failed"
    assert len(final["attempts"]) == 1, "a builder failure is not repaired"
    assert rep["builder_status"] == "failed" and rep["passed"] is False
    assert all(c["status"] == "passed" for c in rep["checks"] if c["required"])
    failed_event = next(
        e for e in events(build_core, final["build_id"]) if e["kind"] == "build.failed"
    )
    assert failed_event["payload"]["checks_passed_anyway"] == len(rep["checks"])


def test_repair_fixes_a_failed_candidate_and_keeps_every_attempt(
    build_core: CoreProcess,
) -> None:
    final, rep = build(build_core, "fake:package fake_persistence notes_ok")
    assert final["state"] == "ready", failed(rep)
    first, second = final["attempts"]
    assert (first["status"], second["status"]) == ("failed", "candidate")
    assert rep["lineage"] == [first["attempt_id"], second["attempt_id"]]
    first_report = report(build_core, final, attempt=0)
    assert "behavior.add_and_count.stored" in failed(first_report)
    repairing = [e for e in events(build_core, final["build_id"]) if e["kind"] == "build.repairing"]
    assert len(repairing) == 1
    assert repairing[0]["payload"]["failed_checks"] == ["behavior.add_and_count.stored"]
    # The builder was told exactly what failed; the first attempt's workspace is retained.
    workspace = build_core.data_dir / "builds" / second["workspace_ref"]
    repair = (workspace / "REPAIR.md").read_text()
    assert "behavior.add_and_count.stored" in repair and "0 saved, expected 1" in repair
    assert (build_core.data_dir / "builds" / first["workspace_ref"] / "package").is_dir()


def test_repair_stops_at_its_limit_and_every_attempt_is_retained(
    build_core: CoreProcess,
) -> None:
    final, rep = build(build_core, "fake:package broken_action")
    assert final["state"] == "failed" and final["terminal_reason"] == "repair_limit_reached"
    assert [a["status"] for a in final["attempts"]] == ["failed", "failed", "failed"]
    assert all(a["report_ref"] for a in final["attempts"])
    assert len(rep["lineage"]) == 3
    kinds = [e["kind"] for e in events(build_core, final["build_id"])]
    assert kinds.count("build.repairing") == 2 and kinds.count("build.attempt_started") == 3


def test_the_total_budget_stops_repair(once_core: CoreProcess) -> None:
    final, _ = build(once_core, "fake:package broken_action")
    assert final["state"] == "failed"
    assert final["terminal_reason"] == "total_deadline_exceeded"
    # The reason says why repair stopped; the category still says what was wrong.
    assert final["failure_category"] == "validation_failed"
    assert len(final["attempts"]) == 1


# ----- F07.C02 (rendered states in a real browser) ---------------------------------------


needs_browser = pytest.mark.skipif(
    validator_browser() is None, reason="the pinned headless browser is not installed"
)


@needs_browser
def test_the_screen_is_driven_through_every_state_in_a_browser(build_core: CoreProcess) -> None:
    final, rep = build(build_core, "fake:package notes_ok")
    assert final["state"] == "ready", failed(rep)
    ui = {c["id"]: c for c in rep["checks"] if c["stage"] == "ui"}
    for check_id in (
        "ui.empty.render",
        "ui.empty.no_error",
        "ui.empty.layout_768",
        "ui.primary.steps",
        "ui.primary.action",
        "ui.primary.saved",
        "ui.primary.shows.1",
        "ui.populated.shows.1",
        "ui.populated.layout_768",
        "ui.error.read",
        "ui.error.save",
        "ui.error.save_nothing_stored",
    ):
        assert ui[check_id]["status"] == "passed", (check_id, ui.get(check_id))
    assert ui["ui.error.save_input_kept"]["status"] == "passed"
    # The primary interaction saved a real record through the declared action.
    assert ui["ui.primary.saved"]["detail"]["values"][0]["title"] == "Buy milk"
    workspace = build_core.data_dir / "builds" / final["attempts"][0]["workspace_ref"]
    for name in [*UI_STATES, "error-read", "error-save"]:
        shot = workspace / "evidence" / "ui" / f"{name}.png"
        assert shot.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", name


@needs_browser
def test_fields_are_found_by_their_own_label_not_by_lookalike_titles(
    once_core: CoreProcess,
) -> None:
    """Found live (F07.C03, first repair run): a section titled "Write a note" was taken for the
    field labelled "Note". Only form controls of the right kind are considered now."""
    final, rep = build(once_core, "fake:package lookalike_titles")
    assert final["state"] == "ready", failed(rep)


def test_a_screen_that_breaks_the_kit_types_fails_the_build_with_the_line(
    once_core: CoreProcess,
) -> None:
    """Found live (F07.C03, second repair run): a table without its required caption crashed
    the screen at run time and the builder had to guess why. The build now type-checks."""
    final, rep = build(once_core, "fake:package missing_prop")
    ui_build = checks(rep)["seal.ui_build"]
    assert final["state"] == "failed" and ui_build["status"] == "failed"
    assert "main.tsx(" in ui_build["summary"] and "caption" in ui_build["summary"]


@needs_browser
def test_a_screen_that_reads_nothing_is_not_asked_to_show_a_failed_read(
    once_core: CoreProcess,
) -> None:
    plan = json.loads(json.dumps(NOTES_PLAN))
    plan["ui"]["shows"], plan["ui"]["seed_shows"], plan["ui"]["seed"] = [], [], []
    created = submit(once_core, "fake:package entry_only", plan)
    final = wait_build(once_core, created["build_id"])
    rep = report(once_core, final)
    assert final["state"] == "ready", failed(rep)
    read = checks(rep)["ui.error.read"]
    assert read["status"] == "skipped" and read["required"] is False


@needs_browser
def test_blocking_overflow_withholds_readiness(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package overflow")
    assert final["state"] == "failed" and final["candidate"] is None
    layout = checks(rep)["ui.empty.layout_768"]
    assert layout["status"] == "failed" and layout["detail"]["scroll_width"] > 1400
    assert layout["evidence"] == [
        "evidence/ui/empty-768.png",
        "evidence/ui/empty-768-overflow.png",
    ]


@needs_browser
def test_a_screen_that_only_pretends_to_save_is_rejected(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package ui_fake_save")
    assert final["state"] == "failed"
    found = checks(rep)
    # It even shows the text; but no action ran and nothing was stored.
    assert found["ui.primary.shows.1"]["status"] == "passed"
    assert found["ui.primary.action"]["status"] == "failed"
    assert found["ui.primary.saved"]["status"] == "failed"


@needs_browser
def test_a_screen_that_hides_failures_is_rejected(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package ui_hides_errors")
    assert final["state"] == "failed"
    found = checks(rep)
    assert found["ui.error.read"]["status"] == "failed"
    assert found["ui.error.save"]["status"] == "failed"
    assert found["ui.primary.saved"]["status"] == "passed", "the happy path itself works"


# ----- F07.C04 -------------------------------------------------------------------------


def test_an_undeclared_import_becomes_a_qualification_request(once_core: CoreProcess) -> None:
    before = profile_rows(once_core)
    final, rep = build(once_core, "fake:package undeclared_import")
    assert final["state"] == "failed" and final["failure_category"] == "dependency_unsupported"
    (request,) = rep["qualification_requests"]
    assert request["package"] == "requests" and request["found_in"] == "import"
    assert request["where"].startswith("src/notes_app/handlers.py:")
    with once_core.client() as client:
        recorded = client.get(
            "/api/dependency-requests", params={"build_id": final["build_id"]}
        ).json()["requests"]
    assert [(r["package"], r["state"]) for r in recorded] == [("requests", "requested")]
    # Nothing was installed or changed to make the candidate work.
    after = profile_rows(once_core)
    for profile_id, row in before.items():
        assert after[profile_id]["installed_tree_sha256"] == row["installed_tree_sha256"]
        assert after[profile_id]["state"] == "ready"


def test_a_declared_extra_module_becomes_a_qualification_request(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package declared_module")
    assert final["failure_category"] == "dependency_unsupported"
    (request,) = rep["qualification_requests"]
    assert (request["package"], request["version"], request["found_in"]) == (
        "requests",
        "2.32.3",
        "app.yaml modules",
    )
    assert checks(rep)["deps.profiles"]["status"] == "failed"


def test_platform_imports_and_dependency_files_are_refused(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package core_import")
    imports = checks(rep)["handlers.imports"]
    assert imports["status"] == "failed" and "imports platform internals" in imports["summary"]
    final, rep = build(once_core, "fake:package requirements_file")
    layout = checks(rep)["package.layout"]
    assert layout["status"] == "failed" and "requirements.txt" in layout["summary"]
    assert final["failure_category"] == "invalid_package"


def test_an_incompatible_profile_is_refused(once_core: CoreProcess) -> None:
    final, rep = build(once_core, "fake:package wrong_profile")
    deps = checks(rep)["deps.profiles"]
    assert (
        deps["status"] == "failed" and "not an App/Task Python runtime profile" in deps["summary"]
    )


def test_the_sealed_candidate_pins_exact_identities_and_holds_no_local_state(
    build_core: CoreProcess, build_profiles: BuildProfiles
) -> None:
    final, rep = build(build_core, "fake:package notes_ok")
    assert final["state"] == "ready", failed(rep)
    version = build_core.data_dir / "builds" / final["candidate"]["version_ref"]
    rows = profile_rows(build_core)
    manifest = json.loads((version / "dependency.manifest.json").read_text())
    runtime = rows[manifest["runtime_profile_id"]]
    assert manifest["runtime_profile_manifest_sha256"] == runtime["manifest_sha256"]
    sdk_pin = next(p for p in runtime["manifest"]["packages"] if p["name"] == "alpha-sdk")
    assert manifest["sdk"] == {
        "name": "alpha-sdk",
        "version": sdk_pin["version"],
        "artifact_sha256": sdk_pin["artifact_sha256"],
    }
    ui_row = rows[manifest["ui_build"]["profile_id"]]
    assert manifest["ui_build"]["manifest_sha256"] == ui_row["manifest_sha256"]
    ui_pins = {p["name"]: p for p in ui_row["manifest"]["packages"]}
    assert manifest["ui_build"]["kit"] == ui_pins["@alpha/ui-kit"]
    assert manifest["ui_build"]["bridge"] == ui_pins["@alpha/ui-bridge"]
    assert manifest["modules"] == []
    # The profile locks travel as provenance, byte for byte.
    runtime_dir = build_profiles.root / manifest["runtime_profile_id"]
    assert (version / "dependencies/python/requirements.lock").read_bytes() == (
        runtime_dir / "requirements.lock"
    ).read_bytes()
    # Every file is indexed; nothing portable names this Mac, the data or the profiles.
    index = json.loads((version / "package.index.json").read_text())
    on_disk = {p.relative_to(version).as_posix() for p in version.rglob("*") if p.is_file()} - {
        "package.index.json"
    }
    assert {f["path"] for f in index["files"]} == on_disk
    assert "dist/ui/index.html" in on_disk
    for rel in on_disk | {"package.index.json"}:
        if rel.endswith((".json", ".yaml", ".html", ".csp", ".lock")):
            text = (version / rel).read_text(encoding="utf-8")
            assert no_local_paths(text, build_core.data_dir, build_profiles.root) == [], rel
    assert not [p for p in on_disk if Path(p).name.startswith(".env")]
    # Sealed read-only.
    assert not (version / "app.yaml").stat().st_mode & stat.S_IWUSR


def test_activation_installs_the_exact_validated_bytes_and_runs_them_on_the_same_profile(
    build_core: CoreProcess,
) -> None:
    final, rep = build(build_core, "fake:package notes_ok")
    candidate = final["candidate"]
    with build_core.client() as client:
        response = client.post(f"/api/builds/{final['build_id']}/activate")
        assert response.status_code == 200, response.text
        activated = response.json()
        assert activated["version_id"] == candidate["version_id"]
        assert activated["package_sha256"] == rep["package_sha256"]
        run = client.post(
            f"/api/apps/{activated['app_id']}/actions/add_note/runs",
            json={"input": {"title": "After activation"}, "origin": "user"},
        ).json()
    done = build_core.run(run["run_id"])
    for _ in range(100):
        if done["state"] in ("succeeded", "failed"):
            break
        time.sleep(0.1)
        done = build_core.run(run["run_id"])
    assert done["state"] == "succeeded", done
    snapshot = done["snapshot"]
    assert snapshot["version_id"] == candidate["version_id"]
    assert snapshot["package_sha256"] == rep["package_sha256"]
    assert snapshot["runtime_profile_id"] == rep["runtime_profile_id"]
    assert snapshot["dependency_manifest_sha256"] == rep["dependency_manifest_sha256"]
    # The preview's records never reached the App: only the run above is stored.
    with build_core.client() as client:
        page = client.post(
            f"/api/apps/{activated['app_id']}/records/query", json={"collection": "notes"}
        ).json()
    assert [r["values"]["title"] for r in page["records"]] == ["After activation"]


def test_a_changed_sealed_artifact_fails_activation(build_core: CoreProcess) -> None:
    final, _ = build(build_core, "fake:package notes_ok")
    version = build_core.data_dir / "builds" / final["candidate"]["version_ref"]
    handler = version / "src" / "notes_app" / "handlers.py"
    unseal(version)
    handler.write_text(handler.read_text() + "\n# changed after validation\n")
    with build_core.client() as client:
        activate = client.post(f"/api/builds/{final['build_id']}/activate")
        invoke = client.post(
            f"/api/builds/{final['build_id']}/invoke",
            json={"action_id": "count_notes", "input": {}},
        )
        apps = client.get("/api/apps").json()["apps"]
    assert activate.status_code == 409 and "changed" in activate.json()["detail"]["message"]
    assert invoke.status_code == 409
    assert apps == []


def test_a_changed_lock_fails_validation(
    data_dir: Path, private_profiles: Path, build_packages: Path
) -> None:
    core = start_build_core(
        data_dir, private_profiles, build_packages, {"ALPHA_BUILD_MAX_TOTAL_SECONDS": "1"}
    )
    try:
        runtime = next(p for p in private_profiles.iterdir() if p.name.startswith("pyprof-"))
        lock = runtime / "requirements.lock"
        unseal(runtime)
        lock.write_text(lock.read_text() + "# edited after the profile was sealed\n")
        final, rep = build(core, "fake:package notes_ok")
        deps = checks(rep)["deps.profiles"]
        assert final["state"] == "failed"
        assert deps["status"] == "failed" and "changed on disk" in deps["summary"]
        assert profile_rows(core)[runtime.name]["state"] == "quarantined"
    finally:
        core.stop()


def test_a_substituted_runtime_fails_activation_and_stops_runs(
    data_dir: Path, private_profiles: Path, build_packages: Path
) -> None:
    core = start_build_core(data_dir, private_profiles, build_packages)
    try:
        final, _ = build(core, "fake:package notes_ok")
        assert final["state"] == "ready"
        runtime = next(p for p in private_profiles.iterdir() if p.name.startswith("pyprof-"))
        site = next((runtime / "venv" / "lib").glob("python*/site-packages"))
        unseal(runtime)
        (site / "substitute.py").write_text("print('not the qualified runtime')\n")
        with core.client() as client:
            response = client.post(f"/api/builds/{final['build_id']}/activate")
        assert response.status_code == 503, response.text
        assert "quarantined" in response.json()["detail"]["message"]
        assert profile_rows(core)[runtime.name]["state"] == "quarantined"
    finally:
        core.stop()


def test_workers_never_install_packages(
    once_core: CoreProcess, build_profiles: BuildProfiles
) -> None:
    """No installer is importable, generated code may not reach the bundled one, and the shared
    installation is read-only."""
    python = build_profiles.runtime.path / "venv" / "bin" / "python"
    probe = subprocess.run(
        [str(python), "-I", "-c", "import pip"], capture_output=True, text=True, env={}, check=False
    )
    assert probe.returncode != 0 and "No module named 'pip'" in probe.stderr
    final, rep = build(once_core, "fake:package installer_import")
    imports = checks(rep)["handlers.imports"]
    assert imports["status"] == "failed" and "installs packages" in imports["summary"]
    site = next((build_profiles.runtime.path / "venv" / "lib").glob("python*/site-packages"))
    assert not site.stat().st_mode & stat.S_IWUSR, "the shared installation must be read-only"


def test_a_seeded_first_attempt_is_verified_like_any_claim_then_repaired(
    data_dir: Path, build_profiles: BuildProfiles, build_packages: Path
) -> None:
    """Qualification path for real repair: start from a known defective package."""
    core = start_build_core(
        data_dir,
        build_profiles.root,
        build_packages,
        {"ALPHA_DEV_SEED_PACKAGES_DIR": str(build_packages)},
    )
    try:
        created = submit(core, "fake:package notes_ok", seed_package="fake_persistence")
        final = wait_build(core, created["build_id"])
        assert final["state"] == "ready" and final["seed_package"] == "fake_persistence"
        assert [a["status"] for a in final["attempts"]] == ["failed", "candidate"]
        started = [
            e for e in events(core, created["build_id"]) if e["kind"] == "build.attempt_started"
        ]
        assert [e["payload"]["harness"] for e in started] == ["seeded", "fake"]
        assert "behavior.add_and_count.stored" in failed(report(core, final, attempt=0))
    finally:
        core.stop()


def test_seeded_builds_are_refused_unless_the_host_enables_them(build_core: CoreProcess) -> None:
    with build_core.client() as client:
        response = client.post(
            "/api/builds",
            json={
                "goal": "x",
                "validation_plan": {
                    "scenarios": [
                        {
                            "id": "s",
                            "description": "d",
                            "steps": [{"kind": "invoke", "id": "a", "action": "add_note"}],
                        }
                    ]
                },
                "seed_package": "fake_persistence",
            },
        )
    assert response.status_code == 409 and "not enabled" in response.json()["detail"]


@needs_browser
def test_a_main_interaction_that_starts_off_screen_is_rejected(once_core: CoreProcess) -> None:
    """M1-R05 (review: large stacked forms above the working area): the first control of the
    main interaction must be visible without scrolling in Alpha's default workspace."""
    final, rep = build(once_core, "fake:package ui_entry_below")
    assert final["state"] == "failed"
    found = checks(rep)
    assert found["ui.primary.steps"]["status"] == "passed", "the interaction itself still works"
    visible = found["ui.primary.visible"]
    assert visible["status"] == "failed" and visible["required"] is True
    assert "not visible without scrolling" in visible["summary"]


@needs_browser
def test_a_screen_that_loses_typed_input_on_a_failed_save_is_rejected(
    once_core: CoreProcess,
) -> None:
    """M1-R05/R06: keeping what was typed after a failed save is now required."""
    final, rep = build(once_core, "fake:package ui_clears_on_failure")
    assert final["state"] == "failed"
    kept = checks(rep)["ui.error.save_input_kept"]
    assert kept["status"] == "failed" and kept["required"] is True
    assert checks(rep)["ui.primary.repeat"]["status"] == "passed"
