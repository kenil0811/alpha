"""F08: from a brief to a usable, reopenable result.

Real Core, real App runtime and UI build profiles, the real UI build tool and the pinned headless
browser. The assistant, the acceptance planner and the builder run on their deterministic fake
routes (control fixtures only: they prove the platform's plumbing, never generation quality;
G1 proves generation with the live routes).

F08.C03  a creation plans, builds, checks and activates with stable App, Version and data
         identities; the result and its data reopen after a restart; an unfinished creation is
         reported, not revived; preview sample data never reaches the App's own data; a
         builder that changes the assigned identity is refused; activation is compare-and-swap.
F08.C04  two created results share one runtime profile with independent data and scratch, and
         cancelling or failing a run in one leaves the other intact.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from tests.integration.app_harness import output, record_evidence, start_action, wait_run
from tests.integration.build_harness import (
    NOTES_PLAN,
    checks,
    report,
    start_build_core,
    submit,
    wait_build,
)
from tests.integration.conftest import BuildProfiles, CoreProcess

pytestmark = pytest.mark.integration

DONE = {"active", "failed", "cancelled"}


def briefed(core: CoreProcess, text: str) -> str:
    with core.client() as client:
        conversation = client.post("/api/conversations", json={"text": text}).json()
        cid = conversation["conversation_id"]
        deadline = time.monotonic() + 20
        while conversation["state"] == "thinking" and time.monotonic() < deadline:
            time.sleep(0.1)
            conversation = client.get(f"/api/conversations/{cid}").json()
    assert conversation["state"] == "briefed", conversation
    assert conversation["delivery"] == "app"
    return str(cid)


def start_creation(core: CoreProcess, cid: str, hint: str) -> dict[str, Any]:
    with core.client() as client:
        response = client.post(f"/api/conversations/{cid}/creations", json={"builder_hint": hint})
    assert response.status_code == 202, response.text
    data: dict[str, Any] = response.json()
    return data


def wait_creation(core: CoreProcess, creation_id: str, timeout: float = 300) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        with core.client() as client:
            last = client.get(f"/api/creations/{creation_id}").json()
        if last["state"] in DONE:
            return last
        time.sleep(0.25)
    raise AssertionError(f"creation {creation_id} stayed {last.get('state')}")


def create(core: CoreProcess, text: str, hint: str = "package notes_ok") -> dict[str, Any]:
    creation = start_creation(core, briefed(core, text), hint)
    return wait_creation(core, creation["creation_id"])


def apps(core: CoreProcess) -> dict[str, dict[str, Any]]:
    with core.client() as client:
        rows = client.get("/api/apps").json()["apps"]
    return {r["app_id"]: r for r in rows}


def detail(core: CoreProcess, app_id: str) -> dict[str, Any]:
    with core.client() as client:
        response = client.get(f"/api/apps/{app_id}")
    assert response.status_code == 200, response.text
    data: dict[str, Any] = response.json()
    return data


def notes(core: CoreProcess, app_id: str) -> list[dict[str, Any]]:
    with core.client() as client:
        response = client.post(
            f"/api/apps/{app_id}/records/query", json={"collection": "notes", "limit": 50}
        )
    assert response.status_code == 200, response.text
    rows: list[dict[str, Any]] = response.json()["records"]
    return rows


def build_of(core: CoreProcess, build_id: str) -> dict[str, Any]:
    with core.client() as client:
        data: dict[str, Any] = client.get(f"/api/builds/{build_id}").json()
    return data


# ----- F08.C03 -------------------------------------------------------------------------------


def test_a_brief_becomes_an_active_app_with_its_own_screen(build_core: CoreProcess) -> None:
    core = build_core
    cid = briefed(core, "Keep a notes list for me")
    started = start_creation(core, cid, "package notes_ok")
    again = start_creation(core, cid, "package notes_ok")
    assert again["creation_id"] == started["creation_id"], "one creation per brief revision"

    final = wait_creation(core, started["creation_id"])
    assert final["state"] == "active", final
    stages = [h["stage"] for h in final["history"]]
    assert stages[0] == "planning" and stages[-1] == "active", stages
    assert {"building", "activating"} <= set(stages), stages
    app_id = final["app_id"]
    assert app_id.startswith("notes-list-"), app_id
    result = final["result"]
    assert result["app_id"] == app_id and result["has_ui"] is True
    assert result["checks_passed"] > 0 and result["attempts"] == 1

    # The build targeted the assigned identity, and the verifier checked it.
    build = build_of(core, final["build_id"])
    assert build["state"] == "ready" and build["app_id"] == app_id
    identity = checks(report(core, build))["package.identity"]
    assert identity["status"] == "passed", identity

    # The registry records where the Version came from.
    row = apps(core)[app_id]
    assert row["origin"] == "created" and row["state"] == "active"
    assert row["creation_id"] == final["creation_id"] and row["has_ui"] is True
    assert row["current_release_id"] == final["release_id"]
    assert row["current_version_id"] == final["version_id"]
    info = detail(core, app_id)
    assert info["ui"]["entry"] == "ui/src/main.tsx"
    assert info["version_id"] == final["version_id"]
    screen = core.data_dir / "versions" / final["version_id"] / "dist" / "ui" / "index.html"
    assert screen.is_file(), "the host serves the App's screen from its sealed Version"
    index = json.loads(
        (core.data_dir / "versions" / final["version_id"] / "package.index.json").read_text()
    )
    assert index.get("app_id", app_id) == app_id

    # Preview images are the checks' own screenshots, served only to the shell...
    assert result["preview_images"], result
    image_url = result["preview_images"][0]["url"]
    with core.client() as client:
        image = client.get(image_url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    with core.client(token="wrong") as client:
        assert client.get(image_url).status_code == 401
    # ...and the sample data they show never reaches the App's own data.
    assert notes(core, app_id) == []
    assert info["record_counts"].get("notes", 0) == 0

    # The result is usable: its primary action saves the person's own record.
    saved = output(core, app_id, "add_note", {"title": "Renew passport"}, origin="ui")
    assert set(saved) >= {"id", "revision"}
    assert [n["values"]["title"] for n in notes(core, app_id)] == ["Renew passport"]
    record_evidence(
        "f08-creation",
        {"creation": final, "app": row, "build_app_id": build["app_id"], "identity": identity},
    )


def test_an_app_without_its_own_screen_is_used_through_its_actions(
    build_core: CoreProcess,
) -> None:
    core = build_core
    final = create(core, "Keep a notes list for me, no screen")
    assert final["state"] == "active", final
    app_id = final["app_id"]
    assert final["result"]["has_ui"] is False
    info = detail(core, app_id)
    assert info["ui"] is None
    actions = {a["id"]: a for a in info["actions"]}
    assert set(actions) == {"add_note", "count_notes"}
    assert actions["add_note"]["input_schema"]["required"] == ["title"]
    assert "manual" in actions["add_note"]["invocable_from"]
    assert not (core.data_dir / "versions" / final["version_id"] / "dist" / "ui").exists()
    assert apps(core)[app_id]["has_ui"] is False

    output(core, app_id, "add_note", {"title": "Call the bank"})
    assert output(core, app_id, "count_notes", {}) == {"count": 1}
    refused = start_action(core, app_id, "add_note", {"title": ""})
    run = wait_run(core, refused.json()["run_id"]) if refused.status_code == 202 else None
    assert refused.status_code == 422 or (run is not None and run["state"] == "failed")
    assert output(core, app_id, "count_notes", {}) == {"count": 1}


def test_created_results_and_their_data_reopen_after_a_restart(
    data_dir: Path, build_profiles: BuildProfiles, build_packages: Path
) -> None:
    core = start_build_core(data_dir, build_profiles.root, build_packages)
    try:
        final = create(core, "Keep a notes list for me, no screen")
        assert final["state"] == "active", final
        app_id = final["app_id"]
        output(core, app_id, "add_note", {"title": "Water the plants"})
        before = detail(core, app_id)
        unfinished = start_creation(core, briefed(core, "Keep a notes list for me"), "hang")
    finally:
        core.stop()

    core = start_build_core(data_dir, build_profiles.root, build_packages)
    try:
        after = detail(core, app_id)
        for key in ("app_id", "version_id", "release_id", "package_sha256", "runtime_profile_id"):
            assert after[key] == before[key], key
        assert [n["values"]["title"] for n in notes(core, app_id)] == ["Water the plants"]
        output(core, app_id, "add_note", {"title": "Book the dentist"})
        assert output(core, app_id, "count_notes", {}) == {"count": 2}

        with core.client() as client:
            stale = client.get(f"/api/creations/{unfinished['creation_id']}").json()
        # Either the creation saw its build interrupted by the shutdown (runtime_quit) before
        # Core exited, or the next start reconciled it (core_restarted). Both end the same way:
        # failed, retry offered, never revived.
        assert stale["state"] == "failed"
        assert stale["failure"]["reason"] in {"core_restarted", "runtime_quit"}, stale["failure"]
        assert stale["failure"]["next_step"] == "retry"
        assert stale["app_id"] not in apps(core), "an unfinished creation never becomes active"
        record_evidence("f08-reopen", {"before": before, "after": after, "unfinished": stale})
    finally:
        core.stop()


def test_a_builder_that_changes_the_assigned_identity_is_refused(
    data_dir: Path, build_profiles: BuildProfiles, build_packages: Path
) -> None:
    core = start_build_core(
        data_dir,
        build_profiles.root,
        build_packages,
        {"ALPHA_BUILD_MAX_TOTAL_SECONDS": "1"},
    )
    try:
        final = create(
            core, "Keep a notes list for me, no screen", "package notes_ok --wrong-app-id"
        )
        assert final["state"] == "failed", final
        assert final["failure"]["next_step"] in {"retry", "revise"}
        build = build_of(core, final["build_id"])
        assert build["state"] == "failed"
        identity = checks(report(core, build))["package.identity"]
        assert identity["status"] == "failed", identity
        assert final["app_id"] not in apps(core)
        assert f"{final['app_id']}-other" not in apps(core)
    finally:
        core.stop()


def test_activation_is_compare_and_swap_on_the_current_release(build_core: CoreProcess) -> None:
    core = build_core
    plan = {"scenarios": NOTES_PLAN["scenarios"], "ui": None}
    first = wait_build(core, submit(core, "fake:package notes_ok", plan)["build_id"])
    second = wait_build(core, submit(core, "fake:package notes_slow", plan)["build_id"])
    assert first["state"] == second["state"] == "ready", (first, second)

    with core.client() as client:
        installed = client.post(
            f"/api/builds/{first['build_id']}/activate", json={"expected_release_id": None}
        )
        assert installed.status_code == 200, installed.text
        release = installed.json()["release_id"]

        # Someone else changed the App since this caller looked: refused, nothing replaced.
        stale = client.post(
            f"/api/builds/{second['build_id']}/activate", json={"expected_release_id": None}
        )
        assert stale.status_code == 409, stale.text
        assert apps(core)[installed.json()["app_id"]]["current_release_id"] == release

        swapped = client.post(
            f"/api/builds/{second['build_id']}/activate", json={"expected_release_id": release}
        )
        assert swapped.status_code == 200, swapped.text
        assert swapped.json()["release_id"] != release
        replay = client.post(
            f"/api/builds/{first['build_id']}/activate", json={"expected_release_id": release}
        )
        assert replay.status_code == 409, "an old expectation cannot roll the App back"


# ----- F08.C04 -------------------------------------------------------------------------------


def test_two_created_results_share_a_profile_with_independent_data_and_scratch(
    build_core: CoreProcess,
) -> None:
    core = build_core
    first = create(core, "Keep a notes list for me, no screen", "package notes_slow")
    second = create(core, "Keep a notes list for me, no screen", "package notes_slow")
    assert first["state"] == second["state"] == "active", (first, second)
    a, b = first["app_id"], second["app_id"]
    assert a != b
    profile_a = detail(core, a)["runtime_profile_id"]
    assert profile_a == detail(core, b)["runtime_profile_id"], "one shared runtime profile"

    # A long run in A and a short one in B at the same time.
    slow = start_action(core, a, "slow_note", {"title": "A, never saved", "seconds": 60})
    assert slow.status_code == 202, slow.text
    slow_id = slow.json()["run_id"]
    core.wait_for_state(slow_id, {"running"})
    quick = wait_run(
        core,
        start_action(core, b, "slow_note", {"title": "B note", "seconds": 0.5}).json()["run_id"],
    )
    assert quick["state"] == "succeeded", quick

    # Cancelling A's run stops only that run.
    with core.client() as client:
        assert client.post(f"/api/runs/{slow_id}/cancel").status_code in (200, 202)
    cancelled = wait_run(core, slow_id)
    assert cancelled["state"] == "cancelled", cancelled
    assert notes(core, a) == [], "a cancelled run saved nothing"
    assert [n["values"]["title"] for n in notes(core, b)] == ["B note"]

    # A failure in A does not touch B either.
    refused = start_action(core, a, "add_note", {"title": ""})
    if refused.status_code == 202:
        assert wait_run(core, refused.json()["run_id"])["state"] == "failed"
    else:
        assert refused.status_code == 422

    # Both keep working, each with its own data and its own scratch, on the same interpreter.
    probe_a = output(core, a, "slow_note", {"title": "A note", "seconds": 0})
    probe_b = output(core, b, "slow_note", {"title": "Another B note", "seconds": 0})
    assert probe_a["python"] == probe_b["python"] == quick["output"]["python"]
    assert probe_a["scratch"] != probe_b["scratch"] != quick["output"]["scratch"]
    assert probe_a["pid"] != probe_b["pid"]
    assert [n["values"]["title"] for n in notes(core, a)] == ["A note"]
    assert sorted(n["values"]["title"] for n in notes(core, b)) == ["Another B note", "B note"]
    record_evidence(
        "f08-shared-profile",
        {
            "apps": [a, b],
            "runtime_profile_id": profile_a,
            "cancelled_run": {k: cancelled[k] for k in ("run_id", "state", "terminal_reason")},
            "concurrent_run": {k: quick[k] for k in ("run_id", "state")},
            "probe_a": probe_a,
            "probe_b": probe_b,
            "notes_a": [n["values"]["title"] for n in notes(core, a)],
            "notes_b": [n["values"]["title"] for n in notes(core, b)],
        },
    )
