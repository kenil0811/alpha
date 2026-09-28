"""The declarative screen: what the shell draws for a module with no compiled UI."""

from __future__ import annotations

import copy

import pytest
from alpha_contracts.apps import AppSource
from pydantic import ValidationError

ACTION = {
    "id": "log_entry",
    "title": "Add an entry",
    "description": "Save one thing eaten.",
    "handler": "app_code.handlers:log_entry",
    "invocable_from": ["ui", "manual"],
    "effect_class": "local_write",
    "capability_requirements": ["records"],
    "input_schema": {
        "type": "object",
        "required": ["text"],
        "additionalProperties": False,
        "properties": {"text": {"type": "string"}, "calories": {"type": ["number", "null"]}},
    },
    "output_schema": {
        "type": "object",
        "required": ["id"],
        "properties": {"id": {"type": "string"}},
    },
}

CORRECT = {
    **ACTION,
    "id": "correct_entry",
    "title": "Fix an entry",
    "handler": "app_code.handlers:correct_entry",
    "input_schema": {
        "type": "object",
        "required": ["entry"],
        "additionalProperties": False,
        "properties": {
            "entry": {"type": "string"},
            "food": {"type": ["string", "null"]},
            "calories": {"type": ["number", "null"]},
            "delete": {"type": ["boolean", "null"]},
        },
    },
}

SOURCE = {
    "contract_version": "0.2",
    "app_id": "food-log",
    "name": "Food log",
    "description": "Log what you eat.",
    "runtime_profile": "pyprof-x",
    "sdk_version": "0.1.0",
    "capabilities": ["records"],
    "collections": [
        {
            "name": "entries",
            "fields": [
                {"name": "when", "kind": "date", "required": True},
                {"name": "food", "kind": "text", "required": True},
                {"name": "calories", "kind": "number"},
                {"name": "meal", "kind": "choice", "choices": ["breakfast", "lunch", "dinner"]},
            ],
        },
        {"name": "goals", "fields": [{"name": "daily", "kind": "number", "required": True}]},
    ],
    "actions": [ACTION, CORRECT],
    "views": [
        {"id": "goals.current", "collection": "goals", "max_limit": 1},
        {
            "id": "entries.all",
            "collection": "entries",
            "filterable": ["when", "meal", "food"],
            "sortable": ["when", "calories"],
            "default_order": [{"field": "when", "direction": "desc"}],
        },
        {
            "id": "entries.by_day",
            "kind": "aggregate",
            "collection": "entries",
            "group_by": [{"field": "when", "bucket": "day"}],
            "metrics": [
                {"name": "total", "fn": "sum", "field": "calories"},
                {"name": "n", "fn": "count"},
            ],
        },
    ],
    "screen": {
        "icon": "🍽",
        "tabs": [
            {
                "id": "log",
                "title": "Food log",
                "blocks": [
                    {
                        "kind": "quick_entry",
                        "action": "log_entry",
                        "input": "text",
                        "placeholder": "What did you eat?",
                    },
                    {
                        "kind": "table",
                        "view": "entries.all",
                        "columns": [
                            {"field": "when", "format": "date"},
                            {"field": "food", "editable": True},
                            {
                                "field": "calories",
                                "format": "number",
                                "editable": True,
                                "unit": "kcal",
                            },
                            {"field": "meal", "format": "pill"},
                        ],
                        "lists": [
                            {
                                "id": "today",
                                "title": "Today",
                                "where": {"field": "when", "op": "eq", "value": "2026-09-27"},
                            }
                        ],
                        "edit": {"action": "correct_entry", "id_param": "entry"},
                        "delete": {
                            "action": "correct_entry",
                            "id_param": "entry",
                            "input": {"delete": True},
                        },
                        "totals": ["calories"],
                    },
                    {
                        "kind": "metrics",
                        "cards": [
                            {
                                "title": "Calories",
                                "view": "entries.by_day",
                                "metric": "total",
                                "goal": 2000,
                                "unit": "kcal",
                            },
                            {
                                "title": "Against goal",
                                "view": "entries.by_day",
                                "metric": "total",
                                "goal_from": {"view": "goals.current", "field": "daily"},
                            },
                        ],
                    },
                    {
                        "kind": "trend",
                        "title": "Daily calories",
                        "view": "entries.by_day",
                        "x": "when_day",
                        "y": "total",
                        "goal": 2000,
                    },
                ],
            },
            {
                "id": "board",
                "title": "By meal",
                "blocks": [
                    {
                        "kind": "board",
                        "view": "entries.all",
                        "group_field": "meal",
                        "columns": ["breakfast", "lunch", "dinner"],
                        "title_field": "food",
                        "subtitle_fields": ["calories"],
                        "move": {"action": "correct_entry", "id_param": "entry"},
                        "field_param": "meal",
                    }
                ],
            },
        ],
    },
}


def test_screen_validates_and_reports_what_it_uses() -> None:
    source = AppSource.model_validate(SOURCE)
    assert source.has_screen()
    assert source.screen is not None
    assert source.screen.views_used() == {"entries.all", "entries.by_day", "goals.current"}
    assert source.screen.actions_used() == {"log_entry", "correct_entry"}
    assert source.view("entries.by_day") is not None


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("screen", "tabs", 0, "blocks", 1, "view"), "nope", "undeclared view"),
        (("screen", "tabs", 0, "blocks", 1, "columns", 0, "field"), "weight", "not in view"),
        (("screen", "tabs", 0, "blocks", 0, "input"), "food", "has no input"),
        (("screen", "tabs", 0, "blocks", 2, "cards", 0, "metric"), "avg", "has no metric"),
        (("screen", "tabs", 0, "blocks", 3, "x"), "when", "not a group key"),
        (("screen", "tabs", 1, "blocks", 0, "columns"), ["breakfast", "brunch"], "not choices"),
        (("screen", "tabs", 1, "blocks", 0, "group_field"), "food", "must be a choice field"),
        (
            ("screen", "tabs", 0, "blocks", 2, "cards", 1, "goal_from", "field"),
            "weekly",
            "goal_from field",
        ),
        (
            ("screen", "tabs", 0, "blocks", 2, "cards", 1, "goal_from", "view"),
            "entries.by_day",
            "needs a records view",
        ),
    ],
)
def test_screen_rejects_dangling_references(path: tuple, value: object, message: str) -> None:
    data = copy.deepcopy(SOURCE)
    node = data
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    with pytest.raises(ValidationError, match=message):
        AppSource.model_validate(data)


def test_screen_action_must_be_ui_invocable() -> None:
    data = copy.deepcopy(SOURCE)
    data["actions"][0]["invocable_from"] = ["manual"]
    with pytest.raises(ValidationError, match="not invocable from ui"):
        AppSource.model_validate(data)


def test_view_ids_unique_across_views_and_ui() -> None:
    data = copy.deepcopy(SOURCE)
    data["ui"] = {"views": [{"id": "entries.all", "collection": "entries"}], "actions": []}
    with pytest.raises(ValidationError, match="unique across"):
        AppSource.model_validate(data)


def test_app_without_screen_still_valid() -> None:
    data = copy.deepcopy(SOURCE)
    del data["screen"]
    del data["views"]
    source = AppSource.model_validate(data)
    assert source.has_screen(), "its collections give it derived pages"
    data["collections"] = []
    assert not AppSource.model_validate(data).has_screen()


def test_richer_field_kinds_and_page_settings() -> None:
    from alpha_contracts.records import CollectionSchema

    schema = CollectionSchema.model_validate(
        {
            "name": "tasks",
            "title_field": "title",
            "fields": [
                {"name": "title", "kind": "text", "required": True},
                {"name": "notes", "kind": "long_text"},
                {"name": "link", "kind": "url"},
                {"name": "tags", "kind": "multiselect", "choices": ["home", "work"]},
                {
                    "name": "state",
                    "kind": "status",
                    "choices": ["todo", "doing", "done"],
                    "done_choices": ["done"],
                },
                {"name": "due", "kind": "date"},
            ],
            "page": {
                "view": "board",
                "group_field": "state",
                "date_field": "due",
                "sort": {"field": "due", "direction": "asc"},
                "columns": ["title", "due"],
            },
        }
    )
    assert schema.page is not None and schema.page.group_field == "state"
    with pytest.raises(ValidationError, match="done_choices names unknown"):
        CollectionSchema.model_validate(
            {
                "name": "t",
                "fields": [
                    {"name": "s", "kind": "status", "choices": ["a"], "done_choices": ["z"]}
                ],
            }
        )
    with pytest.raises(ValidationError, match="group_field must be a choice or status"):
        CollectionSchema.model_validate(
            {"name": "t", "fields": [{"name": "n", "kind": "text"}], "page": {"group_field": "n"}}
        )
    with pytest.raises(ValidationError, match="title_field"):
        CollectionSchema.model_validate(
            {"name": "t", "title_field": "nope", "fields": [{"name": "n", "kind": "text"}]}
        )


def test_summary_cards_are_checked_like_a_screen() -> None:
    data = copy.deepcopy(SOURCE)
    del data["screen"]
    data["summary"] = [
        {
            "kind": "metrics",
            "cards": [{"title": "Today", "view": "entries.by_day", "metric": "total"}],
        }
    ]
    source = AppSource.model_validate(data)
    assert len(source.summary) == 1
    data["summary"] = [
        {"kind": "metrics", "cards": [{"title": "x", "view": "nope", "metric": "total"}]}
    ]
    with pytest.raises(ValidationError, match="undeclared view"):
        AppSource.model_validate(data)


def test_a_negated_filter_accepts_both_spellings() -> None:
    from alpha_contracts.records import Not

    assert Not.model_validate({"not": {"field": "a", "op": "is_null"}}).not_.field == "a"  # type: ignore[union-attr]
    assert Not.model_validate({"not_": {"field": "a", "op": "is_null"}}).not_.field == "a"  # type: ignore[union-attr]


def test_a_table_detail_is_validated_like_its_columns() -> None:
    source = copy.deepcopy(SOURCE)
    table = source["screen"]["tabs"][0]["blocks"][1]
    table["detail"] = {
        "title_field": "food",
        "long_fields": ["food"],
        "actions": [{"action": "correct_entry", "id_param": "entry", "title": "Fix"}],
    }
    app = AppSource.model_validate(source)
    assert app.screen is not None
    detail = app.screen.tabs[0].blocks[1].detail  # type: ignore[union-attr]
    assert detail is not None and detail.title_field == "food"

    for bad, message in (
        ({"fields": ["nope"]}, "detail field 'nope' is not in view"),
        ({"title_field": "nope"}, "detail field 'nope' is not in view"),
        ({"actions": [{"action": "correct_entry"}]}, "needs id_param"),
        ({"actions": [{"action": "missing", "id_param": "entry"}]}, "undeclared action"),
    ):
        broken = copy.deepcopy(source)
        broken["screen"]["tabs"][0]["blocks"][1]["detail"] = bad
        with pytest.raises(ValidationError, match=message):
            AppSource.model_validate(broken)


def test_a_progress_block_is_a_metric_against_a_goal() -> None:
    source = copy.deepcopy(SOURCE)
    blocks = source["screen"]["tabs"][0]["blocks"]
    blocks.append(
        {
            "kind": "progress",
            "title": "Calories today",
            "view": "entries.by_day",
            "metric": "total",
            "unit": "kcal",
            "goal_from": {"view": "goals.current", "field": "daily"},
        }
    )
    app = AppSource.model_validate(source)
    assert app.screen is not None and app.screen.tabs[0].blocks[-1].kind == "progress"
    for bad, message in (
        ({"goal_from": None}, "needs a goal or goal_from"),
        ({"metric": "nope"}, "has no metric 'nope'"),
        ({"view": "entries.all", "goal": 5}, "needs an aggregate view"),
    ):
        broken = copy.deepcopy(source)
        broken["screen"]["tabs"][0]["blocks"][-1].update(bad)
        with pytest.raises(ValidationError, match=message):
            AppSource.model_validate(broken)
