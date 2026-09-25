"""F04.C02 controls on the fake route: routing to answer/task/app, material questions, brief
revision with assumption provenance, no App/Task records created by a brief."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

import pytest

from tests.integration.conftest import CoreProcess

pytestmark = pytest.mark.integration


def start(core: CoreProcess, text: str) -> dict[str, Any]:
    with core.client() as client:
        response = client.post("/api/conversations", json={"text": text})
        assert response.status_code == 201, response.text
        data: dict[str, Any] = response.json()
        return data


def get(core: CoreProcess, conversation_id: str) -> dict[str, Any]:
    with core.client() as client:
        response = client.get(f"/api/conversations/{conversation_id}")
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data


def reply(core: CoreProcess, conversation_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with core.client() as client:
        response = client.post(f"/api/conversations/{conversation_id}/messages", json=body)
        assert response.status_code == 200, response.text
        data: dict[str, Any] = response.json()
        return data


def settle(core: CoreProcess, conversation_id: str, timeout: float = 15.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = get(core, conversation_id)
        if last["state"] != "thinking":
            return last
        time.sleep(0.05)
    raise AssertionError(f"conversation {conversation_id} stayed thinking")


def test_tracker_request_is_clarified_then_briefed_with_provenance(
    core: CoreProcess, data_dir: Path
) -> None:
    created = start(core, "Track what I eat and how much, with calories, history and trends")
    assert created["state"] == "thinking"
    first = settle(core, created["conversation_id"])
    assert first["state"] == "waiting_for_user"
    assert first["delivery"] == "app"
    assert first["interpretation"]["outcome"]
    assert 1 <= len(first["questions"]) <= 3
    assert all(q["options"] and q["why_it_matters"] for q in first["questions"])
    brief1 = first["current_brief"]
    assert brief1["revision"] == 1 and brief1["delivery"] == "app"
    assert brief1["open_questions"] and brief1["supersedes_revision"] is None
    assert all(a["source"] == "model_default" for a in brief1["assumptions"])
    # Questions never ask for implementation choices.
    banned = ("sql", "schema", "database", "component", "framework", "json", "table")
    for q in first["questions"]:
        assert not any(b in q["question"].lower() for b in banned), q

    answers = {q["id"]: q["options"][0] for q in first["questions"]}
    replied = reply(core, created["conversation_id"], {"answers": answers})
    assert replied["state"] == "thinking"
    second = settle(core, created["conversation_id"])
    assert second["state"] == "briefed"
    brief2 = second["current_brief"]
    assert brief2["id"] == brief1["id"] and brief2["revision"] == 2
    assert brief2["supersedes_revision"] == 1 and brief2["open_questions"] == []
    assert second["brief_history"] == [1, 2]
    user_sourced = [a for a in brief2["assumptions"] if a["source"] == "user_answer"]
    assert user_sourced and all(a["turn_ref"] for a in user_sourced)
    kept = [a for a in brief2["assumptions"] if a["source"] == "model_default"]
    assert kept, "model defaults from revision 1 are retained"
    # Revision 1 is still readable.
    with core.client() as client:
        r1 = client.get(f"/api/conversations/{created['conversation_id']}/briefs/1")
    assert r1.status_code == 200 and r1.json()["revision"] == 1

    # A brief creates no App, Task or build.
    conn = sqlite3.connect(data_dir / "control.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM builds").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0] == 2
    conn.close()


def test_use_defaults_resolves_open_questions(core: CoreProcess) -> None:
    created = start(core, "Track what I eat and how much, with calories, history and trends")
    settle(core, created["conversation_id"])
    reply(core, created["conversation_id"], {"use_defaults": True})
    final = settle(core, created["conversation_id"])
    assert final["state"] == "briefed"
    assert final["current_brief"]["revision"] == 2
    assert final["questions"] == []


def test_correction_creates_a_new_revision_attributed_to_the_user(core: CoreProcess) -> None:
    created = start(core, "Track what I eat and how much, with calories, history and trends")
    settle(core, created["conversation_id"])
    reply(core, created["conversation_id"], {"use_defaults": True})
    settle(core, created["conversation_id"])
    reply(core, created["conversation_id"], {"text": "also track protein"})
    final = settle(core, created["conversation_id"])
    assert final["current_brief"]["revision"] == 3
    assert final["brief_history"] == [1, 2, 3]
    kinds = [t["kind"] for t in final["turns"] if t["role"] == "user"]
    assert kinds == ["request", "answer", "correction"]


def test_artifact_request_routes_to_task_without_app(core: CoreProcess) -> None:
    created = start(core, "Turn my meeting notes into a one-page brief")
    final = settle(core, created["conversation_id"])
    assert final["delivery"] == "task"
    assert final["state"] == "briefed"
    assert final["current_brief"]["delivery"] == "task"
    assert "artifacts" in final["current_brief"]["unavailable_capabilities"]
    assert "not connected" in final["reply"]


def test_unsupported_capability_is_named_not_promised(core: CoreProcess) -> None:
    created = start(core, "Text my mom the weather on WhatsApp every morning")
    final = settle(core, created["conversation_id"])
    assert final["state"] in ("briefed", "answered")
    unavailable = set(final["current_brief"]["unavailable_capabilities"])
    assert "messaging" in unavailable
    assert "can't send" in final["reply"] or "not connected" in final["reply"]


def test_plain_question_gets_an_answer_and_no_brief(core: CoreProcess, data_dir: Path) -> None:
    created = start(core, "What is the capital of Australia?")
    final = settle(core, created["conversation_id"])
    assert final["state"] == "answered" and final["delivery"] == "answer"
    assert final["current_brief"] is None
    assert "Canberra" in final["reply"]
    conn = sqlite3.connect(data_dir / "control.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0] == 0
    conn.close()


def test_reply_while_thinking_and_bad_requests_are_rejected(core: CoreProcess) -> None:
    created = start(
        core, "slowly: Track what I eat and how much, with calories, history and trends"
    )
    with core.client() as client:
        busy = client.post(
            f"/api/conversations/{created['conversation_id']}/messages", json={"text": "x"}
        )
        assert busy.status_code == 409
        settle(core, created["conversation_id"])
        assert (
            client.post(
                f"/api/conversations/{created['conversation_id']}/messages", json={}
            ).status_code
            == 422
        )
        assert client.post("/api/conversations", json={"text": ""}).status_code == 422
        assert (
            client.post("/api/conversations", json={"text": "x", "grant": "all"}).status_code == 422
        )
        assert client.get("/api/conversations/conv_missing").status_code == 404
        listed = client.get("/api/conversations").json()["conversations"]
        assert listed and listed[0]["conversation_id"] == created["conversation_id"]
        catalog = client.get("/api/capabilities").json()["capabilities"]
    families = {c["family"]: c for c in catalog}
    assert families["compute"]["available"] is True
    assert (
        families["records"]["available"] is False and families["records"]["arrives_with"] == "F05"
    )
