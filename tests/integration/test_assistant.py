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


def settle(core: CoreProcess, conversation_id: str, timeout: float = 60.0) -> dict[str, Any]:
    """The conversation once the assistant has stopped thinking or researching."""
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = get(core, conversation_id)
        if last["state"] not in ("thinking", "researching"):
            return last
        time.sleep(0.1)
    raise AssertionError(f"conversation {conversation_id} stayed {last.get('state')}")


def accepted(core: CoreProcess, conversation_id: str) -> dict[str, Any]:
    """Settled, and past the proposal a new module gets: the default option is picked the
    way the shell sends a pick, as a plain reply."""
    conversation = settle(core, conversation_id)
    if conversation["state"] == "proposed":
        options = {o["id"]: o for o in conversation["proposal"]["options"]}
        pick = options[conversation["proposal"]["default"]]
        reply(core, conversation_id, {"text": f'Go with "{pick["title"]}": {pick["summary"]}'})
        conversation = settle(core, conversation_id)
    return conversation


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
    proposed = settle(core, created["conversation_id"])
    assert proposed["state"] == "proposed", "a new module is researched and shaped first"
    assert proposed["current_brief"]["revision"] == 2, "the brief is ready behind the options"
    second = accepted(core, created["conversation_id"])
    assert second["state"] == "briefed"
    brief2 = second["current_brief"]
    # Revision 2 answered the questions; the pick from the proposal is revision 3.
    assert brief2["id"] == brief1["id"] and brief2["revision"] == 3
    assert brief2["supersedes_revision"] == 2 and brief2["open_questions"] == []
    assert second["brief_history"] == [1, 2, 3]
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
    assert conn.execute("SELECT COUNT(*) FROM briefs").fetchone()[0] == 3
    conn.close()


def test_use_defaults_resolves_open_questions(core: CoreProcess) -> None:
    created = start(core, "Track what I eat and how much, with calories, history and trends")
    settle(core, created["conversation_id"])
    reply(core, created["conversation_id"], {"use_defaults": True})
    final = accepted(core, created["conversation_id"])
    assert final["state"] == "briefed"
    assert final["current_brief"]["revision"] == 3, "defaults, then the pick from the proposal"
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
        families["records"]["available"] is True
        and "records.create" in families["records"]["operations"][0]
    )


def test_a_turn_cut_off_by_a_restart_is_reported_and_can_be_retried(data_dir: Path) -> None:
    """M1-R01 (review finding F06, check F01.C04): a turn that was thinking when Core stopped is
    marked failed in plain words on the next start, and Try again reruns it from the same input
    without adding a turn."""
    from tests.integration.conftest import start_core

    first = start_core(data_dir)
    try:
        started = start(first, "slowly: Keep a notes list for me")
        assert started["state"] == "thinking"
    finally:
        first.stop()

    second = start_core(data_dir)
    try:
        stalled = get(second, started["conversation_id"])
        assert stalled["state"] == "failed"
        assert stalled["error"] == "Alpha was closed or restarted while it was thinking about this"
        turns = len(stalled["turns"])
        with second.client() as client:
            retried = client.post(f"/api/conversations/{started['conversation_id']}/retry")
            assert retried.status_code == 200, retried.text
            assert retried.json()["state"] == "thinking"
            again = client.post(f"/api/conversations/{started['conversation_id']}/retry")
            assert again.status_code == 409, "only a failed turn can be retried"
        done = settle(second, started["conversation_id"])
        assert done["state"] == "proposed", done
        assert done["delivery"] == "app"
        assert len([t for t in done["turns"] if t["role"] == "user"]) == len(
            [t for t in stalled["turns"] if t["role"] == "user"]
        ), "retry adds no user turn"
        assert len(done["turns"]) == turns + 1
        assert accepted(second, started["conversation_id"])["state"] == "briefed"
    finally:
        second.stop()
