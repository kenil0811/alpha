"""F05.C02: wrong-owner operations, invalid values and unsafe/unbounded queries fail.

Each case runs inside a real App worker. Several deliberately bypass the SDK facade and write raw
calls on the worker's pipe, the way hostile generated code could."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from tests.integration.app_harness import act, output, shell_query, start_action
from tests.integration.conftest import AppCore

pytestmark = pytest.mark.integration

ITEMS = "items-fixture"
TALLY = "tally-fixture"


def probe(app: AppCore, case: str, arg: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"case": case}
    if arg is not None:
        payload["arg"] = arg
    return output(app.core, ITEMS, "expect_failure", payload)


def count_items(app: AppCore) -> int:
    response = shell_query(app.core, ITEMS, {"collection": "items", "limit": 1000})
    return len(response.json()["records"])


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("forged_owner_field", "invalid_input"),
        ("raw_sql_filter", "invalid_input"),
        ("sql_in_field_name", "invalid_input"),
        ("unbounded_page", "limit_exceeded"),
        ("deep_filter", "limit_exceeded"),
        ("too_many_conditions", "limit_exceeded"),
        ("foreign_cursor", "invalid_input"),
        ("unknown_operation", "invalid_input"),
        ("unknown_collection", "not_found"),
        ("filter_unknown_field", "invalid_input"),
        ("invalid_choice", "invalid_input"),
        ("missing_required", "invalid_input"),
        ("wrong_type", "invalid_input"),
        ("out_of_range", "invalid_input"),
        ("undeclared_field", "invalid_input"),
        ("naive_datetime", "invalid_input"),
        ("text_too_long", "invalid_input"),
        ("json_too_large", "invalid_input"),
        ("dangling_reference", "invalid_input"),
        ("idempotency_conflict", "conflict"),
        ("forged_token", "unauthenticated"),
    ],
)
def test_invalid_values_and_unsafe_queries_are_rejected(
    app_core: AppCore, case: str, code: str
) -> None:
    if case == "foreign_cursor":
        for title in ("a", "b"):
            output(app_core.core, ITEMS, "add_item", {"title": title, "category": "work"})
    before = count_items(app_core)
    result = probe(app_core, case)
    assert result["error_code"] == code, result
    if case != "idempotency_conflict":
        assert count_items(app_core) == before, "a rejected operation changed stored records"


def test_revision_uniqueness_and_reference_rules(app_core: AppCore) -> None:
    core = app_core.core
    item = output(core, ITEMS, "add_item", {"title": "one", "category": "work", "code": "U-1"})
    output(
        core,
        ITEMS,
        "update_item",
        {"id": item["id"], "expected_revision": 1, "changes": {"quantity": 2}},
    )
    stale = probe(app_core, "stale_revision", item["id"])
    assert (
        stale["error_code"] == "conflict" and "expected revision 1, current 2" in stale["message"]
    )
    assert probe(app_core, "duplicate_code", "U-1")["error_code"] == "conflict"
    output(core, ITEMS, "add_note", {"item": item["id"], "body": "keep"})
    blocked = probe(app_core, "delete_referenced", item["id"])
    assert blocked["error_code"] == "conflict" and "notes" in blocked["message"]
    # A stale delete is a conflict too, not a silent success.
    run = act(
        core, ITEMS, "remove_item", {"id": item["id"], "expected_revision": 1}, expect="failed"
    )
    assert run["terminal_reason"] == "operation_failed"


def test_failed_batch_rolls_back_every_operation(app_core: AppCore) -> None:
    before = count_items(app_core)
    run = act(
        app_core.core,
        ITEMS,
        "add_many",
        {
            "items": [
                {"title": "first", "category": "work"},
                {"title": "second", "category": "home"},
                {"title": "third", "category": "garden"},  # invalid choice
            ]
        },
        expect="failed",
    )
    assert run["terminal_reason"] == "operation_failed"
    error = next(e for e in app_core.core.events(run["run_id"]) if e["kind"] == "worker.error")
    assert "operation 3 of 3" in error["payload"]["message"]
    assert count_items(app_core) == before


def test_other_apps_records_and_artifacts_are_unreachable(
    app_core: AppCore, data_dir: Path
) -> None:
    core = app_core.core
    item = output(core, ITEMS, "add_item", {"title": "private", "category": "home"})
    report = output(core, ITEMS, "make_report", {})
    output(core, TALLY, "add", {"name": "tally row", "count": 1})

    assert output(core, TALLY, "read_foreign", {"id": item["id"]})["error_code"] == "not_found"
    assert (
        output(core, TALLY, "read_artifact", {"id": report["artifact_id"]})["error_code"]
        == "not_found"
    )
    # The tally App did not declare models, so the broker refuses the family outright.
    assert output(core, TALLY, "try_models", {})["error_code"] == "forbidden"
    # Same collection name, different Apps: each sees only its own rows.
    tally_rows = output(core, TALLY, "list_all", {})["items"]
    assert [r["values"]["name"] for r in tally_rows] == ["tally row"]
    items_titles = [r["values"]["title"] for r in output(core, ITEMS, "list_items", {})["items"]]
    assert "tally row" not in items_titles and "private" in items_titles
    # Separate SQLite files on disk, each stamped with its owner.
    for app_id in (ITEMS, TALLY):
        conn = sqlite3.connect(data_dir / "apps" / app_id / "records.sqlite")
        owner = conn.execute("SELECT value FROM store_meta WHERE key = 'app_id'").fetchone()[0]
        conn.close()
        assert owner == app_id


def test_workload_tokens_are_bound_to_their_own_run(app_core: AppCore) -> None:
    core = app_core.core
    # A run stores its own token in a record; a later run reads it and presents it on its pipe.
    assert probe(app_core, "leak_token")["error_code"] == "none"
    result = probe(app_core, "use_leaked_token")
    assert result["error_code"] == "unauthenticated", result
    with sqlite3.connect(core.data_dir / "control.sqlite") as conn:
        rows = conn.execute("SELECT revoked_at FROM broker_tokens").fetchall()
    assert rows and all(r[0] is not None for r in rows), "tokens outlived their runs"


def test_invocation_checks_happen_before_any_run(app_core: AppCore) -> None:
    core = app_core.core
    with core.client() as client:
        before = len(client.get("/api/runs").json()["runs"])
    bad_input = start_action(core, ITEMS, "add_item", {"title": 3, "category": "work"})
    assert bad_input.status_code == 422 and "title" in json.dumps(bad_input.json())
    unknown = start_action(core, ITEMS, "no_such_action", {})
    assert unknown.status_code == 404
    wrong_origin = start_action(core, ITEMS, "expect_failure", {"case": "x"}, origin="ui")
    assert wrong_origin.status_code == 403
    missing_app = start_action(core, "no-such-app", "add", {})
    assert missing_app.status_code == 404
    with core.client() as client:
        assert len(client.get("/api/runs").json()["runs"]) == before


def test_results_are_checked_and_prints_cannot_forge_protocol(app_core: AppCore) -> None:
    core = app_core.core
    bad = act(core, ITEMS, "bad_output", {}, expect="failed")
    assert bad["terminal_reason"] == "output_schema_violation"
    noisy = act(core, ITEMS, "noisy", {})
    assert noisy["output"] == {"ok": True}


def test_shell_queries_obey_the_same_limits(app_core: AppCore) -> None:
    response = shell_query(app_core.core, ITEMS, {"collection": "items", "limit": 5000})
    assert response.status_code == 422 and response.json()["detail"]["code"] == "limit_exceeded"
    response = shell_query(
        app_core.core,
        ITEMS,
        {"collection": "items", "where": {"field": "1=1", "op": "eq", "value": 1}},
    )
    assert response.status_code == 422
    response = shell_query(app_core.core, ITEMS, {"collection": "items", "sql": "SELECT 1"})
    assert response.status_code == 422
