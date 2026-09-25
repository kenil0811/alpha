"""Dependency profiles and the per-Version dependency manifest (Current Release Specification §11).

These are serialized compatibility records, not a resolver. uv produces the lock; the trusted
build path records identities; Core verifies them. The manifest digest is SHA-256 over UTF-8
compact JSON with recursively sorted keys, sorted locks/packages and no NaN, omitting
`manifest_sha256` itself. The profile ID is derived from the same canonical content without the
ID, so identical inputs always produce the same identity and any change produces a new one.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Any

from pydantic import Field, field_validator

from alpha_contracts.runs import ContractModel

Sha256Hex = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class ProfileKind(StrEnum):
    PYTHON_RUNTIME = "python_runtime"
    UI_BUILD = "ui_build"


class ProfileRole(StrEnum):
    APP_TASK_COMPUTE = "app_task_compute"
    TRUSTED_TOOL = "trusted_tool"


class ProfileTarget(ContractModel):
    os: str = Field(min_length=1)
    arch: str = Field(min_length=1)
    python_implementation: str | None = None
    python_version: str | None = None
    python_abi: str | None = None
    interpreter_build: str | None = None
    ui_toolchain: dict[str, str] | None = None


class LockRef(ContractModel):
    path: str = Field(min_length=1, max_length=200)
    sha256: Sha256Hex

    @field_validator("path")
    @classmethod
    def _relative(cls, value: str) -> str:
        if value.startswith("/") or ".." in value.split("/") or "\\" in value:
            raise ValueError("lock paths are relative, inside the profile definition")
        return value


class PackagePin(ContractModel):
    name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=64)
    artifact_sha256: Sha256Hex
    artifact: str | None = Field(default=None, max_length=200)


class ProfileCompatibility(ContractModel):
    contract_version: str
    sdk_version: str | None = None
    worker_protocol: int | None = None
    kit_version: str | None = None
    bridge_version: str | None = None


class DependencyProfile(ContractModel):
    profile_id: str = Field(pattern=r"^[a-z]+prof-[0-9a-f]{20}$")
    kind: ProfileKind
    role: ProfileRole
    target: ProfileTarget
    locks: list[LockRef]
    packages: list[PackagePin]
    compatibility: ProfileCompatibility
    manifest_sha256: Sha256Hex


class SdkPin(ContractModel):
    name: str
    version: str
    artifact_sha256: Sha256Hex


class UiBuildRef(ContractModel):
    profile_id: str
    manifest_sha256: Sha256Hex
    kit: PackagePin
    bridge: PackagePin


class DependencyManifest(ContractModel):
    """Platform-produced per-Version record. No local paths, grants or secrets."""

    runtime_profile_id: str
    runtime_profile_manifest_sha256: Sha256Hex
    sdk: SdkPin
    modules: list[PackagePin] = Field(default_factory=list)
    ui_build: UiBuildRef | None = None


def canonical_json(value: Any) -> bytes:
    """UTF-8 compact JSON with recursively sorted object keys; NaN/Infinity are rejected."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _normalized(content: dict[str, Any]) -> dict[str, Any]:
    body = {k: v for k, v in content.items() if k != "manifest_sha256"}
    if isinstance(body.get("locks"), list):
        body["locks"] = sorted(body["locks"], key=lambda item: str(item.get("path")))
    if isinstance(body.get("packages"), list):
        body["packages"] = sorted(body["packages"], key=lambda item: str(item.get("name")))
    return body


def manifest_digest(content: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(_normalized(content))).hexdigest()


def derive_profile_id(content: dict[str, Any], prefix: str = "py") -> str:
    body = {k: v for k, v in _normalized(content).items() if k != "profile_id"}
    return f"{prefix}prof-{hashlib.sha256(canonical_json(body)).hexdigest()[:20]}"


def seal_profile(content: dict[str, Any], prefix: str = "py") -> DependencyProfile:
    """Assign the derived ID and digest to a profile definition and validate it.

    Identity is computed over the validated, fully populated JSON form (defaults included), the
    same form `verify_profile` recomputes from, so a stored manifest always re-verifies."""
    draft = DependencyProfile.model_validate(
        {**content, "profile_id": f"{prefix}prof-{'0' * 20}", "manifest_sha256": "0" * 64}
    )
    body = draft.model_dump(mode="json")
    body["profile_id"] = derive_profile_id(body, prefix)
    body["manifest_sha256"] = manifest_digest(body)
    return DependencyProfile.model_validate(body)


def verify_profile(profile: DependencyProfile, prefix: str | None = None) -> list[str]:
    """Return the reasons a profile's identity does not match its content (empty if intact).
    The ID prefix ("py", "ui") is taken from the profile ID unless given."""
    prefix = prefix if prefix is not None else profile.profile_id.split("prof-", 1)[0]
    content = profile.model_dump(mode="json")
    problems: list[str] = []
    if manifest_digest(content) != profile.manifest_sha256:
        problems.append("manifest_sha256 does not match the manifest content")
    if derive_profile_id(content, prefix) != profile.profile_id:
        problems.append("profile_id does not match the manifest content")
    return problems
