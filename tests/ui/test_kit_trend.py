"""M1-R05 (review finding F09): the shared trend chart stays compact and readable for 1, 7 and 30
days, gaps, zero and long titles, at the widths an App's screen gets inside Alpha: about 1002px
(default window) and 670px (minimum window). Real kit build, pinned headless browser."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.integration.build_harness import node, validator_browser
from tests.integration.conftest import REPO_ROOT

pytestmark = pytest.mark.integration

APP_WIDTHS = [1002, 670]


def build_reference(out: Path) -> Path:
    env = {**os.environ, "PATH": f"{node().parent}:{os.environ.get('PATH', '')}"}
    subprocess.run(
        ["pnpm", "--filter", "@alpha/ui-kit", "exec", "vite", "build", "--config",
         "reference/vite.config.ts", "--outDir", str(out), "--emptyOutDir"],
        cwd=REPO_ROOT, env=env, check=True, capture_output=True, text=True,
    )  # fmt: skip
    return out


def test_trend_charts_stay_compact_and_readable(tmp_path: Path) -> None:
    browser = validator_browser()
    if browser is None:
        pytest.skip("the pinned headless browser is not installed")
    dist = build_reference(tmp_path / "kit")
    evidence = Path(os.environ.get("ALPHA_EVIDENCE_DIR") or tmp_path / "evidence") / "kit-trend"
    evidence.mkdir(parents=True, exist_ok=True)
    job = evidence / "job.json"
    job.write_text(
        json.dumps(
            {
                "dist_dir": str(dist),
                "browser": str(browser),
                "evidence_dir": str(evidence),
                "widths": APP_WIDTHS,
            }
        )
    )
    proc = subprocess.run(
        [str(node()), str(REPO_ROOT / "tests" / "ui" / "kit_trend_probe.mjs"), str(job)],
        capture_output=True, text=True, timeout=180, check=False,
    )  # fmt: skip
    lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
    assert lines, proc.stderr[-3000:]
    result: dict[str, Any] = json.loads(lines[-1])
    (evidence / "result.json").write_text(json.dumps(result, indent=2))
    assert "error" not in result, result.get("error")
    assert result["errors"] == []
    for width, found in result["widths"].items():
        assert not found["sideways_scroll"], width
        charts = found["charts"]
        assert set(charts) == {
            "1-point",
            "7-one-logged",
            "7-empty",
            "7-zero",
            "30-mixed",
            "long-title",
        }
        for name, chart in charts.items():
            where = f"{name} at {width}px: {chart}"
            assert 80 <= chart["plot_height"] <= 240, where
            assert chart["axis_px"] <= 14, where
            assert chart["bars_overflow"] is False, where
        assert charts["30-mixed"]["slots"] == 30
        assert "Days with entries: 1 of 7" in charts["7-one-logged"]["coverage"]
        assert "Days with entries: 0 of 7" in charts["7-empty"]["coverage"]
