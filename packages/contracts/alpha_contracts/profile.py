"""The person's profile: facts about them that modules and the assistant share.

A fact is one claimed attribute (a field and a value) with where it came from, how sure the
source was, and what it replaced. Facts are never edited in place: a correction is a new fact
that supersedes the old one, so the history stays whole and every claim is inspectable. Only
the person accepts a suggested fact; a module or the assistant can only propose one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from alpha_contracts.runs import ContractModel

FactProvenance = Literal["person", "module", "assistant", "inferred"]
FactState = Literal["accepted", "suggested", "rejected", "retracted"]

FIELD_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"


class ProfileFact(ContractModel):
    fact_id: str
    # A plain snake_case name: degree, university, skills, target_roles, location, dietary_goal.
    field: str = Field(pattern=FIELD_PATTERN)
    value: Any
    provenance: FactProvenance
    # Who said so: an app id, a conversation id, or "person".
    source: str = Field(default="person", max_length=120)
    # A sentence for the person: why this is believed.
    why: str | None = Field(default=None, max_length=400)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    state: FactState
    supersedes: str | None = None
    recorded_at: str
    # "person" for a fact about them in general; "project:<id>" for one that only holds
    # inside that project.
    scope: str = Field(default="person", max_length=80)


class ProfileView(ContractModel):
    """The living profile: the current accepted fact per field, plus what awaits a yes."""

    facts: list[ProfileFact]
    suggestions: list[ProfileFact]


class FactClaim(ContractModel):
    """What a module or the assistant sends when it learns something about the person."""

    field: str = Field(pattern=FIELD_PATTERN)
    value: Any
    why: str | None = Field(default=None, max_length=400)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class FactLookup(ContractModel):
    field: str = Field(pattern=FIELD_PATTERN)
