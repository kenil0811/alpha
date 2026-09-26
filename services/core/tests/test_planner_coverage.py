"""M1 review finding F05: a plan must cover the brief's material outcomes, and an incomplete plan
gets exactly one chance to be rewritten."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from alpha.solutions.planner import AcceptancePlanner, PlanningFailed, coverage_problems
from alpha_contracts.briefs import SolutionBrief
from alpha_contracts.verification import ValidationPlan

BRIEF = SolutionBrief.model_validate(
    {
        "id": "brief_1",
        "revision": 1,
        "conversation_id": "conv_1",
        "created_at": datetime.now(UTC).isoformat(),
        "goal": "Track what I eat",
        "success_summary": "Entries and trends are right",
        "delivery": "app",
        "surfaces": ["conversation"],
        "inputs": [],
        "primary_journey": [],
        "data_needs": [
            {
                "collection": "food_entries",
                "purpose": "What was eaten",
                "fields": [{"name": "food", "kind": "text", "description": "Food"}],
            }
        ],
        "actions": [
            {
                "id": "log_entry",
                "title": "Log",
                "description": "Save one entry, estimating calories",
                "effect_class": "local_write",
                "required_capabilities": ["records", "models"],
            },
            {"id": "trends", "title": "Trends", "description": "Averages", "effect_class": "none"},
        ],
        "recurrence": None,
        "constraints": [],
        "acceptance_examples": [],
        "assumptions": [],
        "open_questions": [],
        "unavailable_capabilities": [],
        "selected_context_snapshot_id": "conv_1.context.r1",
    }
)

LOG = {"kind": "invoke", "id": "log", "action": "log_entry", "input": {"food": "apple"}}
READ = {"kind": "records", "id": "read", "collection": "food_entries", "count": 1}
TRENDS_ANY = {
    "kind": "invoke",
    "id": "t",
    "action": "trends",
    "input": {},
    "output": {"average": {"$any": True}},
}
TRENDS_EXACT = {
    "kind": "invoke",
    "id": "t",
    "action": "trends",
    "input": {},
    "output": {"average_per_logged_day": 95, "days_logged": 1},
}
OFFLINE = {
    "kind": "invoke",
    "id": "off",
    "action": "log_entry",
    "input": {"food": "pear"},
    "model": "unavailable",
}


def plan(*steps: dict[str, Any]) -> ValidationPlan:
    return ValidationPlan.model_validate(
        {"scenarios": [{"id": "s", "description": "d", "steps": list(steps)}]}
    )


COMPLETE = plan(LOG, READ, OFFLINE, {**READ, "id": "read2", "count": 2}, TRENDS_EXACT)


def test_a_plan_missing_outcomes_is_told_exactly_what_is_missing() -> None:
    assert coverage_problems(plan(LOG), BRIEF) == [
        "the plan never runs log_entry with the model unavailable",
        "the plan never runs trends successfully",
        "the plan never reads what is stored in food_entries",
    ]
    assert "the plan never checks a value trends computes" in coverage_problems(
        plan(LOG, READ, OFFLINE, TRENDS_ANY), BRIEF
    ), "wildcards alone do not check a computed result"
    assert coverage_problems(COMPLETE, BRIEF) == []


class Inference:
    def __init__(self, drafts: list[ValidationPlan]) -> None:
        self.drafts = drafts
        self.prompts: list[str] = []

    def call(self, route: Any, **kwargs: Any) -> Any:
        self.prompts.append(kwargs["prompt"])
        draft = self.drafts[len(self.prompts) - 1]
        return SimpleNamespace(
            output={"app_name": "Food log", "validation_plan": draft.model_dump(mode="json")}
        )


ROUTE = SimpleNamespace(route_id="claude-code-cli")


def test_an_incomplete_plan_is_rewritten_once_with_the_problems() -> None:
    inference = Inference([plan(LOG), COMPLETE])
    planned = AcceptancePlanner(inference).plan(BRIEF, ROUTE, "create_1")  # type: ignore[arg-type]
    assert planned.plan == COMPLETE
    assert "the first plan was incomplete and was rewritten once" in planned.notes
    assert "the plan never runs trends successfully" in inference.prompts[1]


def test_a_plan_still_incomplete_after_one_rewrite_stops_honestly() -> None:
    inference = Inference([plan(LOG), plan(LOG, READ)])
    with pytest.raises(PlanningFailed, match="incomplete"):
        AcceptancePlanner(inference).plan(BRIEF, ROUTE, "create_1")  # type: ignore[arg-type]
    assert len(inference.prompts) == 2
