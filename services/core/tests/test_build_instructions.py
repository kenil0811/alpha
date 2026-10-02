"""The builder hears what the person said as requirements, apart from the model's defaults."""

from __future__ import annotations

from alpha.solutions.creation import build_instructions
from alpha_contracts.briefs import Assumption, SolutionBrief


def test_answers_are_requirements_and_model_choices_are_defaults() -> None:
    brief = SolutionBrief.model_construct(
        goal="Help a professor manage grading and spot students needing attention.",
        success_summary="Every course's grading and at-risk students in one place.",
        primary_journey=[],
        data_needs=[],
        actions=[],
        recurrence=None,
        constraints=[],
        assumptions=[
            Assumption(text="The person is a professor using Canvas.", source="user_answer"),
            Assumption(text="Refreshes run on demand.", source="model_default"),
        ],
        unavailable_capabilities=[],
    )
    text = build_instructions(brief, with_ui=False, app_name="Teaching")
    assert "The goal, in the person's terms: Help a professor" in text
    told, defaults = text.split("What the person told Alpha")[1].split("Defaults chosen")
    assert "professor using Canvas" in told and "on demand" not in told
    assert "Refreshes run on demand." in defaults
