"""F06 support: Core enforces the read views an App's UI declares (App UI Bridge
records.query). Runs against the neutral entries fixture on the real App runtime profile."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from tests.integration.app_harness import install, output
from tests.integration.conftest import AppCore

pytestmark = pytest.mark.integration

APP = "entries-fixture"


def view(app: AppCore, view_id: str, body: dict[str, Any] | None = None) -> httpx.Response:
    with app.core.client() as client:
        return client.post(f"/api/apps/{APP}/views/{view_id}/query", json=body or {})


@pytest.fixture
def entries(app_core: AppCore) -> AppCore:
    install(app_core.core, "entries_app")
    created = output(app_core.core, APP, "seed_examples", {"days": 10})["created"]
    assert created == 13  # 8 of 10 days, one or two entries each
    return app_core


def test_app_detail_exposes_the_ui_declaration(entries: AppCore) -> None:
    with entries.core.client() as client:
        detail = client.get(f"/api/apps/{APP}").json()
    assert [v["id"] for v in detail["ui"]["views"]] == [
        "entries.list",
        "entries.queue",
        "entries.daily",
    ]
    assert detail["ui"]["actions"] == ["add_entry", "update_entry", "set_status", "remove_entry"]


def test_records_views_apply_projection_filters_sorting_and_limits(entries: AppCore) -> None:
    page = view(entries, "entries.list", {"limit": 4}).json()
    assert len(page["records"]) == 4 and page["next_cursor"]
    assert set(page["records"][0]["values"]) <= {
        "title",
        "amount",
        "kind",
        "status",
        "noted_on",
        "note",
        "reason",
    }
    second = view(entries, "entries.list", {"limit": 4, "cursor": page["next_cursor"]}).json()
    assert {r["id"] for r in second["records"]}.isdisjoint({r["id"] for r in page["records"]})

    tasks = view(
        entries,
        "entries.list",
        {
            "where": {"field": "kind", "op": "eq", "value": "task"},
            "order_by": [{"field": "amount", "direction": "desc"}],
        },
    ).json()
    amounts = [r["values"]["amount"] for r in tasks["records"]]
    assert tasks["records"] and all(r["values"]["kind"] == "task" for r in tasks["records"])
    assert amounts == sorted(amounts, reverse=True)

    new_only = view(
        entries, "entries.queue", {"where": {"field": "status", "op": "eq", "value": "new"}}
    ).json()
    assert new_only["records"] and all(r["values"]["status"] == "new" for r in new_only["records"])


@pytest.mark.parametrize(
    ("view_id", "body", "status", "code"),
    [
        ("entries.list", {"where": {"field": "note", "op": "eq", "value": "x"}}, 403, "forbidden"),
        ("entries.list", {"order_by": [{"field": "note", "direction": "asc"}]}, 403, "forbidden"),
        ("entries.list", {"limit": 500}, 422, "limit_exceeded"),
        ("entries.queue", {"order_by": [{"field": "title", "direction": "asc"}]}, 403, "forbidden"),
        (
            "entries.daily",
            {"order_by": [{"field": "noted_on", "direction": "asc"}]},
            403,
            "forbidden",
        ),
        ("entries.secret", {}, 404, "not_found"),
    ],
)
def test_views_refuse_what_they_do_not_declare(
    entries: AppCore, view_id: str, body: dict[str, Any], status: int, code: str
) -> None:
    response = view(entries, view_id, body)
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code


def test_unknown_fields_and_sql_are_rejected_before_any_query(entries: AppCore) -> None:
    assert view(entries, "entries.list", {"sql": "select 1"}).status_code == 422
    assert view(entries, "entries.list", {"where": "1=1"}).status_code == 422


def test_aggregate_view_groups_by_day_and_honors_filters(entries: AppCore) -> None:
    result = view(entries, "entries.daily").json()
    days = [g["key"]["noted_on_day"] for g in result["groups"]]
    assert days == sorted(days) and len(days) == 8  # 10 days minus the two left empty
    assert sum(g["values"]["entries"] for g in result["groups"]) == 13
    recent = view(
        entries, "entries.daily", {"where": {"field": "noted_on", "op": "gte", "value": days[-3]}}
    ).json()
    assert [g["key"]["noted_on_day"] for g in recent["groups"]] == days[-3:]
