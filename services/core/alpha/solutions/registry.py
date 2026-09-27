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
import re
import shutil
import stat
import tempfile
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

# Columns added after F05; an existing control store gains them on startup.
_APP_COLUMNS = {
    "origin": "TEXT NOT NULL DEFAULT 'fixture'",
    "state": "TEXT NOT NULL DEFAULT 'active'",
    "creation_id": "TEXT",
}
_RELEASE_COLUMNS = {
    "previous_release_id": "TEXT",
    "build_id": "TEXT",
    "verification_ref": "TEXT",
}


class AnyRelease:
    """Marker: activate whatever the current release is (development fixture installs)."""


ANY_RELEASE = AnyRelease()


@dataclass(frozen=True)
class Activation:
    """Where a Version comes from and what it must replace. `expected_release_id` is the
    compare-and-swap guard: the App's current release must still be exactly this (None for a
    new App), or activation is refused."""

    kind: str = "installed"
    origin: str = "fixture"
    expected_release_id: str | None | AnyRelease = ANY_RELEASE
    build_id: str | None = None
    verification_ref: str | None = None
    creation_id: str | None = None


# (version_dir, source, profile) -> {"actions": [...], "imports": {...}} from a disposable worker
HandlerValidator = Callable[[Path, AppSource, InstalledProfile], dict[str, Any]]


@dataclass(frozen=True)
class AppVersion:
    app_id: str
    version_id: str
    release_id: str
    origin: str
    state: str
    package_sha256: str
    dependency_manifest_sha256: str
    dependency_manifest: DependencyManifest
    runtime_profile_id: str
    location: Path
    source: AppSource


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


# What sealing and dependency resolution add to a Version; a package copied out of one must
# not carry them (the builder's workspace uses the same list, see alpha.builds.workspace).
_SEALED_ARTEFACTS = shutil.ignore_patterns(
    "__pycache__",
    ".DS_Store",
    "*.pyc",
    "dependencies",
    "dist",
    "node_modules",
    "package.index.json",
    "dependency.manifest.json",
)


def repoint_runtime(app_yaml: str, profile_id: str) -> str:
    """The same app.yaml naming another runtime profile."""
    return re.sub(r"(?m)^runtime_profile:.*$", f"runtime_profile: {profile_id}", app_yaml, count=1)


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
        store.add_missing_columns("apps", _APP_COLUMNS)
        store.add_missing_columns("app_releases", _RELEASE_COLUMNS)
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

    def install(self, package_dir: Path, activation: Activation | None = None) -> AppVersion:
        """Prepare a package into the Versions store and make it current (fixtures, and moving
        an App to the current runtime)."""
        try:
            sealed, report = self.prepare(package_dir, self._root)
        except UnsupportedDependencies as exc:
            raise invalid(
                "the package needs packages outside the runtime profile",
                qualification_requests=[r.model_dump() for r in exc.requests],
            ) from None
        return self.register(sealed, report, activation)

    def move_to_profile(self, app_id: str, profile: InstalledProfile) -> AppVersion:
        """Re-prepare the App's current version on `profile` (normally the newest runtime, which
        carries the current SDK), keeping its code, identity and records. The handlers must bind
        on the new profile and the App's current release must still be the one this started
        from, or nothing changes."""
        current = self.current(app_id)
        if current.runtime_profile_id == profile.profile_id:
            return current
        staging = Path(tempfile.mkdtemp(prefix="alpha-move-"))
        try:
            package = staging / "package"
            shutil.copytree(current.location, package, ignore=_SEALED_ARTEFACTS, symlinks=False)
            for path in [package, *package.rglob("*")]:
                path.chmod(path.stat().st_mode | stat.S_IWUSR)
            app_yaml = package / "app.yaml"
            app_yaml.write_text(
                repoint_runtime(app_yaml.read_text(encoding="utf-8"), profile.profile_id),
                encoding="utf-8",
            )
            return self.install(
                package,
                Activation(
                    kind="moved", origin=current.origin, expected_release_id=current.release_id
                ),
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)

    def activate_sealed(
        self, candidate_dir: Path, package_sha256: str, activation: Activation
    ) -> AppVersion:
        """Make a validated candidate current, after rechecking that its bytes and its profile
        identities are exactly those it was validated with, and that the App's current release
        is still the one the activation expects."""
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
        return self.register(sealed, report, activation)

    def register(
        self,
        sealed: SealedPackage,
        report: dict[str, Any],
        activation: Activation | None = None,
    ) -> AppVersion:
        """Record the Version (once) and make it the App's current release."""
        activation = activation or Activation()
        source = sealed.source
        self._records.store(source.app_id).register_collections(source.collections)
        now = _now()
        with self._store.transaction() as conn:
            self._check_expected(conn, source.app_id, activation)
            app = conn.execute(
                "SELECT app_id FROM apps WHERE app_id = ?", (source.app_id,)
            ).fetchone()
            if app is None:
                conn.execute(
                    """INSERT INTO apps(app_id, name, description, created_at, updated_at,
                       origin, state, creation_id) VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        source.app_id,
                        source.name,
                        source.description,
                        now,
                        now,
                        activation.origin,
                        "active",
                        activation.creation_id,
                    ),
                )
            known = conn.execute(
                "SELECT version_id FROM app_versions WHERE version_id = ?", (sealed.version_id,)
            ).fetchone()
            if known is None:
                conn.execute(
                    """INSERT INTO app_versions(version_id, app_id, package_sha256, source_json,
                       dependency_manifest_json, dependency_manifest_sha256, runtime_profile_id,
                       location_ref, validation_json, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
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
            current = conn.execute(
                "SELECT current_version_id, current_release_id FROM apps WHERE app_id = ?",
                (source.app_id,),
            ).fetchone()
            if current["current_version_id"] != sealed.version_id or activation.build_id:
                self._make_current(conn, source.app_id, sealed.version_id, activation, now)
            conn.execute(
                "UPDATE apps SET name = ?, description = ?, updated_at = ? WHERE app_id = ?",
                (source.name, source.description, now, source.app_id),
            )
        return self.current(source.app_id)

    @staticmethod
    def _check_expected(conn: Any, app_id: str, activation: Activation) -> None:
        if isinstance(activation.expected_release_id, AnyRelease):
            return
        row = conn.execute(
            "SELECT current_release_id FROM apps WHERE app_id = ?", (app_id,)
        ).fetchone()
        current = row["current_release_id"] if row else None
        if current != activation.expected_release_id:
            raise conflict(
                f"{app_id} changed since this build started; build it again",
                expected_release_id=activation.expected_release_id,
                current_release_id=current,
            )

    @staticmethod
    def _make_current(
        conn: Any, app_id: str, version_id: str, activation: Activation, now: str
    ) -> None:
        row = conn.execute(
            "SELECT current_release_id FROM apps WHERE app_id = ?", (app_id,)
        ).fetchone()
        release_id = new_id("rel")
        conn.execute(
            """INSERT INTO app_releases(release_id, app_id, version_id, kind, created_at,
               previous_release_id, build_id, verification_ref)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                release_id,
                app_id,
                version_id,
                activation.kind,
                now,
                row["current_release_id"] if row else None,
                activation.build_id,
                activation.verification_ref,
            ),
        )
        conn.execute(
            """UPDATE apps SET current_version_id = ?, current_release_id = ?, updated_at = ?
               WHERE app_id = ?""",
            (version_id, release_id, now, app_id),
        )

    def _version_row(self, version_id: str) -> dict[str, Any] | None:
        rows = self._store.query("SELECT * FROM app_versions WHERE version_id = ?", (version_id,))
        return dict(rows[0]) if rows else None

    def current(self, app_id: str) -> AppVersion:
        rows = self._store.query(
            """SELECT a.app_id, a.current_release_id, a.origin, a.state, v.* FROM apps a
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
            origin=row["origin"],
            state=row["state"],
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
                      a.origin, a.state, a.creation_id, a.created_at, a.updated_at,
                      v.package_sha256, v.runtime_profile_id, v.source_json
               FROM apps a LEFT JOIN app_versions v ON v.version_id = a.current_version_id
               ORDER BY a.created_at"""
        )
        apps = []
        for row in rows:
            entry = {k: row[k] for k in row.keys() if k != "source_json"}
            source = (
                AppSource.model_validate_json(row["source_json"]) if row["source_json"] else None
            )
            entry["has_ui"] = bool(source and source.has_screen())
            entry["has_screen"] = bool(source and source.screen)
            entry["actions"] = len(source.actions) if source else 0
            apps.append(entry)
        return apps

    def versions_for_profile(self, profile_id: str) -> list[str]:
        rows = self._store.query(
            "SELECT version_id FROM app_versions WHERE runtime_profile_id = ?", (profile_id,)
        )
        return [r["version_id"] for r in rows]
