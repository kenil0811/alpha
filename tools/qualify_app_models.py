"""Opt-in live smoke of runtime model access (F05.C03 supplementary).

Builds the App runtime profile into a temporary directory, starts a real Core with the
`claude-code-cli` route as the App model route, installs the neutral items fixture, runs its
`estimate_quantity` action once, reads the stored provenance, applies a UI-run correction and
writes the observations to <out_dir>/F05.C03-live-model-smoke.json.

Usage: uv run python tools/qualify_app_models.py <out_dir>
Needs a signed-in Claude Code CLI on this Mac (founder decision 2026-09-25).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.integration.app_harness import (  # noqa: E402
    act,
    build_profile,
    install,
    output,
    render_fixtures,
)
from tests.integration.conftest import start_core  # noqa: E402

TOOL_PATH = "/opt/homebrew/bin:/opt/homebrew/opt/node@24/bin:/usr/local/bin:/usr/bin:/bin"


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    out_dir = Path(argv[0])
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="f05-live-"))
    profile = build_profile(work / "profiles")
    fixtures = render_fixtures(work / "fixture-apps", profile.profile_id)
    data = work / "data"
    data.mkdir()
    core = start_core(
        data,
        routes="fake,claude-code-cli",
        extra_env={
            "ALPHA_PROFILES_DIR": str(profile.root),
            "ALPHA_DEV_FIXTURE_APPS_DIR": str(fixtures),
            "ALPHA_TIMEZONE": "Asia/Kolkata",
            "ALPHA_APP_MODEL_ROUTE": "claude-code-cli",
            "ALPHA_BUILDER_PATH": TOOL_PATH,
            "ALPHA_BUILDER_HOME": os.environ["HOME"],
        },
    )
    try:
        install(core, "items_app")
        started = time.monotonic()
        run = act(core, "items-fixture", "estimate_quantity", {"title": "AA batteries"})
        elapsed = time.monotonic() - started
        estimate = run["output"]
        record = output(core, "items-fixture", "get_item", {"id": estimate["id"]})["record"]
        with core.client() as client:
            calls = client.get(f"/api/runs/{run['run_id']}/model-calls").json()["model_calls"]
        conn = sqlite3.connect(data / "control.sqlite")
        cursor = conn.execute("SELECT * FROM model_usage")
        columns = [c[0] for c in cursor.description]
        usage = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        conn.close()
        corrected = output(
            core,
            "items-fixture",
            "correct_quantity",
            {"id": estimate["id"], "expected_revision": estimate["revision"], "quantity": 4},
            origin="ui",
        )
    finally:
        core.stop()
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=False
    ).stdout.strip()
    result = {
        "commit": commit,
        "profile_id": profile.profile_id,
        "elapsed_seconds": round(elapsed, 1),
        "run_state": run["state"],
        "estimate": estimate,
        "record_provenance": record["provenance"],
        "model_calls": calls,
        "model_usage": usage,
        "after_correction": corrected,
    }
    (out_dir / "F05.C03-live-model-smoke.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps({k: result[k] for k in ("elapsed_seconds", "run_state", "estimate")}, indent=1)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
