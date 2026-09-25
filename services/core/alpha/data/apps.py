"""Minimum App ownership records and Version sealing (F05 step 1).

Installing a package: validate `app.yaml` against the source contract, check the runtime profile
and SDK pins, copy only allowed files into staging, compute package.index.json and
dependency.manifest.json, seal read-only, publish atomically as an immutable Version, resolve
every handler in a disposable worker running the exact profile, then register collections and
the App's current Version/Release rows.

Release activation, expected-current-release checks and data-schema migration belong to F08/F10;
the release row written here is the minimal pointer an App run's owner identity needs.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from alpha_contracts.apps import AppSource, PackageFile, PackageIndex
from alpha_contracts.profiles import DependencyManifest, SdkPin, canonical_json
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError

from alpha.capabilities.errors import conflict, invalid, not_found
from alpha.data.store import RecordService
from alpha.execution.profiles import InstalledProfile, ProfileInventory, sha256_file
from alpha.storage.control_store import ControlStore, new_id, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS apps (
    app_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    current_version_id TEXT,
    current_release_id TEXT
);
CREATE TABLE IF NOT EXISTS app_versions (
    version_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL REFERENCES apps(app_id),
    package_sha256 TEXT NOT NULL,
    source_json TEXT NOT NULL,
    dependency_manifest_json TEXT NOT NULL,
    dependency_manifest_sha256 TEXT NOT NULL,
    runtime_profile_id TEXT NOT NULL,
    location_ref TEXT NOT NULL,
    validation_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_releases (
    release_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL REFERENCES apps(app_id),
    version_id TEXT NOT NULL REFERENCES app_versions(version_id),
    kind TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

ALLOWED_SUFFIXES = {".py", ".json", ".txt", ".csv", ".md", ".yaml"}
MAX_FILE_BYTES = 1_000_000
MAX_PACKAGE_BYTES = 10_000_000
MAX_FILES = 500

# (version_dir, source, profile) -> per-action validation report from a disposable worker
HandlerValidator = Callable[[Path, AppSource, InstalledProfile], list[dict[str, Any]]]


@dataclass(frozen=True)
class AppVersion:
    app_id: str
    version_id: str
    release_id: str
    package_sha256: str
    dependency_manifest_sha256: str
    runtime_profile_id: str
    location: Path
    source: AppSource


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def _make_writable(root: Path) -> None:
    if not root.exists():
        return
    root.chmod(root.stat().st_mode | stat.S_IWUSR)
    for path in root.rglob("*"):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


def _remove(root: Path) -> None:
    _make_writable(root)
    shutil.rmtree(root, ignore_errors=True)


def _seal(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    root.chmod(root.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def load_source(package_dir: Path) -> AppSource:
    manifest = package_dir / "app.yaml"
    if not manifest.is_file() or manifest.is_symlink():
        raise invalid("the package has no app.yaml")
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise invalid(f"app.yaml is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise invalid("app.yaml must be a mapping")
    try:
        source = AppSource.model_validate(data)
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()[:10]
        ]
        raise invalid("app.yaml does not match the App contract", problems=problems) from None
    for action in source.actions:
        for label, schema in (("input", action.input_schema), ("output", action.output_schema)):
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                raise invalid(
                    f"the {label} schema of action {action.id} is not valid JSON Schema: "
                    f"{exc.message}"
                ) from None
    return source


def _collect_files(package_dir: Path) -> list[Path]:
    """Files that become part of the Version: app.yaml and src/. Rejects anything unsafe."""
    root = package_dir.resolve()
    selected: list[Path] = [package_dir / "app.yaml"]
    src = package_dir / "src"
    if not src.is_dir() or src.is_symlink():
        raise invalid("the package has no src/ directory")
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(package_dir)
        if "__pycache__" in rel.parts:
            continue
        if path.is_symlink():
            raise invalid(f"{rel.as_posix()} is a symbolic link; packages cannot contain links")
        if not path.resolve().is_relative_to(root):
            raise invalid(f"{rel.as_posix()} points outside the package")
        if path.is_dir():
            continue
        if not path.is_file():
            raise invalid(f"{rel.as_posix()} is not a regular file")
        if path.suffix not in ALLOWED_SUFFIXES:
            raise invalid(f"{rel.as_posix()} has a file type packages cannot contain")
        if path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
            raise invalid(f"{rel.as_posix()} is executable; packages cannot contain executables")
        if path.stat().st_size > MAX_FILE_BYTES:
            raise invalid(f"{rel.as_posix()} is larger than {MAX_FILE_BYTES} bytes")
        selected.append(path)
    if len(selected) > MAX_FILES:
        raise invalid(f"the package has more than {MAX_FILES} files")
    if sum(p.stat().st_size for p in selected) > MAX_PACKAGE_BYTES:
        raise invalid(f"the package is larger than {MAX_PACKAGE_BYTES} bytes")
    return selected


class AppRegistry:
    def __init__(
        self,
        store: ControlStore,
        inventory: ProfileInventory,
        records: RecordService,
        versions_root: Path,
        validator: HandlerValidator,
    ) -> None:
        self._store = store
        self._inventory = inventory
        self._records = records
        self._root = versions_root
        self._validator = validator
        store.execute_script(_SCHEMA)
        versions_root.mkdir(parents=True, exist_ok=True)

    def reconcile_on_startup(self) -> list[str]:
        """Remove staging left by an interrupted install; sealed Versions are never touched."""
        removed: list[str] = []
        for leftover in self._root.glob(".staging-*"):
            _remove(leftover)
            removed.append(leftover.name)
        return removed

    def install(self, package_dir: Path) -> AppVersion:
        source = load_source(package_dir)
        profile = self._inventory.ready(source.runtime_profile)
        sdk = next((p for p in profile.profile.packages if p.name == "alpha-sdk"), None)
        if sdk is None or source.sdk_version != sdk.version:
            raise invalid(
                f"sdk_version {source.sdk_version!r} does not match the runtime profile's SDK "
                f"{sdk.version if sdk else 'none'}"
            )
        if source.modules:
            raise invalid(
                "extra Python modules need a qualified runtime profile; the default profile has "
                f"none (requested {sorted(source.modules)})"
            )
        if source.ui is not None and source.ui.entry is not None:
            raise invalid(
                "building a UI entry into a Version arrives with the delivery loop (F08); "
                "declare views and actions only"
            )
        files = _collect_files(package_dir)
        staging = self._root / f".staging-{uuid.uuid4().hex[:12]}"
        try:
            dependency = DependencyManifest(
                runtime_profile_id=profile.profile_id,
                runtime_profile_manifest_sha256=profile.profile.manifest_sha256,
                sdk=SdkPin(name=sdk.name, version=sdk.version, artifact_sha256=sdk.artifact_sha256),
            )
            dependency_bytes = canonical_json(dependency.model_dump(mode="json"))
            staging.mkdir(parents=True)
            entries: list[PackageFile] = []
            for path in files:
                rel = path.relative_to(package_dir)
                target = staging / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
                entries.append(
                    PackageFile(
                        path=rel.as_posix(), sha256=sha256_file(target), size=target.stat().st_size
                    )
                )
            (staging / "dependency.manifest.json").write_bytes(dependency_bytes)
            dependency_sha = hashlib.sha256(dependency_bytes).hexdigest()
            entries.append(
                PackageFile(
                    path="dependency.manifest.json",
                    sha256=dependency_sha,
                    size=len(dependency_bytes),
                )
            )
            entries.sort(key=lambda e: e.path)
            index_body = {
                "contract_version": "0.2",
                "app_id": source.app_id,
                "files": [e.model_dump(mode="json") for e in entries],
                "dependency_manifest_sha256": dependency_sha,
                "toolchain": {
                    "python": str(profile.profile.target.python_version),
                    "sdk": sdk.version,
                    "worker_protocol": str(profile.profile.compatibility.worker_protocol),
                },
            }
            package_sha = hashlib.sha256(canonical_json(index_body)).hexdigest()
            index = PackageIndex.model_validate({**index_body, "package_sha256": package_sha})
            (staging / "package.index.json").write_bytes(
                canonical_json(index.model_dump(mode="json"))
            )
            version_id = f"ver_{package_sha[:24]}"
            target_dir = self._root / version_id
            existing = self._version_row(version_id)
            if existing is not None:
                _remove(staging)
                return self._ensure_release(existing)
            if target_dir.exists():
                # Sealed directory without a row: an install interrupted after publish. The bytes
                # are content-addressed, so re-verify them and reuse.
                _remove(staging)
                self._verify_sealed(target_dir, index)
            else:
                _seal(staging)
                staging.chmod(staging.stat().st_mode | stat.S_IWUSR)
                os.rename(staging, target_dir)
                target_dir.chmod(target_dir.stat().st_mode & ~stat.S_IWUSR)
            report = self._validator(target_dir, source, profile)
            failures = [r for r in report if not r.get("ok")]
            if failures or len(report) != len(source.actions):
                _remove(target_dir)
                raise invalid(
                    "the package's handlers do not match its declared actions",
                    actions=failures or report,
                )
            store = self._records.store(source.app_id)
            store.register_collections(source.collections)
            now = _now()
            release_id = new_id("rel")
            with self._store.transaction() as conn:
                row = conn.execute(
                    "SELECT app_id FROM apps WHERE app_id = ?", (source.app_id,)
                ).fetchone()
                if row is None:
                    conn.execute(
                        """INSERT INTO apps(app_id, name, description, created_at, updated_at)
                           VALUES (?,?,?,?,?)""",
                        (source.app_id, source.name, source.description, now, now),
                    )
                conn.execute(
                    """INSERT INTO app_versions(version_id, app_id, package_sha256, source_json,
                       dependency_manifest_json, dependency_manifest_sha256, runtime_profile_id,
                       location_ref, validation_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        version_id,
                        source.app_id,
                        package_sha,
                        source.model_dump_json(),
                        dependency.model_dump_json(),
                        dependency_sha,
                        profile.profile_id,
                        str(target_dir),
                        json.dumps(report),
                        now,
                    ),
                )
                conn.execute(
                    """INSERT INTO app_releases(release_id, app_id, version_id, kind, created_at)
                       VALUES (?,?,?,?,?)""",
                    (release_id, source.app_id, version_id, "installed", now),
                )
                conn.execute(
                    """UPDATE apps SET name = ?, description = ?, updated_at = ?,
                       current_version_id = ?, current_release_id = ? WHERE app_id = ?""",
                    (source.name, source.description, now, version_id, release_id, source.app_id),
                )
            return self.current(source.app_id)
        finally:
            if staging.exists():
                _remove(staging)

    def _verify_sealed(self, target_dir: Path, index: PackageIndex) -> None:
        for entry in index.files:
            path = target_dir / entry.path
            if not path.is_file() or sha256_file(path) != entry.sha256:
                raise conflict(f"sealed version {target_dir.name} does not match its index")

    def _version_row(self, version_id: str) -> dict[str, Any] | None:
        rows = self._store.query("SELECT * FROM app_versions WHERE version_id = ?", (version_id,))
        return dict(rows[0]) if rows else None

    def _ensure_release(self, version: dict[str, Any]) -> AppVersion:
        current = self.current(version["app_id"])
        if current.version_id == version["version_id"]:
            return current
        now = _now()
        release_id = new_id("rel")
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO app_releases(release_id, app_id, version_id, kind, created_at)
                   VALUES (?,?,?,?,?)""",
                (release_id, version["app_id"], version["version_id"], "reinstalled", now),
            )
            conn.execute(
                """UPDATE apps SET updated_at = ?, current_version_id = ?, current_release_id = ?
                   WHERE app_id = ?""",
                (now, version["version_id"], release_id, version["app_id"]),
            )
        return self.current(version["app_id"])

    def current(self, app_id: str) -> AppVersion:
        rows = self._store.query(
            """SELECT a.app_id, a.current_release_id, v.* FROM apps a
               JOIN app_versions v ON v.version_id = a.current_version_id WHERE a.app_id = ?""",
            (app_id,),
        )
        if not rows:
            raise not_found(f"no App {app_id!r} is installed", app_id=app_id)
        row = rows[0]
        return AppVersion(
            app_id=row["app_id"],
            version_id=row["version_id"],
            release_id=row["current_release_id"],
            package_sha256=row["package_sha256"],
            dependency_manifest_sha256=row["dependency_manifest_sha256"],
            runtime_profile_id=row["runtime_profile_id"],
            location=Path(row["location_ref"]),
            source=AppSource.model_validate_json(row["source_json"]),
        )

    def list_apps(self) -> list[dict[str, Any]]:
        rows = self._store.query(
            """SELECT a.app_id, a.name, a.description, a.current_version_id, a.current_release_id,
                      a.updated_at, v.package_sha256, v.runtime_profile_id
               FROM apps a LEFT JOIN app_versions v ON v.version_id = a.current_version_id
               ORDER BY a.created_at"""
        )
        return [dict(r) for r in rows]

    def versions_for_profile(self, profile_id: str) -> list[str]:
        rows = self._store.query(
            "SELECT version_id FROM app_versions WHERE runtime_profile_id = ?", (profile_id,)
        )
        return [r["version_id"] for r in rows]
