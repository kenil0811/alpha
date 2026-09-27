"""Trusted tools the build pipeline runs outside Core: the platform's pinned Node, the UI build
tool (tools/ui_build) and the UI render check (workers/validator) with its pinned headless
browser. The host supplies their locations; Core never searches PATH for them.

`resources` is the platform resources directory: the repository root during development, the
bundled resources directory once packaged (F22). It holds `templates/app`, `tools/ui_build`,
`workers/validator` and `packages/app-sdk/REFERENCE.md`.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha.data.packages import UiBuildFailed
from alpha.execution.profiles import InstalledProfile

UI_BUILD_TIMEOUT_SECONDS = 180


@dataclass(frozen=True)
class PlatformResources:
    root: Path

    @property
    def app_template(self) -> Path:
        return self.root / "templates" / "app"

    @property
    def sdk_reference(self) -> Path:
        return self.root / "packages" / "app-sdk" / "REFERENCE.md"

    @property
    def app_contract_reference(self) -> Path:
        return self.root / "templates" / "app" / "APP_CONTRACT.md"

    @property
    def ui_build_tool(self) -> Path:
        return self.root / "tools" / "ui_build" / "build_app_ui.mjs"

    @property
    def ui_validator(self) -> Path:
        return self.root / "workers" / "validator" / "src" / "ui_check.mjs"

    @property
    def browser_worker(self) -> Path:
        return self.root / "workers" / "validator" / "src" / "browser_session.mjs"


@dataclass(frozen=True)
class UiToolchain:
    node: Path
    resources: PlatformResources
    browser: Path | None

    def problems(self) -> list[str]:
        found: list[str] = []
        if not self.node.is_file():
            found.append(f"Node is not installed at {self.node}")
        if not self.resources.ui_build_tool.is_file():
            found.append("the UI build tool is missing")
        return found

    def render_problems(self) -> list[str]:
        found = self.problems()
        if not self.resources.ui_validator.is_file():
            found.append("the UI render check is missing")
        if self.browser is None or not self.browser.is_file():
            found.append("the pinned headless browser is not installed")
        return found

    def build_ui(self, src: Path, out: Path, profile: InstalledProfile) -> dict[str, Any]:
        """Compile `src` against the UI build profile into one static document under `out`."""
        problems = self.problems()
        if problems:
            raise UiBuildFailed("; ".join(problems))
        argv = [
            str(self.node),
            str(self.resources.ui_build_tool),
            "--profile",
            str(profile.location),
            "--src",
            str(src),
            "--out",
            str(out),
        ]
        scratch = out.parent / ".ui-build-tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        env = {"LC_ALL": "C.UTF-8", "HOME": str(scratch), "TMPDIR": str(scratch)}
        code, stdout, stderr = run_process_group(argv, env, UI_BUILD_TIMEOUT_SECONDS)
        _remove_quietly(scratch)
        if code != 0:
            log = (stderr or stdout)[-6000:]
            marker = "ui build failed: "
            if marker in log:
                # Everything the tool reported, including multi-line type errors.
                message = log[log.index(marker) + len(marker) :].strip()
            else:
                message = log.strip().splitlines()[-1] if log.strip() else f"exit {code}"
            raise UiBuildFailed(message[:3000], log)
        report: dict[str, Any] = json.loads((out / "build.json").read_text("utf-8"))
        return report


def run_process_group(
    argv: list[str], env: dict[str, str], timeout_seconds: float
) -> tuple[int, str, str]:
    """Run a trusted tool in its own process group; on timeout the whole group is killed (the
    UI build spawns bundler helper processes)."""
    process = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
        encoding="utf-8",
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        stdout, stderr = process.communicate()
        return (
            124,
            stdout,
            (stderr or "") + f"\nui build failed: timed out after {timeout_seconds}s",
        )
    try:
        os.killpg(process.pid, signal.SIGKILL)  # helpers that outlived the leader
    except (ProcessLookupError, PermissionError):
        pass
    return process.returncode, stdout, stderr


def _remove_quietly(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
