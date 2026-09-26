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
from typing import Any

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
- Action inputs are flat JSON objects whose keys are the action's inputs. Outputs are matched as subsets; only assert values the App cannot choose freely. To require a key whose value the App chooses, write {"$any": true} as its value (never "*"). An action that creates a record should return at least {"id": {"$any": true}, "revision": {"$any": true}}; to act on it later use {"$ref": "<step id>.output.id"}.
- Dates: use {"$today": 0} for today (and -1 for yesterday) wherever the App records a date for the person. Never assert an exact value that comes from a model estimate; assert only that the record exists with the values the person typed.
- Assert exact values for everything computed from values the scenario itself supplied: totals, counts, averages, remaining time, what fits and what does not. Use {"$any": true} only for values the App chooses freely (ids, revisions, timestamps) or that come from a model estimate.
- Missing data is unknown, not zero. An average over days (or weeks, or items) counts only the periods that have entries, and the result says how many periods had entries; a value the person enters as 0 is a real zero. When the brief has such a figure, add a scenario with a gap and assert both numbers exactly.
- If an action fills a value from a model estimate, add one scenario where that invoke step has "model": "unavailable" (the platform makes the model fail). Then require an honest outcome: either "expect": "failed" followed by a records step showing nothing new was stored, or a stored record whose estimated field is null (null means unknown). Never accept a number there. Also show that a value the person types themselves is saved without the model.
- Only when the brief's surfaces include "custom_ui", add "ui": the screen's primary interaction addressed by short visible labels ("fill" a field by its label, then "press" Enter or "click" a button by its name), what it must save ("saved", a records step), text it must then show ("shows"), and 1 or 2 "seed" invoke steps creating sample data (one with a long text value) plus "seed_shows". Choose plain labels a person would expect, such as "Food" or "Title"; the builder will use exactly these. Without "custom_ui", set "ui" to null.
- Cover the whole brief: every action in it runs successfully in some scenario; for an action that computes something (effect "none"), assert at least one exact value it returns; after each action that saves, changes or deletes data, a records step in the same scenario reads back what is stored.
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
    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems = problems or []


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
    return problems + coverage_problems(plan, brief)


def _fixed_value(value: Any) -> bool:
    """True when an expected output pins at least one value (not only "any value")."""
    if isinstance(value, dict):
        if set(value) == {"$any"}:
            return False
        if set(value) <= {"$ref", "$today"}:
            return True
        return any(_fixed_value(v) for v in value.values())
    if isinstance(value, list):
        return any(_fixed_value(v) for v in value)
    return True


def coverage_problems(plan: ValidationPlan, brief: SolutionBrief) -> list[str]:
    """Every material outcome in the brief has a meaningful assertion (M1 review finding F05):
    each action runs successfully, what a computing action returns is checked with real values,
    each model-using action is also run with the model unavailable, and what each writing action
    stores is read back. Judged by actions, not collection names: a brief names its data for
    people ("Food entries"), a plan by storage name ("food_entries") (found in M1-R07)."""
    problems: list[str] = []
    steps = [s for sc in plan.scenarios for s in sc.steps]
    invokes: dict[str, list[InvokeStep]] = {}
    for step in steps:
        if isinstance(step, InvokeStep):
            invokes.setdefault(step.action, []).append(step)
    for action in brief.actions:
        mine = invokes.get(action.id, [])
        if not any(s.expect == "succeeded" and s.model == "normal" for s in mine):
            problems.append(f"the plan never runs {action.id} successfully")
            continue
        if (
            action.effect_class == "none"
            and "models" not in action.required_capabilities
            and not any(s.output is not None and _fixed_value(s.output) for s in mine)
        ):
            problems.append(f"the plan never checks a value {action.id} computes")
        if "models" in action.required_capabilities and not any(s.model != "normal" for s in mine):
            problems.append(f"the plan never runs {action.id} with the model unavailable")
        if action.effect_class == "local_write" and not _read_back(plan, action.id):
            problems.append(f"the plan never reads back what {action.id} stores")
    return problems


def _read_back(plan: ValidationPlan, action_id: str) -> bool:
    """Some scenario runs the action successfully and then reads the stored records."""
    for scenario in plan.scenarios:
        wrote = False
        for step in scenario.steps:
            if isinstance(step, InvokeStep) and step.action == action_id:
                wrote = wrote or step.expect == "succeeded"
            elif wrote and isinstance(step, RecordsStep):
                return True
    return False


def _star_to_any(value: Any) -> tuple[Any, int]:
    """Replace the literal "*" a model writes for "any value" with {"$any": true}."""
    if value == "*":
        return {"$any": True}, 1
    if isinstance(value, dict):
        pairs = [(k, _star_to_any(v)) for k, v in value.items()]
        return {k: v for k, (v, _) in pairs}, sum(n for _, (_, n) in pairs)
    if isinstance(value, list):
        items = [_star_to_any(v) for v in value]
        return [v for v, _ in items], sum(n for _, n in items)
    return value, 0


def normalize_expectations(plan: ValidationPlan) -> tuple[ValidationPlan, int]:
    """Expected outputs and stored values use {"$any": true} for "any value". Found in G1: the
    planner wrote {"id": "*"}, which the matcher compares literally, so every check failed and
    no honest repair could pass. Inputs are left alone ("*" there is data)."""
    data = plan.model_dump(mode="json")
    changed = 0

    def fix(step: dict[str, Any]) -> None:
        nonlocal changed
        for key in ("output", "includes"):
            if step.get(key) is not None:
                step[key], n = _star_to_any(step[key])
                changed += n

    for scenario in data["scenarios"]:
        for step in scenario["steps"]:
            fix(step)
    if data.get("ui"):
        if data["ui"].get("saved"):
            fix(data["ui"]["saved"])
        for step in data["ui"].get("seed") or []:
            fix(step)
    return ValidationPlan.model_validate(data), changed


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
        prompt = plan_prompt(brief)
        problems: list[str] = []
        notes: list[str] = []
        for attempt in (1, 2):  # one repair of an incomplete plan, then stop
            try:
                result = self._inference.call(
                    route,
                    system=SYSTEM,
                    prompt=prompt,
                    schema=PlanDraft.model_json_schema(),
                    scope_kind="acceptance_plan",
                    scope_ref=scope_ref,
                )
                draft = PlanDraft.model_validate(result.output)
            except (InferenceError, ValidationError) as exc:
                raise PlanningFailed(f"the checks could not be written: {str(exc)[:300]}") from None
            plan, replaced = normalize_expectations(draft.validation_plan)
            if replaced:
                notes.append(f'{replaced} "*" expectation(s) read as any value')
            problems = consistency_problems(plan, brief)
            if not problems:
                if attempt == 2:
                    notes.append("the first plan was incomplete and was rewritten once")
                return AcceptancePlan(draft.app_name, plan, "model", notes)
            prompt = (
                plan_prompt(brief)
                + "\n\nYOUR PREVIOUS PLAN (fix it; keep what was right):\n"
                + json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
                + "\n\nIT HAD THESE PROBLEMS:\n- "
                + "\n- ".join(problems)
            )
        raise PlanningFailed("the checks are incomplete", problems[:5])

    def _fake(self, brief: SolutionBrief) -> AcceptancePlan:
        plan = plan_from_brief_examples(brief)
        if wants_ui(brief) and any(a.id == "add_note" for a in brief.actions):
            plan = plan.model_copy(update={"ui": _fake_notes_ui()})
        name = brief.goal.split(",")[0][:40] or "My App"
        return AcceptancePlan(
            name, plan, "brief_examples", ["fake route: plan from the brief's examples"]
        )
