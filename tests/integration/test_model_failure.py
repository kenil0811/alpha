"""M1-R02 (review finding F04): an App must not turn a failed model estimate into a saved value.

Real Core, real App runtime and UI profiles; only the builder is the fake that copies fixture
packages, and App model calls use the fake route. Each variant differs from `notes_ok` only in
`add_timed_note`, which asks the model how many minutes a note takes.
"""

from __future__ import annotations

import copy
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

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


def timed_plan(with_planned_failure: bool) -> dict[str, Any]:
    plan = copy.deepcopy(NOTES_PLAN)
    plan["scenarios"].append(
        {
            "id": "timed",
            "description": "A note with a time estimate is saved",
            "steps": [
                {
                    "kind": "invoke",
                    "id": "add",
                    "action": "add_timed_note",
                    "input": {"title": "Call mum"},
                },
                {
                    "kind": "records",
                    "id": "stored",
                    "collection": "notes",
                    "includes": [{"title": "Call mum"}],
                },
            ],
        }
    )
    if with_planned_failure:
        plan["scenarios"].append(
            {
                "id": "timed_offline",
                "description": "Without the model, the note is kept with its time unknown",
                "steps": [
                    {
                        "kind": "invoke",
                        "id": "add",
                        "action": "add_timed_note",
                        "input": {"title": "Water the plants"},
                        "model": "unavailable",
                    },
                    {
                        "kind": "records",
                        "id": "unknown",
                        "collection": "notes",
                        "count": 1,
                        "includes": [{"title": "Water the plants", "minutes": None}],
                    },
                ],
            }
        )
    return plan


@pytest.fixture
def once_core(
    data_dir: Path, build_profiles: BuildProfiles, build_packages: Path
) -> Iterator[CoreProcess]:
    proc = start_build_core(
        data_dir, build_profiles.root, build_packages, {"ALPHA_BUILD_MAX_TOTAL_SECONDS": "1"}
    )
    try:
        yield proc
    finally:
        proc.stop()


def verified(
    core: CoreProcess, package: str, planned_failure: bool = False
) -> tuple[dict[str, Any], dict[str, Any]]:
    created = submit(core, f"fake:package {package}", timed_plan(planned_failure))
    final = wait_build(core, created["build_id"])
    return final, checks(report(core, final))


def test_an_honest_estimator_passes_including_a_planned_model_failure(
    once_core: CoreProcess,
) -> None:
    final, found = verified(once_core, "estimate_honest", planned_failure=True)
    assert final["state"] == "ready", {
        k: v["summary"] for k, v in found.items() if v["status"] != "passed"
    }
    check = found["model.failure.add_timed_note"]
    assert check["status"] == "passed", check
    assert check["detail"]["estimate_fields"] == ["notes.minutes"]
    assert set(check["detail"]["faults"]) == {"unavailable", "malformed", "timeout"}
    assert found["behavior.timed_offline.unknown"]["status"] == "passed"


def test_an_invented_number_after_a_model_failure_is_caught(once_core: CoreProcess) -> None:
    final, found = verified(once_core, "estimate_invented")
    assert final["state"] == "failed"
    check = found["model.failure.add_timed_note"]
    assert check["status"] == "failed" and check["required"] is True
    assert "saved minutes=30" in check["summary"], check["summary"]
    for fault in ("unavailable", "malformed", "timeout"):
        assert f"model {fault}" in check["summary"]


def test_a_planned_model_failure_catches_an_invented_number_too(once_core: CoreProcess) -> None:
    final, found = verified(once_core, "estimate_invented", planned_failure=True)
    assert final["state"] == "failed"
    step = found["behavior.timed_offline.unknown"]
    assert step["status"] == "failed", step


def test_a_model_result_stored_without_an_estimate_label_is_caught(once_core: CoreProcess) -> None:
    final, found = verified(once_core, "estimate_unlabelled")
    assert final["state"] == "failed"
    check = found["model.failure.add_timed_note"]
    assert check["status"] == "failed"
    assert "without labelling it an estimate" in check["summary"]


def test_an_unexercised_model_action_does_not_hold_back_the_screen_checks(
    once_core: CoreProcess,
) -> None:
    """M1-R07: when no planned step makes an action call the model, its model-failure check is
    an advisory skip. That skip used to stop the screen checks, so the build could never pass
    (the calorie tracker's edit_entry, three attempts)."""
    created = submit(once_core, "fake:package estimate_honest", copy.deepcopy(NOTES_PLAN))
    final = wait_build(once_core, created["build_id"])
    found = checks(report(once_core, final))
    advisory = found["model.failure.add_timed_note"]
    assert advisory["status"] == "skipped" and advisory["required"] is False, advisory
    assert "ui.not_run" not in found
    assert found["ui.primary.steps"]["status"] == "passed"
    assert final["state"] == "ready", {
        k: v["summary"] for k, v in found.items() if v["status"] != "passed"
    }
