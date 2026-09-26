"""The shell a person uses, end to end (M1-R06, review finding F05).

The real desktop shell build in the pinned headless browser, against a real Core with the control
routes: ask, create, open the result, save with its main action, meet a refusal, and find the App,
its data and its runs after a reload. This is browser evidence of the shell and platform path,
not of generation quality; generated screens and live generation are observed in the Alpha window.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.integration.build_harness import node, validator_browser
from tests.integration.conftest import REPO_ROOT, CoreProcess
from tests.integration.test_creations import apps, notes
from tests.ui.test_shell import build_shell

pytestmark = pytest.mark.integration

ENTRY = "Call the bank"
TOO_LONG = "x" * 301  # the notes collection keeps titles of at most 300 characters


def journey(dist: Path, evidence: Path) -> dict[str, Any]:
    browser = validator_browser()
    if browser is None:
        pytest.skip("the pinned headless browser is not installed")
    job = evidence / "journey-job.json"
    job.write_text(
        json.dumps(
            {
                "dist_dir": str(dist),
                "browser": str(browser),
                "evidence_dir": str(evidence),
                "request": "Keep a notes list for me, no screen",
                "builder_hint": "package notes_ok",
                "entry": ENTRY,
                "too_long": TOO_LONG,
            }
        )
    )
    proc = subprocess.run(
        [str(node()), str(REPO_ROOT / "tests" / "ui" / "shell_journey.mjs"), str(job)],
        capture_output=True,
        text=True,
        timeout=420,
        check=False,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    assert lines, proc.stderr[-3000:]
    data: dict[str, Any] = json.loads(lines[-1])
    return data


def test_a_person_creates_uses_and_reopens_a_result_through_the_shell(
    build_core: CoreProcess, tmp_path: Path
) -> None:
    dist = build_shell(build_core, tmp_path / "dist")
    evidence = Path(os.environ.get("ALPHA_EVIDENCE_DIR") or tmp_path / "evidence") / "shell"
    evidence.mkdir(parents=True, exist_ok=True)
    result = journey(dist, evidence)
    (evidence / "journey.json").write_text(json.dumps(result, indent=2))
    assert "error" not in result, (result.get("error"), result.get("page_text"))
    assert result["errors"] == []
    steps = result["steps"]

    assert "passed all" in steps["ready"]
    assert steps["main_action"] == "Add a note"
    assert steps["saved"].startswith("Done.")
    # The refusal is in plain words, keeps what was typed, and saves nothing.
    assert steps["refusal"].startswith("Not done.")
    for leak in ("handler_exception", "InvalidValue", "Traceback", "{", "Something went wrong"):
        assert leak not in steps["refusal"], steps["refusal"]
    assert steps["refusal_kept_input"] is True
    assert ENTRY in steps["saved_data"] and TOO_LONG not in steps["saved_data"]
    assert steps["count"].replace("\n", " ").endswith("Count 1"), steps["count"]
    # After a reload: listed, same data, and every run in Activity with a plain outcome.
    made = steps["ready"].split(" is ready")[0]
    assert steps["listed_after_reload"] == f"Open {made}", "one name for the App throughout"
    assert ENTRY in steps["saved_after_reload"]
    assert sum("Add note" in head for head in steps["activity"]) == 2, steps["activity"]
    assert any("Count notes" in head for head in steps["activity"]), steps["activity"]
    assert [n for n in steps["activity_not_done"] if n.startswith("Not done")], steps
    assert abs(steps["activity_indent"]) <= 1, steps["activity_indent"]

    # Independently of the shell: exactly the one entry was stored.
    [app_id] = apps(build_core)
    assert [n["values"]["title"] for n in notes(build_core, app_id)] == [ENTRY]
