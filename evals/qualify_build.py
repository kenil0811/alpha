"""Opt-in live qualification of candidate verification and bounded repair (F07.C03).

Runs a real Core with the Claude Code CLI builder route (the founder's subscription; no API key),
freshly published App runtime and UI build profiles, the real UI build tool and the pinned
headless browser. Scenarios:

  repair    the first candidate is a known defective package (the `fake_persistence` variant of
            the neutral notes fixture: it reports saving but stores nothing); the live builder
            gets the failed checks and must repair it within the limits
  limit     the plan contradicts itself (one note stored with two different titles); the live
            builder cannot satisfy it and must stop at the repair limit with every attempt kept
  generate  a small App with a screen, generated from the template by the live builder

Evidence goes to docs/development/evidence/logs/F07-live-<scenario>-<stamp>/: record.json
(build, events, every attempt's report and repair request, usage, timings, the final package
source), the control store, and the render check's screenshots. Nothing here edits generated
source. Reuses the integration tests' fixture packages and plan (tests/integration).

Usage: uv run python evals/qualify_build.py --scenario repair|limit|generate
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tests.integration.build_harness import (  # noqa: E402
    NOTES_PLAN,
    build_ui_profile,
    node,
    render_packages,
    validator_browser,
)

EVIDENCE = REPO_ROOT / "docs" / "development" / "evidence" / "logs"
NOTES_GOAL = (
    "I want a tiny notes list: I type a short note, it is saved with today's date, and I can see "
    "my latest notes. I also want to know how many notes I have saved."
)
NOTES_INSTRUCTIONS = (
    "Keep app_id notes-fixture. Actions: add_note (input title, saves one note dated today, "
    "usable from the screen and manually) and count_notes (no input, returns count). The screen "
    "has a quick entry labelled 'Note' and a table of the latest notes."
)

CONTRADICTORY_PLAN: dict[str, Any] = {
    "scenarios": [
        {
            "id": "one_note_two_titles",
            "description": "Adding one note stores exactly one note whose title is both "
            "'Buy milk' and 'BUY MILK' (contradictory on purpose)",
            "steps": [
                {
                    "kind": "invoke",
                    "id": "add",
                    "action": "add_note",
                    "input": {"title": "Buy milk"},
                },
                {
                    "kind": "records",
                    "id": "stored",
                    "collection": "notes",
                    "count": 1,
                    "includes": [{"title": "Buy milk"}, {"title": "BUY MILK"}],
                },
            ],
        }
    ]
}

READING_GOAL = (
    "Help me keep a reading list: I add a book by its title, and I can see the books I have "
    "added, newest first. I also want to mark a book as finished."
)
READING_PLAN: dict[str, Any] = {
    "scenarios": [
        {
            "id": "add_and_finish",
            "description": "A book is added as unfinished and can then be marked finished",
            "steps": [
                {
                    "kind": "invoke",
                    "id": "add",
                    "action": "add_book",
                    "input": {"title": "The Left Hand of Darkness"},
                    "output": {},
                },
                {
                    "kind": "records",
                    "id": "added",
                    "collection": "books",
                    "count": 1,
                    "includes": [{"title": "The Left Hand of Darkness", "finished": False}],
                },
                {
                    "kind": "invoke",
                    "id": "finish",
                    "action": "finish_book",
                    "input": {"id": {"$ref": "add.output.id"}},
                },
                {
                    "kind": "records",
                    "id": "finished",
                    "collection": "books",
                    "count": 1,
                    "includes": [{"title": "The Left Hand of Darkness", "finished": True}],
                },
            ],
        },
        {
            "id": "blank_title_refused",
            "description": "A book without a title is refused and nothing is stored",
            "steps": [
                {
                    "kind": "invoke",
                    "id": "blank",
                    "action": "add_book",
                    "input": {"title": ""},
                    "expect": "failed",
                },
                {"kind": "records", "id": "none", "collection": "books", "count": 0},
            ],
        },
    ],
    "ui": {
        "primary": [
            {"kind": "fill", "label": "Title", "text": "Piranesi"},
            {"kind": "press", "key": "Enter"},
        ],
        "saved": {
            "kind": "records",
            "id": "saved",
            "collection": "books",
            "includes": [{"title": "Piranesi"}],
        },
        "shows": ["Piranesi"],
        "seed": [
            {
                "kind": "invoke",
                "id": "seed_book",
                "action": "add_book",
                "input": {"title": "A Memory Called Empire"},
            }
        ],
        "seed_shows": ["A Memory Called Empire"],
    },
}
READING_INSTRUCTIONS = (
    "Collection books with fields title (text, required) and finished (boolean, required). "
    "Actions: add_book (input title; stores finished=false; returns id and revision; usable from "
    "the screen and manually) and finish_book (input id; sets finished=true; usable from the "
    "screen and manually). The screen has a quick entry labelled 'Title' and a list of books, "
    "newest first."
)

SCENARIOS: dict[str, dict[str, Any]] = {
    "repair": {
        "goal": NOTES_GOAL,
        "instructions": NOTES_INSTRUCTIONS,
        "plan": NOTES_PLAN,
        "seed": "fake_persistence",
    },
    "limit": {
        "goal": NOTES_GOAL,
        "instructions": NOTES_INSTRUCTIONS,
        "plan": CONTRADICTORY_PLAN,
        "seed": "notes_ok",
    },
    "generate": {
        "goal": READING_GOAL,
        "instructions": READING_INSTRUCTIONS,
        "plan": READING_PLAN,
        "seed": None,
    },
}


def publish_profiles(root: Path) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "build_app_profile.py"), "--root", str(root)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(f"runtime profile build failed: {result.stderr[-2000:]}")
    runtime = json.loads(result.stdout.strip().splitlines()[-1])
    return {"runtime": runtime, "ui": build_ui_profile(root)}


def start_core(
    data_dir: Path, token: str, log_path: Path, profiles: Path, seeds: Path
) -> tuple[subprocess.Popen[str], int]:
    browser = validator_browser()
    if browser is None:
        raise SystemExit("the pinned headless browser is not installed")
    env = {
        "ALPHA_DATA_DIR": str(data_dir),
        "ALPHA_SESSION_TOKEN": token,
        "ALPHA_ALLOWED_ORIGINS": "http://localhost:1420",
        "ALPHA_ENABLED_MODEL_ROUTES": "claude-code-cli,fake",
        "ALPHA_APP_MODEL_ROUTE": "fake",
        "ALPHA_BUILDER_PATH": (
            "/opt/homebrew/bin:/opt/homebrew/opt/node@24/bin:/usr/local/bin:/usr/bin:/bin"
        ),
        "ALPHA_BUILDER_HOME": os.environ["HOME"],
        "ALPHA_PROFILES_DIR": str(profiles),
        "ALPHA_PLATFORM_RESOURCES": str(REPO_ROOT),
        "ALPHA_NODE": str(node()),
        "ALPHA_UI_BROWSER": str(browser),
        "ALPHA_DEV_SEED_PACKAGES_DIR": str(seeds),
        "ALPHA_TIMEZONE": "Asia/Kolkata",
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


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def collect_attempts(data_dir: Path, build: dict[str, Any], out_dir: Path) -> list[dict[str, Any]]:
    attempts = []
    for attempt in build["attempts"]:
        workspace = data_dir / "builds" / attempt["workspace_ref"]
        entry = {
            "attempt": attempt,
            "report": read_json(workspace / "verification.report.json"),
            "repair_request": (workspace / "REPAIR.md").read_text(encoding="utf-8")
            if (workspace / "REPAIR.md").is_file()
            else None,
            "package": {
                p.relative_to(workspace / "package").as_posix(): p.read_text(errors="replace")
                for p in sorted((workspace / "package").rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts
            },
        }
        shots = workspace / "evidence" / "ui"
        if shots.is_dir():
            target = out_dir / "screenshots" / f"attempt-{attempt['number']}"
            shutil.copytree(shots, target)
            entry["screenshots"] = sorted(p.name for p in target.iterdir())
        attempts.append(entry)
    return attempts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--timeout", type=float, default=2400.0)
    args = parser.parse_args()
    spec = copy.deepcopy(SCENARIOS[args.scenario])
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = EVIDENCE / f"F07-live-{args.scenario}-{stamp}"
    out_dir.mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="alpha-f07-live-"))
    data_dir = work / "data"
    data_dir.mkdir()
    profiles = work / "profiles"
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=REPO_ROOT
    ).stdout.strip()
    published = publish_profiles(profiles)
    seeds = render_packages(work / "seeds")
    token = secrets.token_hex(32)
    core, port = start_core(data_dir, token, out_dir / "core.stderr.log", profiles, seeds)
    client = httpx.Client(
        base_url=f"http://127.0.0.1:{port}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    record: dict[str, Any] = {
        "scenario": args.scenario,
        "commit": commit,
        "worktree_clean": not dirty,
        "started_at": stamp,
        "profiles": published,
        "spec": spec,
        "work_dir": str(work),
    }
    try:
        submission = {
            "goal": spec["goal"],
            "instructions": spec["instructions"],
            "validation_plan": spec["plan"],
            "route_id": "claude-code-cli",
        }
        if spec["seed"]:
            submission["seed_package"] = spec["seed"]
        response = client.post("/api/builds", json=submission)
        response.raise_for_status()
        build_id = response.json()["build_id"]
        print(f"build {build_id} ({args.scenario}) on claude-code-cli; following…", flush=True)
        seen = 0
        started = time.monotonic()
        build: dict[str, Any] = {}
        while time.monotonic() - started < args.timeout:
            for event in client.get(
                f"/api/builds/{build_id}/events", params={"after": seen}
            ).json()["events"]:
                seen = event["sequence"]
                if not event["kind"].startswith(
                    ("harness.harness.tool_result", "harness.harness.message")
                ):
                    payload = json.dumps(event["payload"])[:150]
                    print(f"  [{seen:>4}] {event['kind']}: {payload}", flush=True)
            build = client.get(f"/api/builds/{build_id}").json()
            if build["state"] in ("ready", "failed", "cancelled"):
                break
            time.sleep(2.0)
        record["elapsed_seconds"] = round(time.monotonic() - started, 1)
        record["build"] = build
        record["events"] = client.get(f"/api/builds/{build_id}/events").json()["events"]
        record["attempts"] = collect_attempts(data_dir, build, out_dir)
        record["dependency_requests"] = client.get(
            "/api/dependency-requests", params={"build_id": build_id}
        ).json()["requests"]
        if build.get("state") == "ready":
            record["preview_invoke"] = client.post(
                f"/api/builds/{build_id}/invoke",
                json={
                    "action_id": "count_notes" if args.scenario != "generate" else "add_book",
                    "input": {} if args.scenario != "generate" else {"title": "Held-out title"},
                },
            ).json()
        print(
            f"finished: state={build.get('state')} reason={build.get('terminal_reason')} "
            f"attempts={len(build.get('attempts', []))} in {record['elapsed_seconds']:.0f}s"
        )
    finally:
        core.terminate()
        core.wait(timeout=30)
        client.close()
    shutil.copyfile(data_dir / "control.sqlite", out_dir / "control.sqlite")
    text = json.dumps(record, default=str) + (out_dir / "core.stderr.log").read_text()
    needles = ("sk-ant-", "Bearer ", "oauth", "access_token", token)
    record["secret_scan"] = {
        "needles": [n if n != token else "<session token>" for n in needles],
        "found": [n if n != token else "<session token>" for n in needles if n in text],
    }
    (out_dir / "record.json").write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )
    print(f"evidence written to {out_dir}")
    print(f"secret scan: {record['secret_scan']['found'] or 'nothing found'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
