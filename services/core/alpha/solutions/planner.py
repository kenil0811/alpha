# ruff: noqa: E501
"""Acceptance planning: turn a SolutionBrief into the independent ValidationPlan a build is
checked against (Implementation Blueprint §6; decision 2026-09-26 §3).

The plan is written before the build and never by the builder. It fixes the App's observable
interface (action ids and inputs, collection and field names, the screen's visible labels) and
the behaviour that counts as done. The builder implements to it; the platform verifies against
its own copy.

Live route: one bounded structured model call, validated against the ValidationPlan contract
and checked for internal consistency. Fake route (control fixture only): a deterministic
conversion of the brief's own acceptance examples.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from alpha_contracts.briefs import SolutionBrief, Surface
from alpha_contracts.verification import (
    InvokeStep,
    RecordsStep,
    Scenario,
    UiPlan,
    UiStep,
    ValidationPlan,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from alpha.models.gateway import ModelRoute
from alpha.models.structured import InferenceError, StructuredInference

SYSTEM = """You write the acceptance checks for a small App before it is built. Alpha's builder will implement the App to satisfy your checks, and Alpha runs them itself against the built App: it calls the App's actions for real and reads what was stored, and it drives the App's screen in a real browser. You never see the App's code; you define what counts as working.

Rules:
- Use the brief's action ids and collection and field names exactly (lowercase snake_case). If the brief lacks one you need, choose a clear snake_case name and use it consistently.
- Write 2 to 4 behaviour scenarios that cover the primary journey, plus one refused case (an empty or invalid input with "expect": "failed", followed by a records step showing nothing was stored).
- After every action that should save something, add a records step that reads storage: "includes" lists field values the scenario supplied (subset match), and "count" when you are certain of it. Never check storage by trusting an action's output.
- Action inputs are flat JSON objects whose keys are the action's inputs. Outputs are matched as subsets; only assert values the App cannot choose freely. An action that creates a record should return at least {"id", "revision"}; to act on it later use {"$ref": "<step id>.output.id"}.
- Dates: use {"$today": 0} for today (and -1 for yesterday) wherever the App records a date for the person. Never assert an exact value that comes from a model estimate; assert only that the record exists with the values the person typed.
- Only when the brief's surfaces include "custom_ui", add "ui": the screen's primary interaction addressed by short visible labels ("fill" a field by its label, then "press" Enter or "click" a button by its name), what it must save ("saved", a records step), text it must then show ("shows"), and 1 or 2 "seed" invoke steps creating sample data (one with a long text value) plus "seed_shows". Choose plain labels a person would expect, such as "Food" or "Title"; the builder will use exactly these. Without "custom_ui", set "ui" to null.
- Every step id is unique within its scenario, lowercase snake_case.
- Also give app_name: two to four plain words naming the App for the person.

Output only the structured object."""


class PlanDraft(BaseModel):
    """What the planner model returns."""

    model_config = ConfigDict(extra="forbid")

    app_name: str = Field(min_length=1, max_length=60)
    validation_plan: ValidationPlan


@dataclass(frozen=True)
class AcceptancePlan:
    app_name: str
    plan: ValidationPlan
    source: str  # "model" or "brief_examples"
    notes: list[str]


class PlanningFailed(Exception):
    pass


def wants_ui(brief: SolutionBrief) -> bool:
    return Surface.CUSTOM_UI in brief.surfaces


def consistency_problems(plan: ValidationPlan, brief: SolutionBrief) -> list[str]:
    """Checks a plan must pass before anything is built from it."""
    problems: list[str] = []
    for scenario in plan.scenarios:
        seen: set[str] = set()
        for step in scenario.steps:
            refs = re.findall(r'"\$ref":\s*"([a-z0-9_]+)\.', json.dumps(step.model_dump()))
            for ref in refs:
                if ref not in seen:
                    problems.append(f"{scenario.id}.{step.id} refers to {ref!r} before it runs")
            seen.add(step.id)
        if not any(isinstance(s, RecordsStep) for s in scenario.steps) and any(
            a.effect_class == "local_write" for a in brief.actions
        ):
            problems.append(f"scenario {scenario.id} never reads storage")
    if wants_ui(brief) and plan.ui is None:
        problems.append("the brief asks for a screen but the plan has no ui checks")
    if not wants_ui(brief) and plan.ui is not None:
        problems.append("the plan checks a screen the brief does not ask for")
    return problems


def plan_prompt(brief: SolutionBrief) -> str:
    body = brief.model_dump(
        mode="json",
        include={
            "goal",
            "success_summary",
            "delivery",
            "surfaces",
            "primary_journey",
            "data_needs",
            "actions",
            "constraints",
            "acceptance_examples",
            "assumptions",
            "unavailable_capabilities",
        },
    )
    return (
        "BRIEF (what the person wants; the App must do this):\n"
        + json.dumps(body, indent=2, ensure_ascii=False)
        + "\n\nWrite the app_name and the validation_plan."
    )


def app_slug(name: str, suffix: str) -> str:
    """A stable, readable App identity: lowercase words joined by hyphens, plus a suffix."""
    words = re.findall(r"[a-z0-9]+", name.lower())[:4] or ["app"]
    base = "-".join(words)[:48].strip("-")
    if not base[0].isalpha():
        base = f"app-{base}"
    return f"{base}-{suffix}"


def plan_from_brief_examples(brief: SolutionBrief) -> ValidationPlan:
    """Deterministic plan from the brief's executable acceptance examples (fake route, and the
    fallback for examples that already name an action and input)."""
    scenarios: list[Scenario] = []
    for index, example in enumerate(brief.acceptance_examples):
        if not example.action_id or example.input is None:
            continue
        scenarios.append(
            Scenario(
                id=f"example_{index + 1}",
                description=example.description[:500],
                steps=[
                    InvokeStep(
                        id="run",
                        action=example.action_id,
                        input=example.input,
                        expect="failed" if example.kind == "failure" else "succeeded",
                        output=example.expected if example.kind != "failure" else None,
                    )
                ],
            )
        )
    if not scenarios:
        raise PlanningFailed("the brief has no executable acceptance example")
    return ValidationPlan(scenarios=scenarios)


def _fake_notes_ui() -> UiPlan:
    """UI checks for the neutral notes fixture (control route only)."""
    return UiPlan(
        primary=[
            UiStep(kind="fill", label="Note", text="Buy milk"),
            UiStep(kind="press", key="Enter"),
        ],
        saved=RecordsStep(id="saved", collection="notes", includes=[{"title": "Buy milk"}]),
        shows=["Buy milk"],
        seed=[
            InvokeStep(
                id="long",
                action="add_note",
                input={
                    "title": "Call the plumber about the kitchen sink leak before Friday afternoon"
                },
            )
        ],
        seed_shows=["Call the plumber"],
    )


class AcceptancePlanner:
    def __init__(self, inference: StructuredInference) -> None:
        self._inference = inference

    def plan(self, brief: SolutionBrief, route: ModelRoute, scope_ref: str) -> AcceptancePlan:
        if route.route_id == "fake":
            return self._fake(brief)
        try:
            result = self._inference.call(
                route,
                system=SYSTEM,
                prompt=plan_prompt(brief),
                schema=PlanDraft.model_json_schema(),
                scope_kind="acceptance_plan",
                scope_ref=scope_ref,
            )
            draft = PlanDraft.model_validate(result.output)
        except (InferenceError, ValidationError) as exc:
            raise PlanningFailed(f"the checks could not be written: {str(exc)[:300]}") from None
        problems = consistency_problems(draft.validation_plan, brief)
        if problems:
            raise PlanningFailed("the checks are inconsistent: " + "; ".join(problems[:5]))
        return AcceptancePlan(draft.app_name, draft.validation_plan, "model", [])

    def _fake(self, brief: SolutionBrief) -> AcceptancePlan:
        plan = plan_from_brief_examples(brief)
        if wants_ui(brief) and any(a.id == "add_note" for a in brief.actions):
            plan = plan.model_copy(update={"ui": _fake_notes_ui()})
        name = brief.goal.split(",")[0][:40] or "My App"
        return AcceptancePlan(
            name, plan, "brief_examples", ["fake route: plan from the brief's examples"]
        )
