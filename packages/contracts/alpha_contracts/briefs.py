"""SolutionBrief contract (Current Release Specification section 2).

All listed top-level fields are required. Empty arrays mean deliberately none, not an unasked
or unknown answer; unresolved material choices belong in open_questions/assumptions. The brief
is not an authorization grant: it never carries credentials, grant ids or resolved paths.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from alpha_contracts.runs import ContractModel


class Delivery(StrEnum):
    ANSWER = "answer"
    TASK = "task"
    APP = "app"


class Surface(StrEnum):
    CONVERSATION = "conversation"
    ARTIFACT = "artifact"
    CUSTOM_UI = "custom_ui"
    BACKGROUND = "background"
    EXTERNAL_UPDATE = "external_update"


class ContextInput(ContractModel):
    ref: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    source: str = Field(min_length=1)
    digest: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")


class JourneyStep(ContractModel):
    action: str = Field(min_length=1)
    expected_result: str = Field(min_length=1)


class FieldNeed(ContractModel):
    name: str = Field(min_length=1)
    kind: Literal["text", "number", "boolean", "date", "datetime", "choice", "reference", "json"]
    description: str = ""
    required: bool = True


class DataNeed(ContractModel):
    collection: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    fields: list[FieldNeed]
    provenance: str = "user"
    retention: str = "until the user deletes it"


class ActionIntent(ContractModel):
    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    effect_class: Literal["none", "local_write", "external_read", "external_write"] = "none"
    required_capabilities: list[str] = Field(default_factory=list)


class Recurrence(ContractModel):
    type: Literal["interval", "daily", "weekly"]
    description: str = Field(min_length=1)
    timezone: str = Field(min_length=1)


class AcceptanceExample(ContractModel):
    description: str = Field(min_length=1)
    action_id: str | None = None
    input: dict[str, Any] | None = None
    expected: dict[str, Any] | None = None
    kind: Literal["success", "failure", "boundary"] = "success"


class Assumption(ContractModel):
    text: str = Field(min_length=1)
    source: Literal["model_default", "user_answer", "user_correction"] = "model_default"
    turn_ref: str | None = None


class OpenQuestion(ContractModel):
    id: str = Field(min_length=1, max_length=64)
    question: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    why_it_matters: str = Field(min_length=1)


class SolutionBrief(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    conversation_id: str = Field(min_length=1)
    created_at: datetime
    goal: str = Field(min_length=1)
    success_summary: str = Field(min_length=1)
    delivery: Delivery
    surfaces: list[Surface]
    inputs: list[ContextInput]
    primary_journey: list[JourneyStep]
    data_needs: list[DataNeed]
    actions: list[ActionIntent]
    recurrence: Recurrence | None
    constraints: list[str]
    acceptance_examples: list[AcceptanceExample]
    assumptions: list[Assumption]
    open_questions: list[OpenQuestion]
    unavailable_capabilities: list[str]
    selected_context_snapshot_id: str = Field(min_length=1)
    supersedes_revision: int | None = None


class Interpretation(ContractModel):
    """Short plain-language reading shown to the user (UX specification section 3)."""

    outcome: str = Field(min_length=1)
    main_input: str = Field(min_length=1)
    useful_result: str = Field(min_length=1)
    important_assumptions: list[str] = Field(default_factory=list)
