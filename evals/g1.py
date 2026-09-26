"""G1 (M1 exit): requests through actual generation and primary use on frozen platform code.

Drives a real Core exactly as the desktop shell does (same HTTP routes, same environment the
native host gives Core) on a dedicated G1 data directory, so the founder can then open the same
results in the Alpha window. Every step is recorded; nothing here edits generated source.

  create  one request: conversation -> clarification -> brief -> creation (plan, live build,
          checks, activation). Questions are answered with the product's own "use sensible
          defaults" unless an answers file is given (recorded either way).
  use     primary use: through the App's own screen (evals/g1_screen.mjs, headless, the same
          bridge host and grant as the shell) or, without a screen, through its actions the way
          the shell's actions view runs them. The journey file is written after looking at the
          result, like a person would; it is recorded with the outcome.
  reopen  a fresh Core on the same data: every G1 App, Version and record is still there and
          still works; screens are opened again.
  share   F08.C04 on generated results: two Apps on one runtime profile, a run in one cancelled
          (or failed) while the other runs; data, scratch and processes are compared.

Usage (from the frozen checkout):
  uv run python evals/g1.py --g1-dir DIR create --label calorie --request "..."
  uv run python evals/g1.py --g1-dir DIR use --label calorie --journey FILE
  uv run python evals/g1.py --g1-dir DIR reopen
  uv run python evals/g1.py --g1-dir DIR share --a calorie --b review --slow FILE
Add --fake to exercise the script itself on the deterministic control routes.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
NODE = Path("/opt/homebrew/opt/node@24/bin/node")
BUILDER_PATH = "/opt/homebrew/bin:/opt/homebrew/opt/node@24/bin:/usr/local/bin:/usr/bin:/bin"
DONE = {"active", "failed", "cancelled"}
RUN_DONE = {"succeeded", "failed", "cancelled", "interrupted"}


def now() -> str:
    return datetime.now(UTC).isoformat()


def browser() -> Path | None:
    browsers = json.loads(
        (REPO_ROOT / "workers/validator/node_modules/playwright-core/browsers.json").read_text()
    )
    revision = next(
        b["revision"] for b in browsers["browsers"] if b["name"] == "chromium-headless-shell"
    )
    exe = (
        Path.home()
        / "Library/Caches/ms-playwright"
        / f"chromium_headless_shell-{revision}"
        / "chrome-headless-shell-mac-arm64"
        / "chrome-headless-shell"
    )
    return exe if exe.is_file() else None


class G1:
    def __init__(self, args: argparse.Namespace) -> None:
        self.dir: Path = args.g1_dir.resolve()
        self.data: Path = self.dir / "data"
        self.records: Path = self.dir / "record"
        self.runtime: Path = (args.runtime or REPO_ROOT / ".alpha-runtime").resolve()
        self.fake: bool = args.fake
        self.data.mkdir(parents=True, exist_ok=True)
        self.records.mkdir(parents=True, exist_ok=True)
        self.token = secrets.token_hex(32)
        self.base = ""
        self.process: subprocess.Popen[str] | None = None

    # ----- Core, started the way the native host starts it ---------------------------------

    def env(self) -> dict[str, str]:
        env = {
            "ALPHA_ENABLED_MODEL_ROUTES": "fake" if self.fake else "fake,claude-code-cli",
            "ALPHA_BUILDER_PATH": BUILDER_PATH,
            "ALPHA_BUILDER_HOME": os.environ["HOME"],
            "ALPHA_DATA_DIR": str(self.data),
            "ALPHA_PROFILES_DIR": str(self.runtime / "profiles"),
            "ALPHA_PLATFORM_RESOURCES": str(REPO_ROOT),
            "ALPHA_SESSION_TOKEN": self.token,
            "ALPHA_ALLOWED_ORIGINS": "http://localhost:1420,tauri://localhost",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "LC_ALL": "C.UTF-8",
        }
        if NODE.is_file():
            env["ALPHA_NODE"] = str(NODE)
        found = browser()
        if found is not None:
            env["ALPHA_UI_BROWSER"] = str(found)
        if self.fake:
            from tests.integration.build_harness import render_packages

            packages = self.dir / "fake-packages"
            if not packages.exists():
                render_packages(packages)
            env["ALPHA_FAKE_BUILDER_PACKAGES"] = str(packages)
        return env

    @contextmanager
    def core(self) -> Iterator[httpx.Client]:
        manifest = json.loads((self.runtime / "core-runtime.json").read_text())
        python = self.runtime / manifest["python"]
        log = (self.dir / "core.log").open("a", encoding="utf-8")
        log.write(f"\n===== core start {now()} =====\n")
        log.flush()
        self.process = subprocess.Popen(
            [str(python), "-I", "-m", "alpha.main"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=log,
            env=self.env(),
            text=True,
            cwd=str(self.dir),
        )
        assert self.process.stdout is not None
        port = None
        for line in self.process.stdout:
            if line.startswith("ALPHA_CORE_READY "):
                port = int(json.loads(line[len("ALPHA_CORE_READY ") :])["port"])
                break
            if line.startswith("ALPHA_CORE_ERROR "):
                raise SystemExit(line)
        if port is None:
            raise SystemExit("core did not start; see core.log")
        stdout = self.process.stdout
        threading.Thread(target=lambda: [None for _ in stdout], daemon=True).start()
        self.base = f"http://127.0.0.1:{port}"
        client = httpx.Client(
            base_url=self.base, headers={"Authorization": f"Bearer {self.token}"}, timeout=60
        )
        try:
            yield client
        finally:
            client.close()
            self.process.terminate()
            try:
                self.process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self.process.kill()
            log.close()

    # ----- helpers --------------------------------------------------------------------------

    def record_dir(self, label: str) -> Path:
        path = self.records / label
        path.mkdir(parents=True, exist_ok=True)
        return path

    def load(self, label: str, name: str = "create.json") -> dict[str, Any]:
        data: dict[str, Any] = json.loads((self.record_dir(label) / name).read_text())
        return data

    def save(self, label: str, name: str, data: Any) -> Path:
        path = self.record_dir(label) / name
        path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False) + "\n")
        return path

    def sql(self, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = sqlite3.connect(f"file:{self.data / 'control.sqlite'}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(r) for r in conn.execute(query, params).fetchall()]
        finally:
            conn.close()


def wait_conversation(client: httpx.Client, cid: str, timeout: float = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        conv: dict[str, Any] = client.get(f"/api/conversations/{cid}").json()
        if conv["state"] != "thinking" or time.monotonic() > deadline:
            return conv
        time.sleep(1)


def wait_run(client: httpx.Client, run_id: str, timeout: float = 600) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        run: dict[str, Any] = client.get(f"/api/runs/{run_id}").json()
        if run["state"] in RUN_DONE or time.monotonic() > deadline:
            return run
        time.sleep(0.5)


def run_action(
    client: httpx.Client, app_id: str, action: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    """As the shell's actions view runs it: origin user when a person may run it by hand."""
    origin = "user" if "manual" in action["invocable_from"] else "ui"
    started = time.monotonic()
    response = client.post(
        f"/api/apps/{app_id}/actions/{action['id']}/runs",
        json={"input": payload, "origin": origin},
    )
    if response.status_code != 202:
        return {"accepted": False, "status": response.status_code, "detail": response.json()}
    run = wait_run(client, response.json()["run_id"])
    events = client.get(f"/api/runs/{run['run_id']}/events").json()["events"]
    return {
        "accepted": True,
        "origin": origin,
        "run_id": run["run_id"],
        "state": run["state"],
        "output": run.get("output"),
        "terminal_reason": run.get("terminal_reason"),
        "errors": [e["payload"] for e in events if e["kind"] in ("worker.error", "run.failed")],
        "seconds": round(time.monotonic() - started, 2),
    }


def all_records(client: httpx.Client, app_id: str, collections: list[str]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for name in collections:
        page = client.post(
            f"/api/apps/{app_id}/records/query", json={"collection": name, "limit": 200}
        ).json()
        found[name] = [
            {"id": r["id"], "revision": r["revision"], "values": r["values"]}
            for r in page.get("records", [])
        ]
    return found


# ----- create ---------------------------------------------------------------------------------


def cmd_create(g1: G1, args: argparse.Namespace) -> int:
    record: dict[str, Any] = {
        "label": args.label,
        "request": args.request,
        "requested_at": now(),
        "platform_commit": git_head(),
        "runtime": json.loads((g1.runtime / "core-runtime.json").read_text()),
        "routes": "fake (control only)" if g1.fake else "claude-code-cli",
    }
    answers_file = json.loads(Path(args.answers).read_text()) if args.answers else None
    timeline: list[dict[str, Any]] = []
    with g1.core() as client:
        t0 = time.monotonic()
        conv = client.post("/api/conversations", json={"text": args.request}).json()
        cid = conv["conversation_id"]
        conv = wait_conversation(client, cid)
        timeline.append({"at": now(), "s": round(time.monotonic() - t0, 1), "state": conv["state"]})
        rounds = 0
        while conv["state"] == "waiting_for_user" and rounds < 3:
            rounds += 1
            questions = conv["questions"]
            if answers_file and str(rounds) in answers_file:
                reply = {"answers": answers_file[str(rounds)]}
            else:
                reply = {"use_defaults": True}
            timeline.append({"at": now(), "questions": questions, "reply": reply})
            client.post(f"/api/conversations/{cid}/messages", json=reply).raise_for_status()
            conv = wait_conversation(client, cid)
            timeline.append(
                {"at": now(), "s": round(time.monotonic() - t0, 1), "state": conv["state"]}
            )
        record["conversation"] = conv
        record["briefed_seconds"] = round(time.monotonic() - t0, 1)
        if conv["state"] != "briefed" or conv.get("delivery") != "app":
            record["outcome"] = f"not briefed as an App ({conv['state']}, {conv.get('delivery')})"
            g1.save(args.label, "create.json", record | {"timeline": timeline})
            print(record["outcome"])
            return 1
        body: dict[str, Any] = {}
        if g1.fake and args.builder_hint:
            body["builder_hint"] = args.builder_hint
        started = client.post(f"/api/conversations/{cid}/creations", json=body)
        started.raise_for_status()
        creation = started.json()
        t1 = time.monotonic()
        seen: tuple[str, str] | None = None
        while creation["state"] not in DONE:
            time.sleep(2)
            creation = client.get(f"/api/creations/{creation['creation_id']}").json()
            if (creation["stage"], creation["label"]) != seen:
                seen = (creation["stage"], creation["label"])
                line = f"{time.monotonic() - t1:7.0f}s  {creation['label']}"
                if creation.get("progress"):
                    line += f"  {creation['progress']}"
                print(line, flush=True)
        record["creation"] = creation
        record["creation_seconds"] = round(time.monotonic() - t1, 1)
        record["total_seconds"] = round(time.monotonic() - t0, 1)
        if creation.get("build_id"):
            build = client.get(f"/api/builds/{creation['build_id']}").json()
            record["build"] = build
            record["build_events"] = client.get(f"/api/builds/{build['build_id']}/events").json()[
                "events"
            ]
        if creation["state"] == "active":
            app_id = creation["app_id"]
            record["app"] = client.get(f"/api/apps/{app_id}").json()
    record["timeline"] = timeline
    record |= collect_store(g1, record)
    record["outcome"] = record["creation"]["state"]
    g1.save(args.label, "create.json", record)
    if record.get("build"):
        copy_attempts(g1, args.label, record["build"])
    print(json.dumps(summary_of(record), indent=2))
    return 0 if record["outcome"] == "active" else 1


def collect_store(g1: G1, record: dict[str, Any]) -> dict[str, Any]:
    creation = record["creation"]
    cid = creation["conversation_id"]
    extra: dict[str, Any] = {
        "turns": g1.sql(
            "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY sequence", (cid,)
        ),
        "briefs": g1.sql(
            "SELECT * FROM briefs WHERE conversation_id = ? ORDER BY revision", (cid,)
        ),
        "plan": json.loads(
            g1.sql(
                "SELECT plan_json FROM creations WHERE creation_id = ?",
                (creation["creation_id"],),
            )[0]["plan_json"]
            or "null"
        ),
    }
    refs = [cid, creation["creation_id"]] + ([creation["build_id"]] if creation["build_id"] else [])
    usage = g1.sql(
        f"SELECT * FROM model_usage WHERE scope_ref IN ({','.join('?' * len(refs))})"
        " ORDER BY recorded_at",
        tuple(refs),
    )
    if creation.get("build_id"):
        usage += g1.sql(
            "SELECT * FROM model_usage WHERE scope_ref LIKE ? ORDER BY recorded_at",
            (f"{creation['build_id']}%",),
        )
    unique: dict[str, dict[str, Any]] = {u["usage_id"]: u for u in usage}
    extra["model_usage"] = list(unique.values())
    extra["cost_usd_estimate"] = round(sum(u["cost_usd"] or 0 for u in extra["model_usage"]), 4)
    return extra


def copy_attempts(g1: G1, label: str, build: dict[str, Any]) -> None:
    out = g1.record_dir(label) / "attempts"
    for attempt in build["attempts"]:
        workspace = g1.data / "builds" / attempt["workspace_ref"]
        target = out / f"attempt-{attempt['number']}"
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True)
        for name in ("verification.report.json", "REPAIR.md", "BUILD.md", "CHECKS.md"):
            if (workspace / name).is_file():
                shutil.copy2(workspace / name, target / name)
        if (workspace / "package").is_dir():
            shutil.copytree(
                workspace / "package",
                target / "package",
                ignore=shutil.ignore_patterns("__pycache__", "node_modules", "dist"),
            )
        if (workspace / "evidence" / "ui").is_dir():
            shutil.copytree(workspace / "evidence" / "ui", target / "screenshots")


def summary_of(record: dict[str, Any]) -> dict[str, Any]:
    creation = record.get("creation") or {}
    build = record.get("build") or {}
    return {
        "label": record["label"],
        "outcome": record.get("outcome"),
        "app_id": creation.get("app_id"),
        "has_ui": (creation.get("result") or {}).get("has_ui"),
        "attempts": len(build.get("attempts", [])),
        "checks_passed": (creation.get("result") or {}).get("checks_passed"),
        "package_sha256": (build.get("candidate") or {}).get("package_sha256"),
        "briefed_seconds": record.get("briefed_seconds"),
        "creation_seconds": record.get("creation_seconds"),
        "cost_usd_estimate": record.get("cost_usd_estimate"),
        "failure": creation.get("failure"),
    }


def git_head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=REPO_ROOT, check=False
    ).stdout.strip()


# ----- use ------------------------------------------------------------------------------------


def screen_job(g1: G1, detail: dict[str, Any], steps: list[Any], name: str) -> dict[str, Any]:
    version = g1.data / "versions" / detail["version_id"]
    manifest = json.loads((version / "dependency.manifest.json").read_text())
    ui_profile = g1.runtime / "profiles" / manifest["ui_build"]["profile_id"]
    assert ui_profile.is_dir(), f"UI build profile {ui_profile.name} is not installed"
    found = browser()
    assert found is not None, "the pinned headless browser is not installed"
    return {
        "core_url": g1.base,
        "token": g1.token,
        "app_id": detail["app_id"],
        "release_id": detail["release_id"],
        "dist_dir": str(version / "dist" / "ui"),
        "bridge_dir": str(ui_profile / "node_modules" / "@alpha" / "ui-bridge" / "dist"),
        "browser": str(found),
        "timezone": "Asia/Kolkata",
        "grant": {
            "actions": list(detail["ui"]["actions"]),
            "read_views": [v["id"] for v in detail["ui"]["views"]],
        },
        "steps": steps,
        "widths": [1280, 768],
        "evidence_dir": str(g1.records / "screens"),
        "name": name,
    }


def drive_screen(g1: G1, job: dict[str, Any], label: str) -> dict[str, Any]:
    path = g1.record_dir(label) / f"{job['name']}.job.json"
    path.write_text(json.dumps(job | {"token": "<redacted>"}, indent=2))
    live = g1.dir / "tmp-job.json"
    live.write_text(json.dumps(job))
    try:
        proc = subprocess.run(
            [str(NODE), str(REPO_ROOT / "evals" / "g1_screen.mjs"), str(live)],
            capture_output=True,
            text=True,
            timeout=900,
            check=False,
        )
    finally:
        live.unlink(missing_ok=True)
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.startswith("{")]
    result = next((line for line in reversed(lines) if line.get("kind") == "result"), None)
    if result is None:
        return {"ok": False, "error": proc.stderr[-3000:]}
    for step in lines:
        if step.get("kind") == "step":
            what = step["step"].get("label") or step["step"].get("key") or step["step"].get("text")
            print(
                f"  step {step['index'] + 1} {step['step']['kind']} {what}: ok={step['ok']}"
                f" {step.get('error', '')}"
            )
    found: dict[str, Any] = result
    return found


def cmd_use(g1: G1, args: argparse.Namespace) -> int:
    created = g1.load(args.label)
    app_id = created["creation"]["app_id"]
    journey = json.loads(Path(args.journey).read_text())
    record: dict[str, Any] = {"label": args.label, "app_id": app_id, "journey": journey}
    record["started_at"] = now()
    with g1.core() as client:
        detail = client.get(f"/api/apps/{app_id}").json()
        collections = [c["name"] for c in detail["collections"]]
        record["before"] = all_records(client, app_id, collections)
        if journey.get("screen"):
            assert detail.get("ui"), "this App has no screen"
            result = drive_screen(
                g1, screen_job(g1, detail, journey["screen"], f"{args.label}-use"), args.label
            )
            record["screen"] = result
        actions = {a["id"]: a for a in detail["actions"]}
        record["actions"] = []
        for call in journey.get("actions", []):
            before = all_records(client, app_id, collections)
            outcome = run_action(client, app_id, actions[call["action"]], call["input"])
            after = all_records(client, app_id, collections)
            verdict = call_verdict(call, outcome, before, after)
            record["actions"].append({"call": call, "outcome": outcome, "verdict": verdict})
            print(
                f"  {call['action']}: {verdict['state']} ok={verdict['ok']} {verdict['problems']}"
            )
        record["after"] = all_records(client, app_id, collections)
        record["runs"] = [
            {k: r.get(k) for k in ("run_id", "state", "origin", "terminal_reason", "created_at")}
            for r in client.get("/api/runs").json()["runs"]
            if (r.get("owner") or {}).get("app_id") == app_id
        ]
    record["finished_at"] = now()
    ok = (not journey.get("screen") or record["screen"].get("ok")) and all(
        a["verdict"]["ok"] for a in record["actions"]
    )
    record["ok"] = bool(ok)
    g1.save(args.label, "use.json", record)
    print(json.dumps({"ok": record["ok"], "after": record["after"]}, indent=2)[:4000])
    return 0 if ok else 1


def call_verdict(
    call: dict[str, Any],
    outcome: dict[str, Any],
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, Any]:
    """Whether one journey call ended the way it was meant to. M1 review finding F05: the old
    verdict passed any call marked as an expected refusal, even one that succeeded and wrote
    data. An expected refusal must end failed (or be refused before running), say what the call
    expects when `expect_message` is given, and change no stored data."""
    state = "refused" if outcome.get("accepted") is False else outcome.get("state")
    problems: list[str] = []
    if call.get("expect") == "failed":
        if state not in ("failed", "refused"):
            problems.append(f"expected a refusal but it ended {state}")
        wanted = call.get("expect_message")
        said = json.dumps([outcome.get("errors"), outcome.get("detail")], default=str)
        if wanted and wanted.lower() not in said.lower():
            problems.append(f"the refusal did not say {wanted!r}")
        if before != after:
            problems.append("the refused call changed stored data")
        return {"ok": not problems, "expected": "failed", "state": state, "problems": problems}
    if state != "succeeded":
        problems.append(f"expected success but it ended {state}")
    return {"ok": not problems, "expected": "succeeded", "state": state, "problems": problems}


# ----- record (after a session in the Alpha window) --------------------------------------------


def native_record(data: Path, conversation_id: str) -> dict[str, Any]:
    """Everything the stores hold about one request made and used in the Alpha window: the
    conversation, its briefs and creations, builds and attempts, the App, its releases, runs and
    records, and the model usage of every step. Read-only; run it with Alpha quit."""
    conn = sqlite3.connect(f"file:{data / 'control.sqlite'}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    def rows(query: str, *params: Any) -> list[dict[str, Any]]:
        return [dict(r) for r in conn.execute(query, params).fetchall()]

    def usage(ref: str) -> list[dict[str, Any]]:
        return rows("SELECT * FROM model_usage WHERE scope_ref = ? ORDER BY recorded_at", ref)

    try:
        cid = conversation_id
        record: dict[str, Any] = {
            "conversation": rows("SELECT * FROM conversations WHERE conversation_id = ?", cid),
            "turns": rows(
                "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY sequence",
                cid,
            ),
            "briefs": rows("SELECT * FROM briefs WHERE conversation_id = ? ORDER BY revision", cid),
            "creations": rows(
                "SELECT * FROM creations WHERE conversation_id = ? ORDER BY created_at", cid
            ),
            "builds": [],
            "apps": [],
            "model_usage": usage(cid),
        }
        for creation in record["creations"]:
            record["model_usage"] += usage(creation["creation_id"])
            if creation["build_id"]:
                attempts = rows(
                    "SELECT * FROM build_attempts WHERE build_id = ? ORDER BY number",
                    creation["build_id"],
                )
                for attempt in attempts:
                    record["model_usage"] += usage(attempt["attempt_id"])
                record["builds"].append(
                    {
                        "build": rows(
                            "SELECT * FROM builds WHERE build_id = ?", creation["build_id"]
                        ),
                        "attempts": attempts,
                        "events": rows(
                            "SELECT kind, attempt_id, occurred_at, payload_json FROM build_events"
                            " WHERE build_id = ? ORDER BY sequence",
                            creation["build_id"],
                        ),
                    }
                )
            if creation["app_id"]:
                app_id = creation["app_id"]
                runs = rows(
                    "SELECT run_id, origin, state, input_json, output_json, terminal_reason,"
                    " created_at, finished_at FROM runs WHERE json_extract(owner_json, '$.app_id')"
                    " = ? ORDER BY created_at",
                    app_id,
                )
                for run in runs:
                    record["model_usage"] += usage(run["run_id"])
                record["apps"].append(
                    {
                        "app": rows("SELECT * FROM apps WHERE app_id = ?", app_id),
                        "versions": rows(
                            "SELECT version_id, package_sha256, runtime_profile_id, created_at"
                            " FROM app_versions WHERE app_id = ? ORDER BY created_at",
                            app_id,
                        ),
                        "releases": rows(
                            "SELECT * FROM app_releases WHERE app_id = ? ORDER BY created_at",
                            app_id,
                        ),
                        "runs": runs,
                        "records": app_records(data / "apps" / app_id / "records.sqlite"),
                    }
                )
    finally:
        conn.close()
    record["cost_usd_estimate"] = round(
        sum((u["cost_usd"] or 0.0 for u in record["model_usage"]), 0.0), 4
    )
    return record


def app_records(store: Path) -> list[dict[str, Any]]:
    if not store.is_file():
        return []
    conn = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [
            {**dict(r), "values": json.loads(r["values_json"])}
            for r in conn.execute("SELECT * FROM records ORDER BY collection, created_at")
        ]
    finally:
        conn.close()


def cmd_record(g1: G1, args: argparse.Namespace) -> int:
    record = native_record(g1.data, args.conversation)
    record |= {"label": args.label, "recorded_at": now(), "platform_commit": git_head()}
    for build in record["builds"]:
        copy_attempts(g1, args.label, {"attempts": build["attempts"]})
    g1.save(args.label, "native.json", record)
    summary = {
        "label": args.label,
        "creations": [(c["state"], c["app_id"]) for c in record["creations"]],
        "records": {a["app"][0]["app_id"]: len(a["records"]) for a in record["apps"]},
        "cost_usd_estimate": record["cost_usd_estimate"],
    }
    print(json.dumps(summary, indent=2))
    return 0


# ----- reopen ---------------------------------------------------------------------------------


def cmd_reopen(g1: G1, args: argparse.Namespace) -> int:
    labels = sorted(p.name for p in g1.records.iterdir() if (p / "create.json").is_file())
    report: dict[str, Any] = {"reopened_at": now(), "apps": {}}
    ok = True
    with g1.core() as client:
        listed = {a["app_id"]: a for a in client.get("/api/apps").json()["apps"]}
        for label in labels:
            created = g1.load(label)
            if created.get("outcome") != "active":
                continue
            app_id = created["creation"]["app_id"]
            detail = client.get(f"/api/apps/{app_id}").json()
            same = all(
                detail.get(k) == created["app"].get(k)
                for k in ("app_id", "version_id", "release_id", "package_sha256")
            )
            collections = [c["name"] for c in detail["collections"]]
            data = all_records(client, app_id, collections)
            used = g1.record_dir(label) / "use.json"
            expected = json.loads(used.read_text())["after"] if used.is_file() else None
            entry: dict[str, Any] = {
                "listed": app_id in listed,
                "identity_unchanged": same,
                "records": data,
                "records_unchanged": expected is None or data == expected,
            }
            if detail.get("ui"):
                entry["screen"] = drive_screen(
                    g1, screen_job(g1, detail, [], f"{label}-reopen"), label
                )
            reuse = (
                json.loads(used.read_text())["journey"].get("reopen_action")
                if used.is_file()
                else None
            )
            if reuse:
                actions = {a["id"]: a for a in detail["actions"]}
                entry["action_after_reopen"] = run_action(
                    client, app_id, actions[reuse["action"]], reuse["input"]
                )
            ok &= entry["listed"] and same and entry["records_unchanged"]
            report["apps"][label] = entry
            print(
                f"{label}: listed={entry['listed']} same={same} data={entry['records_unchanged']}"
            )
    report["ok"] = ok
    (g1.records / "reopen.json").write_text(json.dumps(report, indent=2, default=str))
    return 0 if ok else 1


# ----- share (F08.C04) ------------------------------------------------------------------------


def worker_facts(pid: int) -> dict[str, Any]:
    def run(argv: list[str]) -> str:
        return subprocess.run(argv, capture_output=True, text=True, check=False).stdout

    cwd = next(
        (
            line[1:]
            for line in run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"]).splitlines()
            if line.startswith("n")
        ),
        None,
    )
    return {
        "pid": pid,
        "cwd": cwd,
        "command": run(["ps", "-o", "command=", "-p", str(pid)]).strip(),
    }


def cmd_share(g1: G1, args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.slow).read_text())
    a, b = g1.load(args.a)["creation"]["app_id"], g1.load(args.b)["creation"]["app_id"]
    report: dict[str, Any] = {"apps": {"a": a, "b": b}, "plan": plan, "at": now()}
    with g1.core() as client:
        detail_a = client.get(f"/api/apps/{a}").json()
        detail_b = client.get(f"/api/apps/{b}").json()
        report["runtime_profiles"] = [
            detail_a["runtime_profile_id"],
            detail_b["runtime_profile_id"],
        ]
        cols_a = [c["name"] for c in detail_a["collections"]]
        cols_b = [c["name"] for c in detail_b["collections"]]
        report["before"] = {
            "a": all_records(client, a, cols_a),
            "b": all_records(client, b, cols_b),
        }
        slow = client.post(
            f"/api/apps/{a}/actions/{plan['a']['action']}/runs",
            json={"input": plan["a"]["input"], "origin": "user"},
        ).json()
        other = client.post(
            f"/api/apps/{b}/actions/{plan['b']['action']}/runs",
            json={"input": plan["b"]["input"], "origin": "user"},
        ).json()
        workers: dict[str, Any] = {}
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline and len(workers) < 2:
            for key, run in (("a", slow), ("b", other)):
                if key in workers:
                    continue
                for lease in g1.sql(
                    "SELECT * FROM worker_leases WHERE run_id = ?", (run["run_id"],)
                ):
                    pid = lease.get("pid") or lease.get("worker_pid")
                    if pid:
                        workers[key] = worker_facts(int(pid)) | {"lease": lease}
            time.sleep(0.2)
        report["workers_while_running"] = workers
        time.sleep(plan.get("cancel_after_seconds", 2))
        report["a_state_before_cancel"] = client.get(f"/api/runs/{slow['run_id']}").json()["state"]
        cancelled = client.post(f"/api/runs/{slow['run_id']}/cancel")
        report["cancel_response"] = cancelled.status_code
        report["a_run"] = wait_run(client, slow["run_id"])
        report["b_run"] = wait_run(client, other["run_id"])
        report["after"] = {"a": all_records(client, a, cols_a), "b": all_records(client, b, cols_b)}
        if "a_failure" in plan:
            actions = {x["id"]: x for x in detail_a["actions"]}
            report["a_failure"] = run_action(
                client, a, actions[plan["a_failure"]["action"]], plan["a_failure"]["input"]
            )
        actions_b = {x["id"]: x for x in detail_b["actions"]}
        report["b_after"] = run_action(
            client, b, actions_b[plan["b_after"]["action"]], plan["b_after"]["input"]
        )
        report["final"] = {"a": all_records(client, a, cols_a), "b": all_records(client, b, cols_b)}
        for key in ("a", "b"):
            pid = (workers.get(key) or {}).get("pid")
            if pid:
                workers[key]["alive_after"] = (
                    subprocess.run(
                        ["kill", "-0", str(pid)], capture_output=True, check=False
                    ).returncode
                    == 0
                )
    (g1.records / "share.json").write_text(json.dumps(report, indent=2, default=str))
    print(
        json.dumps({k: report[k] for k in ("runtime_profiles", "a_state_before_cancel")}, indent=2)
    )
    print("a:", report["a_run"]["state"], "b:", report["b_run"]["state"])
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--g1-dir", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, default=None)
    parser.add_argument("--fake", action="store_true", help="control routes (script self-test)")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--label", required=True)
    create.add_argument("--request", required=True)
    create.add_argument("--answers", default=None)
    create.add_argument("--builder-hint", default=None)
    use = sub.add_parser("use")
    use.add_argument("--label", required=True)
    use.add_argument("--journey", required=True)
    sub.add_parser("reopen")
    record = sub.add_parser("record")
    record.add_argument("--label", required=True)
    record.add_argument("--conversation", required=True)
    share = sub.add_parser("share")
    share.add_argument("--a", required=True)
    share.add_argument("--b", required=True)
    share.add_argument("--slow", required=True)
    args = parser.parse_args()
    g1 = G1(args)
    commands = {
        "create": cmd_create,
        "use": cmd_use,
        "reopen": cmd_reopen,
        "share": cmd_share,
        "record": cmd_record,
    }
    return commands[args.command](g1, args)


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    raise SystemExit(main())
