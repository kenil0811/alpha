"""Builder worker profile.

Reads one job on stdin, runs the selected harness inside the leased workspace and emits JSON
lines on stdout: progress events (one per normalized harness event) and a final result line
carrying the harness outcome. Core owns the authoritative build state; this process never
touches the control store, live data or any release.

Job shape (JSON):
  {"request": <BuildRequest>, "harness": "fake" | "claude-code-cli" | "codex-cli",
   "workspace": "<dir>",
   "goal": str, "instructions": str, "model": str, "candidate_python": "<path>",
   "targets": {...}, "fake_packages_dir": "<dir>" | null}

The workspace was materialized by Core (package/, reference/, PLAN.md, REPAIR.md on a repair).
"""

from __future__ import annotations

import json
import signal
import sys
import threading
from pathlib import Path
from typing import Any

from alpha_contracts.builds import BuildRequest

from alpha.builds.harness import BuilderHarness, HarnessInputs
from alpha.builds.harness_claude_cli import ClaudeCliHarness
from alpha.builds.harness_codex_cli import CodexCliHarness
from alpha.builds.harness_fake import FakeHarness


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def select_harness(name: str, candidate_python: Path) -> BuilderHarness:
    if name == "fake":
        return FakeHarness()
    if name == "claude-code-cli":
        return ClaudeCliHarness(candidate_python=candidate_python)
    if name == "codex-cli":
        return CodexCliHarness(candidate_python=candidate_python)
    raise ValueError(f"unknown harness: {name}")


def main() -> int:
    raw = sys.stdin.readline()
    try:
        job = json.loads(raw)
        request = BuildRequest.model_validate(job["request"])
        candidate_python = Path(str(job["candidate_python"]))
        harness = select_harness(str(job["harness"]), candidate_python)
    except Exception as exc:  # invalid job is a failed attempt, reported honestly
        emit({"kind": "error", "code": "invalid_job", "message": str(exc)})
        return 2

    inputs = HarnessInputs(
        request=request,
        workspace=Path(str(job["workspace"])),
        goal=str(job.get("goal", "")),
        instructions=str(job.get("instructions", "")),
        model=str(job.get("model", "default")),
        candidate_python=candidate_python,
        targets={str(k): str(v) for k, v in (job.get("targets") or {}).items()},
        fake_packages_dir=job.get("fake_packages_dir"),
        claude_auth=str(job.get("claude_auth", "cli")),
    )
    capabilities = harness.capabilities()
    emit({"kind": "progress", "stage": "capabilities", "capabilities": capabilities.__dict__})

    session = harness.start(inputs)
    cancelled = threading.Event()

    def on_term(signum: int, _frame: object) -> None:
        cancelled.set()
        harness.cancel(session)

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)

    emit({"kind": "progress", "stage": "harness_started", "session_ref": session.session_ref})
    for event in harness.events(session):
        emit(
            {
                "kind": "progress",
                "stage": "harness_event",
                "event": event.kind,
                "payload": event.payload,
            }
        )
    outcome = harness.result(session)
    emit(
        {
            "kind": "result",
            "output": {
                "status": outcome.status.value,
                "failure_category": outcome.failure_category.value
                if outcome.failure_category
                else None,
                "usage": outcome.usage.model_dump(mode="json") if outcome.usage else None,
                "diagnostics": [d.model_dump(mode="json") for d in outcome.diagnostics],
                "final_text": outcome.final_text[:4000],
                "exit_code": outcome.exit_code,
                "harness": capabilities.name,
                "harness_version": capabilities.version,
                "cancelled": cancelled.is_set(),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
