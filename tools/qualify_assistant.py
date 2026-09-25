"""Opt-in live assistant qualification (F04.C01).

Starts a real Core with the Claude Code CLI route, runs three request families through the
real model loop (a tracker, an artifact request, an unsupported-capability request), answers
the tracker's questions, and records routing, interpretation, questions, brief revisions,
assumption provenance and usage under docs/development/evidence/logs/. No generated source,
no App or Task records are created by a brief. Runs on the founder's subscription.
"""

from __future__ import annotations

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

REQUESTS = {
    "tracker": "Track what I eat and how much, with calories, history and trends.",
    "artifact": "Turn my meeting notes into a one-page brief I can send to my team.",
    "unsupported": (
        "Every morning, send my mom a WhatsApp message with today's weather for Ahmedabad."
    ),
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


def settle(client: httpx.Client, conversation_id: str, timeout: float = 300.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    while time.monotonic() < deadline:
        record: dict[str, Any] = client.get(f"/api/conversations/{conversation_id}").json()
        if record["state"] != "thinking":
            record["_elapsed_seconds"] = round(time.monotonic() - started, 1)
            return record
        time.sleep(1.0)
    raise SystemExit(f"conversation {conversation_id} did not settle")


LIMIT_PHRASES = ("can't", "cannot", "can not", "not connected", "isn't connected", "not available")


def states_limit(reply: str) -> bool:
    """True when the reply tells the user plainly that something is not possible today."""
    lowered = reply.lower()
    return any(phrase in lowered for phrase in LIMIT_PHRASES)


def summarize(record: dict[str, Any]) -> dict[str, Any]:
    brief = record.get("current_brief") or {}
    return {
        "state": record["state"],
        "delivery": record["delivery"],
        "elapsed_seconds": record.get("_elapsed_seconds"),
        "interpretation": record.get("interpretation"),
        "reply": record.get("reply"),
        "questions": record.get("questions"),
        "brief_revision": brief.get("revision"),
        "unavailable_capabilities": brief.get("unavailable_capabilities"),
        "assumptions": brief.get("assumptions"),
        "data_needs": [d.get("collection") for d in brief.get("data_needs", [])],
        "actions": [a.get("id") for a in brief.get("actions", [])],
        "error": record.get("error"),
    }


def recover(out_dir: Path) -> int:
    """Rebuild record.json for a run whose process ended before writing it. Everything needed
    (conversations, turns, briefs, usage) is in the run's own control store."""
    import sqlite3

    data_dir = out_dir / "data"
    conn = sqlite3.connect(data_dir / "control.sqlite")
    conn.row_factory = sqlite3.Row
    record: dict[str, Any] = {"recovered_from": str(data_dir), "requests": REQUESTS, "results": {}}
    verdicts: dict[str, bool] = {}
    convs = conn.execute("SELECT * FROM conversations ORDER BY created_at").fetchall()
    for row in convs:
        cid = row["conversation_id"]
        turns = [
            dict(t)
            for t in conn.execute(
                "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY sequence",
                (cid,),
            )
        ]
        for t in turns:
            t["content"] = json.loads(t.pop("content_json"))
        briefs = [
            json.loads(b["brief_json"])
            for b in conn.execute(
                "SELECT brief_json FROM briefs WHERE conversation_id = ? ORDER BY revision", (cid,)
            )
        ]
        request_text = turns[0]["content"].get("text", "")
        family = next((k for k, v in REQUESTS.items() if v == request_text), cid)
        assistant_turns = [t for t in turns if t["role"] == "assistant"]
        first_a = assistant_turns[0]["content"] if assistant_turns else {}
        last_a = assistant_turns[-1]["content"] if assistant_turns else {}
        entry = {
            "conversation_id": cid,
            "state": row["state"],
            "delivery": row["delivery"],
            "turns": turns,
            "briefs": briefs,
            "first_reply": first_a.get("reply"),
            "first_questions": first_a.get("questions"),
            "first_interpretation": first_a.get("interpretation"),
            "last_reply": last_a.get("reply"),
        }
        record["results"][family] = entry
        if family == "tracker":
            verdicts["tracker_routes_to_app"] = row["delivery"] == "app"
            verdicts["tracker_asks_material_questions"] = (
                1 <= len(first_a.get("questions") or []) <= 3
            )
            final = briefs[-1] if briefs else {}
            verdicts["tracker_brief_revised_with_provenance"] = (
                row["state"] == "briefed"
                and final.get("revision") == 2
                and any(a["source"] == "user_answer" for a in final.get("assumptions", []))
            )
        elif family == "artifact":
            verdicts["artifact_routes_to_task"] = row["delivery"] == "task"
            verdicts["artifact_names_unavailable_files"] = any(
                "artifact" in c.lower() or "file" in c.lower()
                for c in (briefs[-1].get("unavailable_capabilities", []) if briefs else [])
            )
        elif family == "unsupported":
            unavailable = (
                " ".join(briefs[-1].get("unavailable_capabilities", [])).lower() if briefs else ""
            )
            verdicts["unsupported_named_not_promised"] = (
                any(k in unavailable for k in ("messaging", "whatsapp", "http", "web", "schedule"))
                and row["state"] != "failed"
                and states_limit(first_a.get("reply") or "")
            )
    cursor = conn.execute("SELECT * FROM model_usage")
    columns = [c[0] for c in cursor.description]
    record["model_usage"] = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
    record["builds_count"] = conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
    record["runs_count"] = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    conn.close()
    verdicts["no_app_or_task_records_created"] = (
        record["builds_count"] == 0 and record["runs_count"] == 0
    )
    record["verdicts"] = verdicts
    text = json.dumps(record, default=str)
    record["secret_scan"] = {
        "needles_found": [n for n in ("sk-ant-", "sk-", "Bearer ", "access_token") if n in text]
    }
    (out_dir / "record.json").write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )
    print("verdicts:", json.dumps(verdicts, indent=1))
    return 0 if all(verdicts.values()) else 1


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--recover-from":
        return recover(Path(sys.argv[2]))
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = EVIDENCE / f"F04-live-{stamp}"
    out_dir.mkdir(parents=True)
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
        timeout=60,
    )
    record: dict[str, Any] = {
        "commit": commit,
        "started_at": stamp,
        "requests": REQUESTS,
        "results": {},
    }
    verdicts: dict[str, bool] = {}
    try:
        for family, text in REQUESTS.items():
            print(f"--- {family}: {text}")
            created = client.post(
                "/api/conversations", json={"text": text, "route_id": "claude-code-cli"}
            )
            created.raise_for_status()
            cid = created.json()["conversation_id"]
            first = settle(client, cid)
            summary = summarize(first)
            print(json.dumps(summary, indent=1)[:2500])
            record["results"][family] = {"first": summary, "conversation_id": cid}
            if family == "tracker":
                verdicts["tracker_routes_to_app"] = first["delivery"] == "app"
                verdicts["tracker_asks_material_questions"] = (
                    1 <= len(first.get("questions") or []) <= 3
                )
                if first["state"] == "waiting_for_user" and first["questions"]:
                    answers = {
                        q["id"]: q["options"][0] if q["options"] else "your call"
                        for q in first["questions"]
                    }
                    client.post(
                        f"/api/conversations/{cid}/messages", json={"answers": answers}
                    ).raise_for_status()
                    second = settle(client, cid)
                    record["results"][family]["answers"] = answers
                    record["results"][family]["second"] = summarize(second)
                    print("after answers:", json.dumps(summarize(second), indent=1)[:2000])
                    brief = second.get("current_brief") or {}
                    verdicts["tracker_brief_revised_with_provenance"] = (
                        second["state"] == "briefed"
                        and brief.get("revision") == 2
                        and any(a["source"] == "user_answer" for a in brief.get("assumptions", []))
                    )
                    record["results"][family]["full_conversation"] = second
                else:
                    verdicts["tracker_brief_revised_with_provenance"] = False
                    record["results"][family]["full_conversation"] = first
            elif family == "artifact":
                verdicts["artifact_routes_to_task"] = first["delivery"] == "task"
                verdicts["artifact_names_unavailable_files"] = "artifacts" in (
                    (first.get("current_brief") or {}).get("unavailable_capabilities") or []
                )
                record["results"][family]["full_conversation"] = first
            else:
                # A recurring background workflow is an App without custom UI
                # (Prototype_Scope_and_Acceptance §1), so the delivery is not constrained;
                # the check is that the missing pieces are named and the reply states the
                # limit instead of promising the outcome now.
                unavailable = (first.get("current_brief") or {}).get(
                    "unavailable_capabilities"
                ) or []
                verdicts["unsupported_named_not_promised"] = (
                    bool({"messaging", "http", "schedules"} & set(unavailable))
                    and first["state"] != "failed"
                    and states_limit(first.get("reply") or "")
                )
                record["results"][family]["full_conversation"] = first
        record["routes"] = client.get("/api/model-routes").json()
    finally:
        core.terminate()
        core.wait(timeout=15)
        client.close()
    import sqlite3

    conn = sqlite3.connect(data_dir / "control.sqlite")
    record["model_usage"] = [
        dict(
            zip(
                [c[0] for c in conn.execute("SELECT * FROM model_usage").description],
                r,
                strict=True,
            )
        )
        for r in conn.execute("SELECT * FROM model_usage")
    ]
    record["builds_count"] = conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0]
    record["runs_count"] = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    conn.close()
    verdicts["no_app_or_task_records_created"] = (
        record["builds_count"] == 0 and record["runs_count"] == 0
    )
    record["verdicts"] = verdicts
    text = json.dumps(record, default=str)
    needles = ("sk-ant-", "sk-", "Bearer ", "access_token")
    record["secret_scan"] = {"needles_found": [n for n in needles if n in text]}
    (out_dir / "record.json").write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )
    print("verdicts:", json.dumps(verdicts, indent=1))
    print(f"evidence written to {out_dir}")
    return 0 if all(verdicts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
