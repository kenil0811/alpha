"""Skills: reusable abilities that live outside any module.

A skill is how Alpha does one kind of job for the person: "find people to cold call in an
industry", "summarise a week of a module's entries", "check a supplier's prices". It has a
title, a plain description, the inputs it needs, what it produces, the sources it may read and
the way it works (a procedure in plain steps the assistant follows with its tools, or a pointer
to a module's action). The assistant and the avatar run skills directly; modules may use them;
they are listed on the Intelligence page.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from alpha_contracts.runs import ContractModel

SKILL_ID_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
SkillKind = Literal["procedure", "code"]
SkillState = Literal["active", "retired"]


class SkillInput(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,47}$")
    description: str = Field(default="", max_length=300)
    required: bool = True


class SkillSpec(ContractModel):
    id: str = Field(pattern=SKILL_ID_PATTERN)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    kind: SkillKind = "procedure"
    # Procedure skills: the way it works, in plain steps the assistant follows with its tools
    # (web search and reading, the person's modules, the profile). Code skills: which module
    # action does the job.
    instructions: str = Field(default="", max_length=6000)
    module: str | None = Field(default=None, max_length=64)
    action: str | None = Field(default=None, max_length=64)
    inputs: list[SkillInput] = Field(default_factory=list, max_length=8)
    produces: str = Field(default="", max_length=400)
    # Sites or kinds of source it may read (plain words: "LinkedIn", "company websites").
    sources: list[str] = Field(default_factory=list, max_length=12)
    created_by: Literal["person", "assistant"] = "person"
    state: SkillState = "active"
    created_at: str
    updated_at: str


class SkillDraft(ContractModel):
    """What a person (or the assistant) sends to make or change a skill."""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    kind: SkillKind = "procedure"
    instructions: str = Field(default="", max_length=6000)
    module: str | None = Field(default=None, max_length=64)
    action: str | None = Field(default=None, max_length=64)
    inputs: list[SkillInput] = Field(default_factory=list, max_length=8)
    produces: str = Field(default="", max_length=400)
    sources: list[str] = Field(default_factory=list, max_length=12)


class SkillRun(ContractModel):
    run_id: str
    skill_id: str
    inputs: dict[str, Any]
    state: Literal["running", "done", "failed"]
    summary: str = ""
    # What the skill produced: rows a person can read (and a module can save).
    items: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    started_at: str
    finished_at: str | None = None
