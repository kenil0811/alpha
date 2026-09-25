"""ctx.artifacts: immutable files the App produces (reports, exports, transformed documents).

The platform stores the bytes, computes their digest and records where they came from. You get a
handle, never a filesystem path. Artifacts belong to the App that made them.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from alpha_sdk._channel import Transport

if TYPE_CHECKING:
    from alpha_sdk.models import ModelResult


@dataclass(frozen=True)
class ArtifactRef:
    id: str
    display_name: str
    media_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    provenance: dict[str, Any]

    @classmethod
    def from_wire(cls, data: Mapping[str, Any]) -> ArtifactRef:
        return cls(
            id=str(data["artifact_id"]),
            display_name=str(data["display_name"]),
            media_type=str(data["media_type"]),
            size_bytes=int(data["size_bytes"]),
            sha256=str(data["sha256"]),
            created_at=datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00")),
            provenance=dict(data.get("provenance") or {}),
        )


class Artifacts:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def create(
        self,
        display_name: str,
        content: bytes | str,
        *,
        media_type: str = "text/plain",
        derived_from: Iterable[ArtifactRef | str] = (),
        model_results: Iterable[ModelResult] = (),
    ) -> ArtifactRef:
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        args: dict[str, Any] = {
            "display_name": display_name,
            "media_type": media_type,
            "content_b64": base64.b64encode(data).decode("ascii"),
            "derived_from": [a.id if isinstance(a, ArtifactRef) else str(a) for a in derived_from],
            "model_call_ids": [m.call_id for m in model_results],
        }
        return ArtifactRef.from_wire(self._t.call("artifacts.create", args))

    def get(self, artifact_id: str) -> ArtifactRef:
        return ArtifactRef.from_wire(self._t.call("artifacts.get", {"artifact_id": artifact_id}))

    def read(self, artifact_id: str) -> bytes:
        data = self._t.call("artifacts.read", {"artifact_id": artifact_id})
        return base64.b64decode(str(data["content_b64"]))

    def read_text(self, artifact_id: str) -> str:
        return self.read(artifact_id).decode("utf-8")
