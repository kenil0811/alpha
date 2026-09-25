"""App ownership records, Version registration and activation of sealed packages.

Packaging (dependency resolution, file rules, UI build, sealing, byte verification) lives in
`alpha.data.packages`; this module decides which sealed Version an App currently runs:

- `prepare` validates and seals a package into any directory and binds every handler in a
  disposable worker on the exact profile (F07 candidates are prepared inside their build).
- `install` = prepare into the Versions store + register (development fixtures, F05).
- `activate_sealed` re-verifies a validated candidate's bytes and its profile identities, copies
  it into the Versions store and registers it. Validation, activation and invocation therefore
  agree on one dependency manifest.

Expected-current-release checks, release history UX and data-schema migration belong to
F08/F10; the release row written here is the minimal pointer an App run's owner needs.
"""

from __future__ import annotations

import json
import shutil
import stat
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alpha_contracts.apps import AppSource
from alpha_contracts.profiles import DependencyManifest, canonical_json
from alpha_contracts.verification import DependencyQualificationRequest

from alpha.capabilities.errors import conflict, invalid, not_found
from alpha.data.packages import (
    SealedPackage,
    UiBuilder,
    UnsupportedDependencies,
    collect_files,
    load_source,
    remove_tree,
    resolve_dependencies,
    seal,
    seal_tree,
    sealed_manifest,
    verify_sealed,
)
from alpha.data.store import RecordService
from alpha.execution.profiles import InstalledProfile, ProfileInventory
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

# (version_dir, source, profile) -> {"actions": [...], "imports": {...}} from a disposable worker
HandlerValidator = Callable[[Path, AppSource, InstalledProfile], dict[str, Any]]


@dataclass(frozen=True)
class AppVersion:
    app_id: str
    version_id: str
    release_id: str
    package_sha256: str
    dependency_manifest_sha256: str
    dependency_manifest: DependencyManifest
    runtime_profile_id: str
    location: Path
    source: AppSource


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def interpret_handler_report(
    report: dict[str, Any], source: AppSource, runtime_profile_id: str
) -> None:
    """Raise unless every import is allowed and every declared handler binds."""
    imports = report.get("imports")
    if not isinstance(imports, dict):
        # A worker without the import scan (a profile built before F07) cannot vouch for the
        # package's dependencies; it must not pass silently.
        raise invalid(
            f"runtime profile {runtime_profile_id} cannot check imports; rebuild the profile"
        )
    undeclared = imports.get("undeclared") or []
    if undeclared:
        seen: dict[str, str] = {}
        for item in undeclared:
            seen.setdefault(str(item["top"]), str(item["where"]))
        raise UnsupportedDependencies(
            [
                DependencyQualificationRequest(
                    package=name,
                    found_in="import",
                    where=where,
                    runtime_profile_id=runtime_profile_id,
                    reason="imported by the package but not in the qualified runtime profile; "
                    "nothing is installed at run time",
                )
                for name, where in sorted(seen.items())
            ]
        )
    if not imports.get("ok", False):
        raise invalid(
            "the package's imports are not allowed", problems=imports.get("problems", [])[:10]
        )
    actions = report.get("actions") or []
    failures = [a for a in actions if not a.get("ok")]
    if failures or len(actions) != len(source.actions):
        raise invalid(
            "the package's handlers do not match its declared actions",
            actions=failures or actions,
        )


class AppRegistry:
    def __init__(
        self,
        store: ControlStore,
        inventory: ProfileInventory,
        records: RecordService,
        versions_root: Path,
        validator: HandlerValidator,
        ui_builder: UiBuilder | None = None,
    ) -> None:
        self._store = store
        self._inventory = inventory
        self._records = records
        self._root = versions_root
        self._validator = validator
        self._ui_builder = ui_builder
        store.execute_script(_SCHEMA)
        versions_root.mkdir(parents=True, exist_ok=True)

    @property
    def inventory(self) -> ProfileInventory:
        return self._inventory

    def reconcile_on_startup(self) -> list[str]:
        """Remove staging left by an interrupted install; sealed Versions are never touched."""
        removed: list[str] = []
        for leftover in self._root.glob(".staging-*"):
            remove_tree(leftover)
            removed.append(leftover.name)
        return removed

    def prepare(self, package_dir: Path, dest_root: Path) -> tuple[SealedPackage, dict[str, Any]]:
        """Validate, resolve, build, seal and bind a package under `dest_root`. Raises
        OperationFailed, UnsupportedDependencies or UiBuildFailed with the reason."""
        source = load_source(package_dir)
        deps = resolve_dependencies(source, self._inventory)
        files = collect_files(package_dir, source)
        sealed = seal(package_dir, source, deps, files, dest_root, self._ui_builder)
        try:
            report = self.bind_handlers(sealed.path, source, deps.runtime)
        except Exception:
            # A Version whose handlers do not bind is never kept, unless an identical Version
            # was already registered (content addressing makes it the same directory).
            if self._version_row(sealed.version_id) is None:
                remove_tree(sealed.path)
            raise
        return sealed, report

    def bind_handlers(
        self, version_dir: Path, source: AppSource, profile: InstalledProfile
    ) -> dict[str, Any]:
        report = self._validator(version_dir, source, profile)
        interpret_handler_report(report, source, profile.profile_id)
        return report

    def install(self, package_dir: Path) -> AppVersion:
        """Development path (fixtures): prepare into the Versions store and make it current."""
        try:
            sealed, report = self.prepare(package_dir, self._root)
        except UnsupportedDependencies as exc:
            raise invalid(
                "the package needs packages outside the runtime profile",
                qualification_requests=[r.model_dump() for r in exc.requests],
            ) from None
        return self.register(sealed, report)

    def activate_sealed(self, candidate_dir: Path, package_sha256: str) -> AppVersion:
        """Make a validated candidate current, after rechecking that its bytes and its profile
        identities are exactly those it was validated with."""
        verify_sealed(candidate_dir, package_sha256)
        source = load_source(candidate_dir)
        deps = resolve_dependencies(source, self._inventory)
        sealed_bytes = (candidate_dir / "dependency.manifest.json").read_bytes()
        if canonical_json(deps.manifest().model_dump(mode="json")) != sealed_bytes:
            raise conflict(
                "the installed profiles differ from the ones this candidate was validated with; "
                "rebuild and validate it again",
                validated=json.loads(sealed_bytes),
                installed=deps.manifest().model_dump(mode="json"),
            )
        target = self._root / candidate_dir.name
        if not target.exists():
            staging = self._root / f".staging-{uuid.uuid4().hex[:12]}"
            try:
                shutil.copytree(candidate_dir, staging, symlinks=True)
                for path in [staging, *staging.rglob("*")]:
                    path.chmod(path.stat().st_mode | stat.S_IWUSR)
                verify_sealed(staging, package_sha256)
                seal_tree(staging)
                staging.chmod(staging.stat().st_mode | stat.S_IWUSR)
                staging.rename(target)
                target.chmod(target.stat().st_mode & ~stat.S_IWUSR)
            finally:
                if staging.exists():
                    remove_tree(staging)
        index = verify_sealed(target, package_sha256)
        report = self.bind_handlers(target, source, deps.runtime)
        sealed = SealedPackage(
            path=target,
            version_id=target.name,
            source=source,
            index=index,
            dependency_manifest=sealed_manifest(target),
            dependency_manifest_sha256=index.dependency_manifest_sha256,
            ui_build=None,
        )
        return self.register(sealed, report)

    def register(self, sealed: SealedPackage, report: dict[str, Any]) -> AppVersion:
        """Record the Version and make it the App's current release."""
        source = sealed.source
        existing = self._version_row(sealed.version_id)
        if existing is not None:
            return self._ensure_release(existing)
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
                    sealed.version_id,
                    source.app_id,
                    sealed.package_sha256,
                    source.model_dump_json(),
                    sealed.dependency_manifest.model_dump_json(),
                    sealed.dependency_manifest_sha256,
                    sealed.dependency_manifest.runtime_profile_id,
                    str(sealed.path),
                    json.dumps(report),
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO app_releases(release_id, app_id, version_id, kind, created_at)
                   VALUES (?,?,?,?,?)""",
                (release_id, source.app_id, sealed.version_id, "installed", now),
            )
            conn.execute(
                """UPDATE apps SET name = ?, description = ?, updated_at = ?,
                   current_version_id = ?, current_release_id = ? WHERE app_id = ?""",
                (
                    source.name,
                    source.description,
                    now,
                    sealed.version_id,
                    release_id,
                    source.app_id,
                ),
            )
        return self.current(source.app_id)

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
            dependency_manifest=DependencyManifest.model_validate_json(
                row["dependency_manifest_json"]
            ),
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
