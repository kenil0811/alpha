"""Artifact staging, sealing and registration (Current Release Specification §8).

Bytes are written to a private staging file with a size limit, fsynced and hashed, then moved to
a content-addressed read-only blob and only then registered in the control store. Reads verify
the digest again. Metadata carries owner and provenance; the storage reference is logical and no
filesystem path leaves Core. An artifact is visible only to its owner (the trusted shell reads
through its own route).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import stat
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from alpha_contracts.artifacts import (
    ALLOWED_MEDIA_TYPES,
    Artifact,
    ArtifactOwner,
    ArtifactProvenance,
    CreateArtifact,
)

from alpha.capabilities.errors import OperationFailed, invalid, limit, not_found
from alpha.storage.control_store import ControlStore, new_id, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id TEXT PRIMARY KEY,
    owner_kind TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    display_name TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    provenance_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    retention TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS artifacts_owner_idx ON artifacts(owner_kind, owner_id, created_at);
"""

MAX_ARTIFACT_BYTES = 10 * 1024 * 1024


class ArtifactService:
    def __init__(
        self, store: ControlStore, root: Path, max_bytes: int = MAX_ARTIFACT_BYTES
    ) -> None:
        self._store = store
        self._root = root
        self._blobs = root / "blobs" / "sha256"
        self._staging = root / "staging"
        self._max = max_bytes
        self._blobs.mkdir(parents=True, exist_ok=True)
        self._staging.mkdir(parents=True, exist_ok=True)
        store.execute_script(_SCHEMA)

    def _blob_path(self, digest: str) -> Path:
        return self._blobs / digest[:2] / digest

    def reconcile_on_startup(self) -> dict[str, list[str]]:
        """Remove abandoned staging files and blobs no registered artifact references."""
        removed_staging = []
        for path in self._staging.iterdir():
            path.unlink(missing_ok=True)
            removed_staging.append(path.name)
        referenced = {
            r["sha256"] for r in self._store.query("SELECT DISTINCT sha256 FROM artifacts")
        }
        removed_blobs = []
        for path in self._blobs.glob("*/*"):
            if path.name not in referenced:
                path.chmod(stat.S_IRUSR | stat.S_IWUSR)
                path.unlink(missing_ok=True)
                removed_blobs.append(path.name)
        return {"staging": removed_staging, "unreferenced_blobs": removed_blobs}

    def create(
        self, owner: ArtifactOwner, request: CreateArtifact, provenance: ArtifactProvenance
    ) -> Artifact:
        if request.media_type not in ALLOWED_MEDIA_TYPES:
            raise invalid(
                f"{request.media_type!r} is not a supported artifact type",
                supported=sorted(ALLOWED_MEDIA_TYPES),
            )
        if len(request.content_b64) > (self._max * 4) // 3 + 8:
            raise limit(f"artifacts are limited to {self._max} bytes")
        try:
            data = base64.b64decode(request.content_b64.encode("ascii"), validate=True)
        except (binascii.Error, ValueError, UnicodeEncodeError):
            raise invalid("artifact content is not valid base64") from None
        if len(data) > self._max:
            raise limit(f"artifacts are limited to {self._max} bytes")
        for source_id in request.derived_from:
            self.get(owner, source_id)  # must exist and belong to the same owner
        staging = self._staging / f"{uuid.uuid4().hex}.part"
        fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            digest = hashlib.sha256(staging.read_bytes()).hexdigest()
            if digest != hashlib.sha256(data).hexdigest():
                raise OperationFailed("internal_error", "staged artifact bytes did not match")
            blob = self._blob_path(digest)
            blob.parent.mkdir(parents=True, exist_ok=True)
            if blob.exists():
                if hashlib.sha256(blob.read_bytes()).hexdigest() != digest:
                    raise OperationFailed("internal_error", "an existing blob failed verification")
                staging.unlink()
            else:
                os.chmod(staging, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
                os.replace(staging, blob)
                dir_fd = os.open(blob.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            if staging.exists():
                staging.unlink()
        artifact = Artifact(
            artifact_id=new_id("art"),
            owner=owner,
            media_type=request.media_type,
            display_name=request.display_name,
            size_bytes=len(data),
            sha256=digest,
            provenance=provenance,
            created_at=utc_now(),
            storage_ref=f"blob:sha256:{digest}",
        )
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO artifacts(artifact_id, owner_kind, owner_id, media_type,
                   display_name, size_bytes, sha256, provenance_json, created_at, retention)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    artifact.artifact_id,
                    owner.kind,
                    owner.id,
                    artifact.media_type,
                    artifact.display_name,
                    artifact.size_bytes,
                    artifact.sha256,
                    provenance.model_dump_json(),
                    artifact.created_at.isoformat().replace("+00:00", "Z"),
                    artifact.retention,
                ),
            )
        return artifact

    def get(self, owner: ArtifactOwner | None, artifact_id: str) -> Artifact:
        """Metadata for an artifact. With an owner, other owners' artifacts are not found."""
        rows = self._store.query("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,))
        if not rows or (
            owner is not None
            and (rows[0]["owner_kind"] != owner.kind or rows[0]["owner_id"] != owner.id)
        ):
            raise not_found(f"no artifact {artifact_id}", artifact_id=artifact_id)
        return _row_to_artifact(rows[0])

    def read(self, owner: ArtifactOwner | None, artifact_id: str) -> tuple[Artifact, bytes]:
        artifact = self.get(owner, artifact_id)
        blob = self._blob_path(artifact.sha256)
        try:
            data = blob.read_bytes()
        except FileNotFoundError:
            raise OperationFailed(
                "internal_error", f"artifact {artifact_id} bytes are missing"
            ) from None
        if hashlib.sha256(data).hexdigest() != artifact.sha256 or len(data) != artifact.size_bytes:
            raise OperationFailed("internal_error", f"artifact {artifact_id} failed verification")
        return artifact, data

    def list_for_owner(self, owner: ArtifactOwner, limit_: int = 100) -> list[Artifact]:
        rows = self._store.query(
            """SELECT * FROM artifacts WHERE owner_kind = ? AND owner_id = ?
               ORDER BY created_at DESC LIMIT ?""",
            (owner.kind, owner.id, limit_),
        )
        return [_row_to_artifact(r) for r in rows]


def _row_to_artifact(row: Any) -> Artifact:
    return Artifact(
        artifact_id=row["artifact_id"],
        owner=ArtifactOwner(kind=row["owner_kind"], id=row["owner_id"]),
        media_type=row["media_type"],
        display_name=row["display_name"],
        size_bytes=row["size_bytes"],
        sha256=row["sha256"],
        provenance=ArtifactProvenance.model_validate(json.loads(row["provenance_json"])),
        created_at=datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")),
        retention=row["retention"],
        storage_ref=f"blob:sha256:{row['sha256']}",
    )
