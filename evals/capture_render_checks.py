"""Capture the rendered-UI evidence for F07.C02 with the deterministic builder.

Builds the neutral notes fixture and its screen defects (blocking overflow, a screen that only
pretends to save, a screen that hides failures) through a real Core, the real UI build tool and
the pinned headless browser, each on a single attempt. Copies every verification report and the
render check's screenshots to docs/development/evidence/logs/F07-rendered-<stamp>/.

Usage: uv run python evals/capture_render_checks.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from evals.qualify_build import publish_profiles  # noqa: E402
from tests.integration.build_harness import (  # noqa: E402
    render_packages,
    report,
    start_build_core,
    submit,
    wait_build,
)

CASES = ["notes_ok", "overflow", "ui_fake_save", "ui_hides_errors"]
EVIDENCE = REPO_ROOT / "docs" / "development" / "evidence" / "logs"


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = EVIDENCE / f"F07-rendered-{stamp}"
    out.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="alpha-f07-rendered-"))
    published = publish_profiles(work / "profiles")
    packages = render_packages(work / "packages")
    data = work / "data"
    data.mkdir()
    core = start_build_core(
        data, work / "profiles", packages, {"ALPHA_BUILD_MAX_TOTAL_SECONDS": "1"}
    )
    summary: dict[str, Any] = {
        "commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
        ).stdout.strip(),
        "profiles": {k: v["profile_id"] for k, v in published.items()},
        "cases": {},
    }
    try:
        for case in CASES:
            build = wait_build(core, submit(core, f"fake:package {case}")["build_id"])
            rep = report(core, build)
            workspace = data / "builds" / build["attempts"][0]["workspace_ref"]
            target = out / case
            target.mkdir()
            (target / "verification.report.json").write_text(json.dumps(rep, indent=2))
            shots = workspace / "evidence" / "ui"
            if shots.is_dir():
                shutil.copytree(shots, target / "screenshots")
            summary["cases"][case] = {
                "state": build["state"],
                "ui": {c["id"]: c["status"] for c in rep["checks"] if c["stage"] == "ui"},
                "failed": [c["id"] for c in rep["checks"] if c["status"] == "failed"],
                "environment": {k: v for k, v in rep["environment"].items() if k.startswith("ui_")},
            }
            print(f"{case}: {build['state']} failed={summary['cases'][case]['failed']}")
    finally:
        core.stop()
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"evidence written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
