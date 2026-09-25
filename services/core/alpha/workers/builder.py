"""Builder worker profile.

Reads one job on stdin, runs the selected harness inside the leased workspace and emits JSON
lines on stdout: progress events (one per normalized harness event) and a final result line
carrying the harness outcome. Core owns the authoritative build state; this process never
touches the control store, live data or any release.

Job shape (JSON):
  {"request": <BuildRequest>, "harness": "fake" | "claude-code-cli", "workspace": "<dir>",
   "goal": str, "instructions": str, "acceptance_examples": [...], "model": str,
   "platform_python": "<path>"}
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
from alpha.builds.harness_fake import FakeHarness


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


def select_harness(name: str, platform_python: Path) -> BuilderHarness:
    if name == "fake":
        return FakeHarness()
    if name == "claude-code-cli":
        return ClaudeCliHarness(platform_python=platform_python)
    raise ValueError(f"unknown harness: {name}")


def main() -> int:
    raw = sys.stdin.readline()
    try:
        job = json.loads(raw)
        request = BuildRequest.model_validate(job["request"])
        harness = select_harness(str(job["harness"]), Path(str(job["platform_python"])))
    except Exception as exc:  # invalid job is a failed attempt, reported honestly
        emit({"kind": "error", "code": "invalid_job", "message": str(exc)})
        return 2

    inputs = HarnessInputs(
        request=request,
        workspace=Path(str(job["workspace"])),
        goal=str(job.get("goal", "")),
        instructions=str(job.get("instructions", "")),
        acceptance_examples=list(job.get("acceptance_examples", [])),
        model=str(job.get("model", "default")),
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
