"""The desktop shell itself, in the pinned headless browser against a real Core (M1-R01).

Covers M1 review findings F01 (each surface uses the window's working area; nothing scrolls
sideways) and F02 (a request stays reachable through navigation and a reload). This is browser
evidence of the real shell build; the native Alpha window is observed separately.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.integration.build_harness import node, validator_browser
from tests.integration.conftest import REPO_ROOT, CoreProcess, start_core

pytestmark = pytest.mark.integration

REQUEST = "slowly: Keep a notes list for me"


@pytest.fixture
def core(tmp_path: Path) -> Iterator[CoreProcess]:
    data = tmp_path / "alpha-data"
    data.mkdir()
    proc = start_core(data)
    try:
        yield proc
    finally:
        proc.stop()


def build_shell(core: CoreProcess, out: Path) -> Path:
    env = {
        **os.environ,
        "PATH": f"{node().parent}:{os.environ.get('PATH', '')}",
        "VITE_ALPHA_CORE_URL": core.base_url,
        "VITE_ALPHA_CORE_TOKEN": core.token,
    }
    subprocess.run(
        [
            "pnpm",
            "--filter",
            "@alpha/desktop",
            "exec",
            "vite",
            "build",
            "--outDir",
            str(out),
            "--emptyOutDir",
        ],
        cwd=REPO_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return out


def probe(dist: Path, evidence: Path) -> dict[str, Any]:
    browser = validator_browser()
    if browser is None:
        pytest.skip("the pinned headless browser is not installed")
    job = evidence / "job.json"
    job.write_text(
        json.dumps(
            {
                "dist_dir": str(dist),
                "browser": str(browser),
                "evidence_dir": str(evidence),
                "widths": [1100, 768],
                "request": REQUEST,
            }
        )
    )
    proc = subprocess.run(
        [str(node()), str(REPO_ROOT / "tests" / "ui" / "shell_probe.mjs"), str(job)],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    assert lines, proc.stderr[-3000:]
    data: dict[str, Any] = json.loads(lines[-1])
    return data


def test_the_shell_uses_the_window_and_keeps_a_request_through_navigation(
    core: CoreProcess, tmp_path: Path
) -> None:
    dist = build_shell(core, tmp_path / "dist")
    evidence = Path(os.environ.get("ALPHA_EVIDENCE_DIR") or tmp_path / "evidence") / "shell"
    evidence.mkdir(parents=True, exist_ok=True)
    result = probe(dist, evidence)
    (evidence / "result.json").write_text(json.dumps(result, indent=2))
    assert "error" not in result, result.get("error")
    assert result["errors"] == []

    for m in result["layouts"]:
        where = f"{m['surface']} at {m['width']}px: {m}"
        assert not m["sideways_scroll"], where
        # Every surface fills the working area up to its reading width, centred.
        assert m["surface_width"] >= min(1120, m["available"]) - 1, where
        assert abs(2 * m["surface_left"] + m["surface_width"] - m["available"]) <= 2, where

    continuity = result["continuity"]
    assert continuity["request_shown_after_navigation"] is True
    assert continuity["answered_after_navigation"] is True
    assert continuity["request_shown_after_reload"] is True
