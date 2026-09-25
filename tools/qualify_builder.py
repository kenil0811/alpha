"""Opt-in live builder qualification (F02.C01).

Starts a real Core with the Claude Code CLI route enabled, submits a fresh plain-language goal
with independently authored acceptance examples, follows the build to its terminal state, then
invokes the generated action with a new input. Everything (events, usage, package index,
validation report, invoke result) is written to docs/development/evidence/logs/. Nothing here
edits generated source. Runs on the founder's subscription; no API key exists.

Usage: uv run python tools/qualify_builder.py [--goal-file path] [--label name]
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = REPO_ROOT / "docs" / "development" / "evidence" / "logs"

DEFAULT_GOAL = {
    "goal": (
        "I keep a list of expenses as text lines like '2026-09-03 groceries 42.50' and "
        "'2026-09-04 fuel 61.10'. I want something that tells me the total per category and "
        "the overall total, ignoring lines it cannot understand."
    ),
    "instructions": (
        "Implement exactly one action with id 'summarize_expenses' taking a single string "
        "argument 'lines' (newline-separated). Return an object with 'totals' (mapping category "
        "to a number rounded to 2 decimals), 'overall' (number rounded to 2 decimals) and "
        "'ignored' (count of lines that could not be parsed). A parsable line is: ISO date, one "
        "or more spaces, a single-word category, one or more spaces, a decimal amount."
    ),
    "acceptance_examples": [
        {
            "action_id": "summarize_expenses",
            "input": {
                "lines": "2026-09-03 groceries 42.50\n2026-09-04 fuel 61.10\n2026-09-05 groceries 7.25"
            },
            "expected": {
                "totals": {"groceries": 49.75, "fuel": 61.10},
                "overall": 110.85,
                "ignored": 0,
            },
        },
        {
            "action_id": "summarize_expenses",
            "input": {"lines": "not a line\n2026-09-06 coffee 3.40\n\n2026-09-07 coffee 3.6"},
            "expected": {"totals": {"coffee": 7.0}, "overall": 7.0, "ignored": 1},
        },
        {
            "action_id": "summarize_expenses",
            "input": {"lines": ""},
            "expected": {"totals": {}, "overall": 0.0, "ignored": 0},
        },
    ],
    "held_out_invoke": {
        "action_id": "summarize_expenses",
        "input": {
            "lines": "2026-09-10 rent 1200\n2026-09-11 groceries 15.5\nbad\n2026-09-12 rent 0.5"
        },
        "expected": {
            "totals": {"rent": 1200.5, "groceries": 15.5},
            "overall": 1216.0,
            "ignored": 1,
        },
    },
}


def start_core(data_dir: Path, token: str, log_path: Path) -> tuple[subprocess.Popen[str], int]:
    env = {
        "ALPHA_DATA_DIR": str(data_dir),
        "ALPHA_SESSION_TOKEN": token,
        "ALPHA_ALLOWED_ORIGINS": "http://localhost:1420",
        "ALPHA_ENABLED_MODEL_ROUTES": "claude-code-cli,fake",
        "ALPHA_BUILDER_PATH": (
            "/opt/homebrew/bin:/opt/homebrew/opt/node@24/bin:/usr/local/bin:/usr/bin:/bin"
        ),
        "ALPHA_BUILDER_HOME": os.environ["HOME"],
        "ALPHA_WATCH_PARENT": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "alpha.main"],
        stdout=subprocess.PIPE,
        stderr=log_path.open("w", encoding="utf-8"),
        env=env,
        text=True,
        cwd=str(REPO_ROOT),
    )
    assert process.stdout is not None
    for line in process.stdout:
        if line.startswith("ALPHA_CORE_READY "):
            return process, int(json.loads(line[len("ALPHA_CORE_READY ") :])["port"])
        if line.startswith("ALPHA_CORE_ERROR "):
            raise SystemExit(line)
    raise SystemExit("core did not start")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--goal-file", type=Path, help="JSON file with goal/instructions/acceptance_examples"
    )
    parser.add_argument("--label", default="expenses")
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()
    spec: dict[str, Any] = (
        json.loads(args.goal_file.read_text()) if args.goal_file else DEFAULT_GOAL
    )
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out_dir = EVIDENCE / f"F02-live-{args.label}-{stamp}"
    out_dir.mkdir()
    data_dir = out_dir / "data"
    data_dir.mkdir()
    token = secrets.token_hex(32)
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
    ).stdout.strip()
    core, port = start_core(data_dir, token, out_dir / "core.stderr.log")
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    record: dict[str, Any] = {"commit": commit, "started_at": stamp, "spec": spec}
    try:
        routes = client.get("/api/model-routes").json()["routes"]
        record["routes"] = routes
        submission = {
            "goal": spec["goal"],
            "instructions": spec.get("instructions", ""),
            "acceptance_examples": spec["acceptance_examples"],
            "route_id": "claude-code-cli",
        }
        response = client.post("/api/builds", json=submission)
        response.raise_for_status()
        build = response.json()
        build_id = build["build_id"]
        print(f"build {build_id} submitted on route claude-code-cli; following events…", flush=True)
        seen = 0
        deadline = time.monotonic() + args.timeout
        started = time.monotonic()
        while time.monotonic() < deadline:
            events = client.get(f"/api/builds/{build_id}/events", params={"after": seen}).json()[
                "events"
            ]
            for event in events:
                seen = event["sequence"]
                payload = json.dumps(event["payload"])[:160]
                print(f"  [{event['sequence']:>3}] {event['kind']}: {payload}", flush=True)
            build = client.get(f"/api/builds/{build_id}").json()
            if build["state"] in ("ready", "failed", "cancelled"):
                break
            time.sleep(1.0)
        elapsed = time.monotonic() - started
        record["build"] = build
        record["events"] = client.get(f"/api/builds/{build_id}/events").json()["events"]
        record["elapsed_seconds"] = round(elapsed, 1)
        print(
            f"build finished: state={build['state']} reason={build.get('terminal_reason')} in {elapsed:.0f}s"
        )
        if build["state"] == "ready":
            held = spec["held_out_invoke"]
            invoke = client.post(
                f"/api/builds/{build_id}/invoke",
                json={"action_id": held["action_id"], "input": held["input"]},
            )
            record["held_out_invoke"] = {
                "request": held,
                "status": invoke.status_code,
                "response": invoke.json(),
            }
            observed = invoke.json().get("output", {}).get("calls", [{}])[0].get("output")
            record["held_out_invoke"]["matches_expected"] = observed == held["expected"]
            print(
                f"held-out invoke: observed={observed} expected={held['expected']} match={observed == held['expected']}"
            )
            attempt = build["attempts"][-1]
            workspace = data_dir / "builds" / attempt["workspace_ref"]
            for name in ("package.index.json", "validation.report.json", "harness.argv.json"):
                path = workspace / name
                if path.is_file():
                    record[name] = json.loads(path.read_text())
            sources = {}
            for path in sorted((workspace / "package").rglob("*")):
                if path.is_file():
                    sources[path.relative_to(workspace / "package").as_posix()] = path.read_text(
                        errors="replace"
                    )
            record["generated_package"] = sources
        record["usage"] = [a.get("usage") for a in build["attempts"]]
    finally:
        core.terminate()
        core.wait(timeout=15)
        client.close()
    (out_dir / "record.json").write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )
    # scan retained logs/records for durable secrets (none should exist on this route)
    text = (out_dir / "record.json").read_text() + (out_dir / "core.stderr.log").read_text()
    leaks = [
        needle
        for needle in ("sk-ant-", "sk-", "Bearer ", "oauth", "access_token")
        if needle in text
    ]
    record["secret_scan"] = {"needles_found": leaks}
    print(f"evidence written to {out_dir}")
    print(f"secret scan: {leaks or 'nothing found'}")
    return 0 if record.get("build", {}).get("state") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
