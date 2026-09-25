"""F05.C01: actual worker/SDK operations validate, save, query, aggregate and reopen records.

Every operation below runs generated-style handler code in a real App worker process on the
published runtime profile; the worker reaches records only through the capability broker."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.app_harness import (
    act,
    output,
    record_evidence,
    shell_query,
    start_app_core,
    wait_run,
)
from tests.integration.conftest import AppCore

pytestmark = pytest.mark.integration

ITEMS = "items-fixture"


def _seed(app: AppCore) -> dict[str, str]:
    core = app.core
    ids = {}
    rows = [
        ("apples", "home", 3, 1.5, "2026-09-20", "2026-09-25T20:00:00Z", "A-1"),
        ("paper", "work", 10, 4.0, "2026-09-21", "2026-09-25T04:00:00+05:30", "B-2"),
        ("pens", "work", 7, 2.5, "2026-09-22", "2026-09-24T10:00:00Z", "C-3"),
        ("soap", "home", 1, 3.0, "2026-09-23", "2026-09-24T19:00:00Z", None),
    ]
    for title, category, quantity, price, noted_on, happened_at, code in rows:
        payload = {
            "title": title,
            "category": category,
            "quantity": quantity,
            "price": price,
            "noted_on": noted_on,
            "happened_at": happened_at,
            "tags": {"source": "seed", "n": quantity},
        }
        if code:
            payload["code"] = code
        ids[title] = output(core, ITEMS, "add_item", payload)["id"]
    return ids


def test_records_validate_save_query_aggregate(app_core: AppCore) -> None:
    core = app_core.core
    ids = _seed(app_core)

    record = output(core, ITEMS, "get_item", {"id": ids["paper"]})["record"]
    assert record["revision"] == 1
    # Datetimes are normalized to UTC; +05:30 04:00 is 22:30 the previous day in UTC.
    assert record["values"]["happened_at"] == "2026-09-24T22:30:00.000000Z"
    assert record["values"]["tags"] == {"n": 10, "source": "seed"}

    updated = output(
        core,
        ITEMS,
        "update_item",
        {"id": ids["paper"], "expected_revision": 1, "changes": {"quantity": 12, "price": None}},
    )
    assert updated["revision"] == 2
    record = output(core, ITEMS, "get_item", {"id": ids["paper"]})["record"]
    assert record["values"]["quantity"] == 12 and "price" not in record["values"]

    work = output(core, ITEMS, "list_items", {"category": "work", "order": ["-quantity"]})
    assert [r["values"]["title"] for r in work["items"]] == ["paper", "pens"]
    assert output(core, ITEMS, "list_items", {"min_quantity": 5})["items"].__len__() == 2
    # Case-insensitive substring match: "PE" is in paper and pens, not apples or soap.
    matched = output(core, ITEMS, "list_items", {"text": "PE"})["items"]
    assert [r["values"]["title"] for r in matched] == ["paper", "pens"]
    projected = output(core, ITEMS, "list_items", {"fields": ["title"], "limit": 1})
    assert list(projected["items"][0]["values"]) == ["title"]

    # Pagination: two pages of two, then no cursor.
    first = output(core, ITEMS, "list_items", {"limit": 2, "order": ["title"]})
    assert [r["values"]["title"] for r in first["items"]] == ["apples", "paper"]
    second = output(
        core, ITEMS, "list_items", {"limit": 2, "order": ["title"], "cursor": first["next_cursor"]}
    )
    assert [r["values"]["title"] for r in second["items"]] == ["pens", "soap"]
    assert second["next_cursor"] is None

    summary = output(core, ITEMS, "summarize", {})
    by_category = {g["key"]["category"]: g["values"] for g in summary["by_category"]}
    assert by_category["home"] == {"n": 2, "quantity": 4, "avg_price": 2.25}
    assert by_category["work"]["n"] == 2 and by_category["work"]["quantity"] == 19
    assert by_category["work"]["avg_price"] == 2.5  # paper's price was cleared
    # Days are bucketed in the person's timezone (Asia/Kolkata): 20:00Z on the 25th is the 26th.
    by_day = {g["key"]["happened_at_day"]: g["values"]["n"] for g in summary["by_day"]}
    assert by_day == {"2026-09-24": 1, "2026-09-25": 2, "2026-09-26": 1}
    assert summary["overall"] == {"n": 4, "latest": "2026-09-23", "quantity": 23}

    record_evidence("F05.C01-summary", {"paper": record, "work_page": work, "summary": summary})
    batch = output(
        core,
        ITEMS,
        "add_many",
        {
            "items": [
                {"title": "tape", "category": "work"},
                {"title": "glue", "category": "home", "quantity": 2},
            ]
        },
    )
    assert len(batch["ids"]) == 2
    note = output(core, ITEMS, "add_note", {"item": ids["pens"], "body": "blue ones"})
    assert note["id"].startswith("rec_")

    # Idempotent create: the same key and values return the same record, not a duplicate.
    again = [
        output(
            core, ITEMS, "add_item", {"title": "lamp", "category": "home", "idempotency_key": "k-1"}
        )
        for _ in range(2)
    ]
    assert again[0]["id"] == again[1]["id"]

    # Deleting at the current revision removes the record.
    output(core, ITEMS, "remove_item", {"id": ids["soap"], "expected_revision": 1})
    response = shell_query(core, ITEMS, {"collection": "items", "limit": 1000})
    titles = sorted(r["values"]["title"] for r in response.json()["records"])
    assert titles == ["apples", "glue", "lamp", "paper", "pens", "tape"]


def test_records_persist_and_reopen_after_restart(app_core: AppCore, data_dir: Path) -> None:
    core = app_core.core
    ids = _seed(app_core)
    output(
        core,
        ITEMS,
        "update_item",
        {"id": ids["pens"], "expected_revision": 1, "changes": {"title": "pens (blue)"}},
    )
    before = shell_query(
        core, ITEMS, {"collection": "items", "order_by": [{"field": "title"}]}
    ).json()
    core.stop()

    restarted = start_app_core(data_dir, app_core.profile, app_core.fixtures)
    try:
        after = shell_query(
            restarted, ITEMS, {"collection": "items", "order_by": [{"field": "title"}]}
        ).json()
        assert after == before
        record_evidence(
            "F05.C01-reopen",
            {"records_before": len(before["records"]), "identical_after_restart": after == before},
        )
        # A fresh worker in the new Core reads and writes the same store.
        record = output(restarted, ITEMS, "get_item", {"id": ids["pens"]})["record"]
        assert record["revision"] == 2 and record["values"]["title"] == "pens (blue)"
        run = act(
            restarted,
            ITEMS,
            "update_item",
            {"id": ids["pens"], "expected_revision": 2, "changes": {"quantity": 8}},
        )
        assert run["output"]["revision"] == 3
        summary = output(restarted, ITEMS, "summarize", {})
        assert summary["overall"]["quantity"] == 22
        assert wait_run(restarted, run["run_id"])["state"] == "succeeded"
    finally:
        restarted.stop()
