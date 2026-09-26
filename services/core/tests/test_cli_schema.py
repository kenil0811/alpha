"""Schemas sent over the claude-code-cli route hold only standard JSON Schema keywords.

Found live in G1: the planner's schema carried Pydantic's `discriminator` (from the tagged step
union), and the CLI refused the call before the model ran ("--json-schema is not a valid JSON
Schema: strict mode: unknown keyword"). The fake route never sends a schema, so only this test
guards it offline.
"""

from __future__ import annotations

from typing import Any

import jsonschema
import pytest
from alpha.assistant.turn import turn_output_schema
from alpha.models.structured import _SCHEMA_KEYWORDS, cli_schema
from alpha.solutions.planner import PlanDraft

SAMPLE_PLAN: dict[str, Any] = {
    "scenarios": [
        {
            "id": "log_and_read",
            "description": "An entry is saved and read back from storage",
            "steps": [
                {"kind": "invoke", "id": "add", "action": "log_food", "input": {"food": "Apple"}},
                {
                    "kind": "records",
                    "id": "stored",
                    "collection": "food_entries",
                    "count": 1,
                    "includes": [{"food": "Apple", "eaten_on": {"$today": 0}}],
                },
            ],
        }
    ],
    "ui": {
        "primary": [
            {"kind": "fill", "label": "Food", "text": "Apple"},
            {"kind": "press", "key": "Enter"},
        ],
        "saved": {
            "kind": "records",
            "id": "saved",
            "collection": "food_entries",
            "includes": [{"food": "Apple"}],
        },
        "shows": ["Apple"],
        "seed": [{"kind": "invoke", "id": "s1", "action": "log_food", "input": {"food": "Rice"}}],
        "seed_shows": ["Rice"],
    },
}


def keywords(schema: Any, path: str = "#") -> list[str]:
    """Every (path, keyword) outside the standard vocabulary, walked structurally."""
    found: list[str] = []
    if not isinstance(schema, dict):
        return found
    for key, value in schema.items():
        if key not in _SCHEMA_KEYWORDS:
            found.append(f"{path}/{key}")
        if key in {"properties", "patternProperties", "$defs", "definitions"}:
            for name, sub in value.items():
                found += keywords(sub, f"{path}/{key}/{name}")
        elif key in {"anyOf", "oneOf", "allOf", "prefixItems"}:
            for i, sub in enumerate(value):
                found += keywords(sub, f"{path}/{key}/{i}")
        elif isinstance(value, dict):
            found += keywords(value, f"{path}/{key}")
    return found


SCHEMAS = {
    "acceptance_plan": PlanDraft.model_json_schema(),
    "assistant_turn": turn_output_schema(),
}


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_schemas_sent_to_the_cli_use_only_standard_keywords(name: str) -> None:
    raw = SCHEMAS[name]
    clean = cli_schema(raw)
    assert keywords(clean) == []
    jsonschema.Draft202012Validator.check_schema(clean)


def test_the_planner_schema_needed_cleaning() -> None:
    assert any(k.endswith("/discriminator") for k in keywords(SCHEMAS["acceptance_plan"]))


def test_a_valid_plan_still_satisfies_the_cleaned_schema() -> None:
    draft = PlanDraft.model_validate({"app_name": "Food log", "validation_plan": SAMPLE_PLAN})
    clean = cli_schema(PlanDraft.model_json_schema())
    jsonschema.validate(draft.model_dump(mode="json", exclude_none=True), clean)


def test_properties_named_like_keywords_are_kept() -> None:
    schema = {
        "type": "object",
        "properties": {"format": {"type": "string", "format": "date"}, "discriminator": {}},
        "x-vendor": True,
    }
    assert cli_schema(schema) == {
        "type": "object",
        "properties": {"format": {"type": "string"}, "discriminator": {}},
    }
