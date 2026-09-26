"""`just verify-ticket <ticket-id>` dispatcher.

Runs the registered deterministic checks for a ticket, then reports separately which required
checks of other evidence kinds (native, live_model, live_source, rendered_ui, review,
user_study) are recorded as passed in docs/development/task_state.json and which remain
pending. Unknown or unimplemented tickets fail. Missing credentials or hardware are never
translated into a pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS = REPO_ROOT / "docs" / "alpha-r2" / "delivery" / "TASKS.json"
STATE = REPO_ROOT / "docs" / "development" / "task_state.json"

AUTOMATED_KINDS = {"integration", "unit"}
LIVE_COMMANDS = {
    "F02": "just qualify-builder  (opt-in live route; see docs/development/decisions)",
    "F03": "just qualify-sandbox (real macOS sandbox probes) + desktop fixture run (native)",
    "F04": "just qualify-assistant (opt-in live route; three request families)",
    "F06": "rendered checks: kit-fixture.html against a development Core, and `just kit-reference`",
    "F07": "just qualify-build repair | limit | generate  (opt-in live builder route)",
    "F08": "G1 on frozen platform code: evals/g1.py create | use | reopen | share (live routes)",
}

# Ticket -> ordered list of (label, argv). Only tickets with real implemented checks appear.
RECIPES: dict[str, list[tuple[str, Sequence[str]]]] = {
    "F01": [
        ("check", ["just", "check"]),
        ("test-core", ["just", "test-core"]),
        ("test-ui", ["just", "test-ui"]),
        ("test-integration", ["just", "test-integration"]),
        ("toolchain-locks", ["just", "verify-locks"]),
    ],
    "F04": [
        ("check", ["just", "check"]),
        ("test-ui", ["just", "test-ui"]),
        (
            "test-assistant",
            [
                "uv",
                "run",
                "pytest",
                "tests/integration/test_assistant.py",
                "-q",
                "-m",
                "integration",
            ],
        ),
    ],
    "F03": [
        ("check", ["just", "check"]),
        ("test-ui", ["just", "test-ui"]),
    ],
    "F05": [
        ("check", ["just", "check"]),
        ("toolchain-locks", ["just", "verify-locks"]),
        (
            "test-apps",
            [
                "uv",
                "run",
                "pytest",
                "tests/integration/test_app_records.py",
                "tests/integration/test_app_rejections.py",
                "tests/integration/test_app_artifacts_models.py",
                "tests/integration/test_app_profile_sharing.py",
                "-q",
                "-m",
                "integration",
            ],
        ),
        ("test-integration-regression", ["just", "test-integration"]),
    ],
    "F06": [
        ("check", ["just", "check"]),
        ("toolchain-locks", ["just", "verify-locks"]),
        ("test-ui", ["just", "test-ui"]),
        (
            "test-ui-build-and-views",
            [
                "uv",
                "run",
                "pytest",
                "tests/ui",
                "tests/integration/test_app_views.py",
                "-q",
                "-m",
                "integration",
            ],
        ),
    ],
    "F07": [
        ("check", ["just", "check"]),
        ("toolchain-locks", ["just", "verify-locks"]),
        (
            "test-verification",
            [
                "uv",
                "run",
                "pytest",
                "tests/integration/test_candidate_verification.py",
                "tests/integration/test_builds.py",
                "-q",
                "-m",
                "integration",
            ],
        ),
        ("test-integration-regression", ["just", "test-integration"]),
    ],
    "F08": [
        ("check", ["just", "check"]),
        ("toolchain-locks", ["just", "verify-locks"]),
        ("test-ui", ["just", "test-ui"]),
        (
            "test-creations",
            [
                "uv",
                "run",
                "pytest",
                "tests/integration/test_creations.py",
                "-q",
                "-m",
                "integration",
            ],
        ),
        ("test-integration-regression", ["just", "test-integration"]),
    ],
    "F02": [
        ("check", ["just", "check"]),
        ("test-core", ["just", "test-core"]),
        (
            "test-builds",
            ["uv", "run", "pytest", "tests/integration/test_builds.py", "-q", "-m", "integration"],
        ),
    ],
}


def _run(label: str, argv: Sequence[str]) -> int:
    print(f"\n=== {label}: {' '.join(argv)}", flush=True)
    completed = subprocess.run(list(argv), cwd=REPO_ROOT)
    print(f"=== {label}: exit {completed.returncode}", flush=True)
    return completed.returncode


def _report_recorded_checks(ticket: str) -> None:
    registry = json.loads(TASKS.read_text(encoding="utf-8"))
    packet = next(t for t in registry["tickets"] if t["id"] == ticket)
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    recorded = state.get("tickets", {}).get(ticket, {}).get("checks", {})
    print(f"\n=== required checks for {ticket} (from task_state.json; helper-audited bookkeeping)")
    for check in packet["required_checks"]:
        entry = recorded.get(check["id"], {})
        result = entry.get("result", "pending")
        kind = check["evidence_kind"]
        source = "automated here" if kind in AUTOMATED_KINDS else f"{kind} evidence required"
        print(f"  {check['id']:<9} {kind:<12} {result:<8} ({source})")
    print("  Note: native/live/rendered/review/user checks are not run by this command.")
    if ticket in LIVE_COMMANDS:
        print(f"  Live check command (explicit opt-in): {LIVE_COMMANDS[ticket]}")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: verify_ticket.py <ticket-id>", file=sys.stderr)
        return 2
    ticket = argv[0].upper()
    registry = json.loads(TASKS.read_text(encoding="utf-8"))
    known = {t["id"] for t in registry["tickets"]}
    if ticket not in known:
        print(f"verify-ticket: unknown ticket {ticket!r}", file=sys.stderr)
        return 2
    if ticket not in RECIPES:
        print(
            f"verify-ticket: {ticket} has no implemented verification recipe yet", file=sys.stderr
        )
        return 3
    failures = [label for label, cmd in RECIPES[ticket] if _run(label, cmd) != 0]
    _report_recorded_checks(ticket)
    if failures:
        print(f"\nverify-ticket {ticket}: FAILED ({', '.join(failures)})", file=sys.stderr)
        return 1
    print(f"\nverify-ticket {ticket}: automated checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
