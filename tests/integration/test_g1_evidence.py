"""M1-R06 (review finding F05): the G1 driver's verdicts, and its record of a native session.

The old use verdict passed any call marked as an expected refusal, even one that succeeded and
wrote data. The `record` command collects what a session in the Alpha window left in the stores,
so native evidence is kept apart from evidence gathered through the API.
"""

from __future__ import annotations

from typing import Any

import pytest

from evals.g1 import call_verdict, native_record, record_summary
from tests.integration.app_harness import output, start_action, wait_run
from tests.integration.conftest import CoreProcess
from tests.integration.test_creations import create

pytestmark = pytest.mark.integration

REFUSE: dict[str, Any] = {"action": "add_note", "input": {"title": ""}, "expect": "failed"}
ADD: dict[str, Any] = {"action": "add_note", "input": {"title": "Call the bank"}}
ONE = {"notes": [{"id": "n1", "revision": 1, "values": {"title": "Call the bank"}}]}
TWO = {"notes": [*ONE["notes"], {"id": "n2", "revision": 1, "values": {"title": ""}}]}


def test_an_expected_refusal_that_succeeds_fails_the_verdict() -> None:
    # The review's probe R06: this case passed the old verdict.
    verdict = call_verdict(REFUSE, {"accepted": True, "state": "succeeded"}, ONE, TWO)
    assert verdict["ok"] is False
    assert verdict["problems"] == [
        "expected a refusal but it ended succeeded",
        "the refused call changed stored data",
    ]


def test_a_refusal_that_still_writes_fails_the_verdict() -> None:
    verdict = call_verdict(REFUSE, {"accepted": True, "state": "failed"}, ONE, TWO)
    assert verdict["ok"] is False
    assert verdict["problems"] == ["the refused call changed stored data"]


def test_a_clean_refusal_passes_and_can_be_held_to_its_reason() -> None:
    failed = {"accepted": True, "state": "failed", "errors": [{"message": "Title is needed."}]}
    assert call_verdict(REFUSE, failed, ONE, ONE)["ok"] is True
    assert call_verdict({**REFUSE, "expect_message": "title is needed"}, failed, ONE, ONE)["ok"]
    wrong = call_verdict({**REFUSE, "expect_message": "amount"}, failed, ONE, ONE)
    assert wrong["problems"] == ["the refusal did not say 'amount'"]
    refused = {"accepted": False, "status": 422, "detail": {"detail": "title: too short"}}
    assert call_verdict(REFUSE, refused, ONE, ONE) == {
        "ok": True,
        "expected": "failed",
        "state": "refused",
        "problems": [],
    }


def test_an_expected_success_must_succeed() -> None:
    assert call_verdict(ADD, {"accepted": True, "state": "succeeded"}, {}, ONE)["ok"] is True
    assert call_verdict(ADD, {"accepted": True, "state": "failed"}, {}, {})["ok"] is False
    assert call_verdict(ADD, {"accepted": False, "status": 422}, {}, {})["ok"] is False


def test_record_collects_a_session_from_the_stores_without_changing_them(
    build_core: CoreProcess,
) -> None:
    core = build_core
    final = create(core, "Keep a notes list for me, no screen")
    assert final["state"] == "active", final
    app_id = final["app_id"]
    output(core, app_id, "add_note", {"title": "Call the bank"})
    refused = start_action(core, app_id, "add_note", {"title": "x" * 301})
    assert refused.status_code == 202, refused.text
    assert wait_run(core, refused.json()["run_id"])["state"] == "failed"
    core.stop()

    control = core.data_dir / "control.sqlite"
    before = control.read_bytes()
    record = native_record(core.data_dir, final["conversation_id"])
    assert control.read_bytes() == before, "recording is read-only"

    assert [t["role"] for t in record["turns"]][:2] == ["user", "assistant"]
    assert record["briefs"], "the brief is recorded"
    [creation] = record["creations"]
    assert (creation["state"], creation["app_id"]) == ("active", app_id)
    assert creation["plan_json"], "the acceptance plan is recorded"
    [build] = record["builds"]
    assert build["attempts"] and build["events"]
    [app] = record["apps"]
    assert app["app"][0]["current_release_id"] == app["releases"][-1]["release_id"]
    assert [r["state"] for r in app["runs"]] == ["succeeded", "failed"]
    assert [r["values"]["title"] for r in app["records"]] == ["Call the bank"]
    assert {u["scope_kind"] for u in record["model_usage"]} >= {"assistant_turn"}
    assert isinstance(record["cost_usd_estimate"], float)


def test_record_keeps_a_failed_creation_that_made_no_app(build_core: CoreProcess) -> None:
    """Found in M1-R07: a failed creation keeps its assigned App id, and the summary assumed an
    App had been made."""
    final = create(build_core, "Keep a notes list for me, no screen", hint="fail")
    assert final["state"] == "failed" and final["app_id"], final
    build_core.stop()
    record = native_record(build_core.data_dir, final["conversation_id"])
    record["label"] = "failed"
    [app] = record["apps"]
    assert app["app"] == [] and app["records"] == []
    assert record_summary(record)["creations"] == [("failed", final["app_id"])]
    assert record_summary(record)["records"] == {}
