"""What the assistant model must return each turn (validated structured output)."""

from __future__ import annotations

from typing import Any

from alpha_contracts.briefs import (
    AcceptanceExample,
    ActionIntent,
    DataNeed,
    Delivery,
    Interpretation,
    JourneyStep,
    OpenQuestion,
    Recurrence,
    Surface,
)
from pydantic import BaseModel, ConfigDict, Field


class BriefDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1)
    success_summary: str = Field(min_length=1)
    surfaces: list[Surface]
    primary_journey: list[JourneyStep]
    data_needs: list[DataNeed]
    actions: list[ActionIntent]
    recurrence: Recurrence | None = None
    constraints: list[str]
    acceptance_examples: list[AcceptanceExample]
    unavailable_capabilities: list[str]


class AssistantTurnOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delivery: Delivery
    interpretation: Interpretation
    reply: str = Field(min_length=1, description="What to say to the user, in plain language.")
    questions: list[OpenQuestion] = Field(max_length=3)
    assumptions: list[str]
    brief_draft: BriefDraft | None = None


def turn_output_schema() -> dict[str, Any]:
    """JSON Schema for the model. Pydantic's schema is used as-is; the route supports $defs."""
    schema = AssistantTurnOutput.model_json_schema()
    return schema
