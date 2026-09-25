"""Artifact metadata (Current Release Specification §8).

Bytes are staged with limits, sealed and content-addressed, then registered. The storage
reference is logical (`blob:sha256:<hex>`); filesystem paths never leave Core. Artifacts are not
shared across owners or sent to models automatically.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from alpha_contracts.profiles import Sha256Hex
from alpha_contracts.runs import ContractModel

# Media types accepted in this release. Everything else is rejected at staging.
ALLOWED_MEDIA_TYPES: frozenset[str] = frozenset(
    {
        "text/plain",
        "text/csv",
        "text/markdown",
        "application/json",
        "application/pdf",
        "image/png",
        "image/jpeg",
    }
)


class ArtifactOwner(ContractModel):
    kind: Literal["app", "task"]
    id: str = Field(min_length=1)


class ArtifactProvenance(ContractModel):
    created_by: Literal["app_run", "task_run", "user"]
    run_id: str | None = None
    action_id: str | None = None
    version_id: str | None = None
    package_sha256: Sha256Hex | None = None
    derived_from: list[str] = Field(default_factory=list)
    model_call_ids: list[str] = Field(default_factory=list)


class Artifact(ContractModel):
    contract_version: Literal["0.2"] = "0.2"
    artifact_id: str = Field(min_length=1)
    owner: ArtifactOwner
    media_type: str
    display_name: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(ge=0)
    sha256: Sha256Hex
    provenance: ArtifactProvenance
    created_at: datetime
    retention: Literal["until_deleted"] = "until_deleted"
    storage_ref: str = Field(pattern=r"^blob:sha256:[0-9a-f]{64}$")


class CreateArtifact(ContractModel):
    display_name: str = Field(min_length=1, max_length=200)
    media_type: str = Field(min_length=1, max_length=100)
    content_b64: str
    derived_from: list[str] = Field(default_factory=list, max_length=20)
    model_call_ids: list[str] = Field(default_factory=list, max_length=20)


class ArtifactRef(ContractModel):
    artifact_id: str = Field(min_length=1, max_length=64)
