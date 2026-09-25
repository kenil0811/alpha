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
                "lines": (
                    "2026-09-03 groceries 42.50\n2026-09-04 fuel 61.10\n2026-09-05 groceries 7.25"
                )
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
    """Since F07 a build targets installed profiles and is verified as an App Version: publish
    fresh profiles beside the data and start Core exactly as the F07 live qualification does."""
    sys.path.insert(0, str(REPO_ROOT))
    from evals.qualify_build import publish_profiles
    from evals.qualify_build import start_core as start_live_core
    from tests.integration.build_harness import render_packages

    profiles = data_dir.parent / "profiles"
    publish_profiles(profiles)
    seeds = render_packages(data_dir.parent / "seeds")
    return start_live_core(data_dir, token, log_path, profiles, seeds)


def cli_tree_pids() -> list[int]:
    """Builder worker, claude CLI and any of their descendants, by command line."""
    out = subprocess.run(
        ["pgrep", "-f", "alpha.workers.builder|claude -p"], capture_output=True, text=True
    )
    pids = [int(p) for p in out.stdout.split()]
    # descendants of those pids
    ps = subprocess.run(["ps", "-axo", "pid=,ppid="], capture_output=True, text=True).stdout.split(
        "\n"
    )
    children: dict[int, list[int]] = {}
    for row in ps:
        parts = row.split()
        if len(parts) == 2:
            children.setdefault(int(parts[1]), []).append(int(parts[0]))
    result = set(pids)
    stack = list(pids)
    while stack:
        for child in children.get(stack.pop(), []):
            if child not in result:
                result.add(child)
                stack.append(child)
    return sorted(result)


def alive(pids: list[int]) -> list[int]:
    return [
        p
        for p in pids
        if subprocess.run(["kill", "-0", str(p)], capture_output=True).returncode == 0
    ]


def run_interruption_scenario(
    scenario: str,
    client: httpx.Client,
    core: subprocess.Popen[str],
    build_id: str,
    data_dir: Path,
    token: str,
) -> dict[str, Any]:
    """Wait until the real CLI is working (a tool_use event), then cancel or kill Core."""
    deadline = time.monotonic() + 300
    seen_tool_use = False
    while time.monotonic() < deadline and not seen_tool_use:
        events = client.get(f"/api/builds/{build_id}/events").json()["events"]
        seen_tool_use = any(e["kind"] == "harness.harness.tool_use" for e in events)
        if client.get(f"/api/builds/{build_id}").json()["state"] in (
            "ready",
            "failed",
            "cancelled",
        ):
            break
        time.sleep(1.0)
    tree_before = cli_tree_pids()
    summary: dict[str, Any] = {
        "scenario": scenario,
        "tool_use_seen": seen_tool_use,
        "tree_before": tree_before,
    }
    outcome: dict[str, Any] = {}
    if scenario == "cancel":
        response = client.post(f"/api/builds/{build_id}/cancel")
        summary["cancel_status"] = response.status_code
        time.sleep(4.0)
        still = alive(tree_before)
        build_after = client.get(f"/api/builds/{build_id}").json()
        summary.update(
            {
                "tree_alive_after": still,
                "state_after": build_after["state"],
                "terminal_reason": build_after.get("terminal_reason"),
                "attempt_status": build_after["attempts"][0]["status"]
                if build_after["attempts"]
                else None,
                "passed": response.status_code == 200
                and not still
                and build_after["state"] == "cancelled",
            }
        )
        outcome["build_after"] = build_after
    else:
        core.kill()
        core.wait(timeout=10)
        time.sleep(1.0)
        summary["tree_alive_after_core_kill"] = alive(tree_before)
        new_core, port = start_core(data_dir, token, data_dir.parent / "core.restart.stderr.log")
        client.base_url = httpx.URL(f"http://127.0.0.1:{port}")
        time.sleep(2.0)
        build_after = client.get(f"/api/builds/{build_id}").json()
        still = alive(tree_before)
        summary.update(
            {
                "tree_alive_after_restart": still,
                "state_after": build_after["state"],
                "terminal_reason": build_after.get("terminal_reason"),
                "attempts": len(build_after["attempts"]),
                "attempt_status": build_after["attempts"][0]["status"]
                if build_after["attempts"]
                else None,
                "passed": not still
                and build_after["state"] == "failed"
                and build_after.get("terminal_reason", "").startswith("core_restarted")
                and len(build_after["attempts"]) == 1,
            }
        )
        outcome["build_after"] = build_after
        outcome["core_process"] = new_core
    outcome["summary"] = summary
    outcome["events"] = client.get(f"/api/builds/{build_id}/events").json()["events"]
    return outcome


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--goal-file", type=Path, help="JSON file with goal/instructions/acceptance_examples"
    )
    parser.add_argument("--label", default="expenses")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--scenario",
        choices=("build", "cancel", "restart"),
        default="build",
        help="build: full qualification; cancel: cancel mid-build and verify the CLI tree is gone;"
        " restart: kill Core mid-build, restart, verify the build is interrupted and not revived",
    )
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
        if args.scenario in ("cancel", "restart"):
            outcome = run_interruption_scenario(
                args.scenario, client, core, build_id, data_dir, token
            )
            record.update(outcome)
            build = outcome["build_after"]
            record["build"] = build
            core = outcome.get("core_process", core)
            (out_dir / "record.json").write_text(
                json.dumps(record, indent=2, default=str), encoding="utf-8"
            )
            print(f"scenario {args.scenario}: {json.dumps(outcome['summary'])}")
            print(f"evidence written to {out_dir}")
            core.terminate()
            core.wait(timeout=15)
            client.close()
            return 0 if outcome["summary"].get("passed") else 1
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
            f"build finished: state={build['state']} "
            f"reason={build.get('terminal_reason')} in {elapsed:.0f}s"
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
            observed = invoke.json().get("output")
            record["held_out_invoke"]["matches_expected"] = observed == held["expected"]
            print(
                f"held-out invoke: observed={observed} expected={held['expected']} "
                f"match={observed == held['expected']}"
            )
            attempt = build["attempts"][-1]
            workspace = data_dir / "builds" / attempt["workspace_ref"]
            for name in ("verification.report.json", "harness.argv.json"):
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
    # scan retained logs/records for durable secrets (none should exist on this route), then
    # write the record including the scan result
    text = json.dumps(record, default=str) + (out_dir / "core.stderr.log").read_text()
    needles = ("sk-ant-", "sk-", "Bearer ", "oauth", "access_token")
    leaks = [needle for needle in needles if needle in text]
    record["secret_scan"] = {"needles": list(needles), "needles_found": leaks}
    (out_dir / "record.json").write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )
    print(f"evidence written to {out_dir}")
    print(f"secret scan: {leaks or 'nothing found'}")
    return 0 if record.get("build", {}).get("state") == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
