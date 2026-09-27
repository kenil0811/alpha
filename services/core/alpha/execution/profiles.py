"""Dependency profile inventory (Current Release Specification §11, Implementation Blueprint §10).

Profiles are built and published by the trusted build path (tools/build_app_profile.py). Core
never installs packages: at startup it verifies each published profile against its sealed
manifest and installation record and registers it in the control store. Only a `ready`, verified
profile can back a new worker lease; a profile whose bytes changed is quarantined, never
silently used.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from alpha_contracts.profiles import DependencyProfile, ProfileKind, verify_profile

from alpha.capabilities.errors import unavailable
from alpha.storage.control_store import ControlStore, utc_now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dependency_profiles (
    profile_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    role TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    manifest_sha256 TEXT NOT NULL,
    registered_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_installations (
    profile_id TEXT PRIMARY KEY REFERENCES dependency_profiles(profile_id),
    location_ref TEXT NOT NULL,
    state TEXT NOT NULL,
    reason TEXT,
    integrity_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    verified_at TEXT
);
"""


class InstallationState(StrEnum):
    PREPARING = "preparing"
    READY = "ready"
    QUARANTINED = "quarantined"
    DELETING = "deleting"
    FAILED = "failed"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(root: Path) -> dict[str, Any]:
    """Digest of every file (bytes) and symlink (target text) under root, by relative path."""
    digest = hashlib.sha256()
    entries = 0
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root).as_posix()
        if path.is_symlink():
            digest.update(f"L {rel} -> {os.readlink(path)}\n".encode())
            entries += 1
        elif path.is_file():
            digest.update(f"F {rel} {sha256_file(path)}\n".encode())
            entries += 1
    return {"sha256": digest.hexdigest(), "entries": entries}


def verify_profile_dir(target: Path) -> tuple[DependencyProfile | None, dict[str, Any], list[str]]:
    """Verify a published profile directory. Returns (manifest, installation record, problems)."""
    try:
        profile = DependencyProfile.model_validate_json(
            (target / "manifest.json").read_text("utf-8")
        )
        installation = json.loads((target / "installation.json").read_text("utf-8"))
    except Exception as exc:
        return None, {}, [f"unreadable manifest or installation record: {exc}"]
    problems = list(verify_profile(profile))
    if profile.profile_id != target.name:
        problems.append("directory name differs from profile_id")
    for lock in profile.locks:
        lock_path = target / lock.path
        if not lock_path.is_file() or sha256_file(lock_path) != lock.sha256:
            problems.append(f"lock {lock.path} is missing or changed")
    if profile.kind is ProfileKind.PYTHON_RUNTIME:
        problems += _verify_python(target, profile, installation)
    else:
        problems += _verify_ui(target, profile, installation)
    return profile, installation, problems


def _verify_python(
    target: Path, profile: DependencyProfile, installation: dict[str, Any]
) -> list[str]:
    problems: list[str] = []
    for pin in profile.packages:
        wheel = target / "wheels" / (pin.artifact or "")
        if pin.artifact is None or not wheel.is_file() or sha256_file(wheel) != pin.artifact_sha256:
            problems.append(f"artifact for {pin.name} is missing or changed")
    venv = target / "venv"
    if not (venv / "bin" / "python").exists():
        problems.append("profile interpreter is missing")
        return problems
    observed = tree_digest(venv)
    if observed["sha256"] != installation.get("venv_tree", {}).get("sha256"):
        problems.append("installed files differ from the sealed installation record")
    interpreter = Path(str(installation.get("interpreter", "")))
    if not interpreter.is_file():
        problems.append("base interpreter is missing")
    elif sha256_file(interpreter) != installation.get("interpreter_sha256"):
        problems.append("base interpreter bytes changed")
    return problems


def _verify_ui(target: Path, profile: DependencyProfile, installation: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for name, tarball in (installation.get("tarballs") or {}).items():
        path = target / "packages" / str(tarball.get("file", ""))
        if not path.is_file() or sha256_file(path) != tarball.get("sha256"):
            problems.append(f"packed artifact for {name} is missing or changed")
    node_modules = target / "node_modules"
    if not node_modules.is_dir():
        problems.append("installed packages are missing")
    elif tree_digest(node_modules)["sha256"] != (installation.get("node_modules_tree") or {}).get(
        "sha256"
    ):
        problems.append("installed files differ from the sealed installation record")
    for pin in profile.packages:
        if (
            pin.artifact
            and pin.artifact.endswith(".tgz")
            and pin.name not in (installation.get("tarballs") or {})
        ):
            problems.append(f"no packed artifact recorded for {pin.name}")
    return problems


@dataclass(frozen=True)
class InstalledProfile:
    profile: DependencyProfile
    location: Path
    state: InstallationState
    reason: str | None

    @property
    def python(self) -> Path:
        return self.location / "venv" / "bin" / "python"

    @property
    def profile_id(self) -> str:
        return self.profile.profile_id


class ProfileInventory:
    def __init__(self, store: ControlStore, root: Path | None) -> None:
        self._store = store
        self._root = root
        store.execute_script(_SCHEMA)

    @property
    def root(self) -> Path | None:
        return self._root

    def scan(self) -> list[dict[str, Any]]:
        """Verify every published profile and (re)register its installation state."""
        report: list[dict[str, Any]] = []
        seen: set[str] = set()
        if self._root is not None and self._root.is_dir():
            # Oldest build first, so "newest registered" (the default for new Apps) is the
            # profile built most recently, not the one that happens to sort last by id.
            for target in sorted(self._root.iterdir(), key=_built_at):
                if target.name.startswith(".") or not target.is_dir():
                    continue
                profile, installation, problems = verify_profile_dir(target)
                if profile is None:
                    report.append(
                        {"location": target.name, "state": "unreadable", "problems": problems}
                    )
                    continue
                seen.add(profile.profile_id)
                report.append(self._register(profile, target, installation, problems))
        now = _now()
        with self._store.transaction() as conn:
            for row in conn.execute(
                "SELECT profile_id FROM profile_installations WHERE state = ?",
                (InstallationState.READY.value,),
            ).fetchall():
                if row["profile_id"] not in seen:
                    conn.execute(
                        """UPDATE profile_installations SET state = ?, reason = ?, updated_at = ?
                           WHERE profile_id = ?""",
                        (
                            InstallationState.FAILED.value,
                            "installation missing",
                            now,
                            row["profile_id"],
                        ),
                    )
                    report.append(
                        {
                            "profile_id": row["profile_id"],
                            "state": "failed",
                            "problems": ["installation missing"],
                        }
                    )
        return report

    def _register(
        self,
        profile: DependencyProfile,
        target: Path,
        installation: dict[str, Any],
        problems: list[str],
    ) -> dict[str, Any]:
        now = _now()
        integrity = {
            "venv_tree": installation.get("venv_tree"),
            "node_modules_tree": installation.get("node_modules_tree"),
            "interpreter_sha256": installation.get("interpreter_sha256"),
            "uv_version": installation.get("uv_version"),
        }
        with self._store.transaction() as conn:
            existing = conn.execute(
                "SELECT manifest_sha256 FROM dependency_profiles WHERE profile_id = ?",
                (profile.profile_id,),
            ).fetchone()
            if existing is None:
                conn.execute(
                    """INSERT INTO dependency_profiles(profile_id, kind, role, manifest_json,
                       manifest_sha256, registered_at) VALUES (?,?,?,?,?,?)""",
                    (
                        profile.profile_id,
                        profile.kind.value,
                        profile.role.value,
                        profile.model_dump_json(),
                        profile.manifest_sha256,
                        now,
                    ),
                )
            elif existing["manifest_sha256"] != profile.manifest_sha256:
                problems = [*problems, "manifest differs from the registered manifest"]
            row = conn.execute(
                "SELECT integrity_json, state FROM profile_installations WHERE profile_id = ?",
                (profile.profile_id,),
            ).fetchone()
            if row is not None:
                recorded = json.loads(row["integrity_json"])
                if (recorded.get("venv_tree"), recorded.get("node_modules_tree")) != (
                    integrity["venv_tree"],
                    integrity["node_modules_tree"],
                ):
                    problems = [*problems, "installation differs from the registered installation"]
                if row["state"] == InstallationState.QUARANTINED.value and not problems:
                    problems = ["previously quarantined; remains quarantined until reviewed"]
            state = InstallationState.READY if not problems else InstallationState.QUARANTINED
            reason = "; ".join(problems) or None
            if row is None:
                conn.execute(
                    """INSERT INTO profile_installations(profile_id, location_ref, state, reason,
                       integrity_json, created_at, updated_at, verified_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        profile.profile_id,
                        str(target),
                        state.value,
                        reason,
                        json.dumps(integrity, sort_keys=True),
                        now,
                        now,
                        now if state is InstallationState.READY else None,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE profile_installations SET location_ref = ?, state = ?, reason = ?,
                       updated_at = ?, verified_at = ? WHERE profile_id = ?""",
                    (
                        str(target),
                        state.value,
                        reason,
                        now,
                        now if state is InstallationState.READY else None,
                        profile.profile_id,
                    ),
                )
        return {"profile_id": profile.profile_id, "state": state.value, "problems": problems}

    def get(self, profile_id: str) -> InstalledProfile | None:
        rows = self._store.query(
            """SELECT p.manifest_json, i.location_ref, i.state, i.reason
               FROM dependency_profiles p JOIN profile_installations i USING(profile_id)
               WHERE p.profile_id = ?""",
            (profile_id,),
        )
        if not rows:
            return None
        row = rows[0]
        return InstalledProfile(
            profile=DependencyProfile.model_validate_json(row["manifest_json"]),
            location=Path(row["location_ref"]),
            state=InstallationState(row["state"]),
            reason=row["reason"],
        )

    def ready(self, profile_id: str) -> InstalledProfile:
        installed = self.get(profile_id)
        if installed is None:
            raise unavailable(f"runtime profile {profile_id!r} is not installed on this Mac")
        if installed.state is not InstallationState.READY:
            raise unavailable(
                f"runtime profile {profile_id!r} is {installed.state.value}",
                reason=installed.reason,
            )
        return installed

    def verified(self, profile_id: str) -> InstalledProfile:
        """`ready`, plus a fresh check of the installation's bytes. Used where identity must be
        exact right now (candidate validation, activation), not just as it was at startup. Any
        difference quarantines the profile, which also stops new runs on it."""
        installed = self.ready(profile_id)
        profile, installation, problems = verify_profile_dir(installed.location)
        if profile is None or profile.profile_id != profile_id:
            problems = problems or ["the installation no longer holds this profile"]
            self._quarantine(profile_id, problems)
        else:
            self._register(profile, installed.location, installation, problems)
        current = self.ready_or_none(profile_id)
        if current is None:
            row = self.get(profile_id)
            raise unavailable(
                f"runtime profile {profile_id!r} changed on disk and is quarantined",
                reason=row.reason if row else None,
            )
        return current

    def ready_or_none(self, profile_id: str) -> InstalledProfile | None:
        installed = self.get(profile_id)
        return installed if installed and installed.state is InstallationState.READY else None

    def _quarantine(self, profile_id: str, problems: list[str]) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                """UPDATE profile_installations SET state = ?, reason = ?, updated_at = ?,
                   verified_at = NULL WHERE profile_id = ?""",
                (InstallationState.QUARANTINED.value, "; ".join(problems), _now(), profile_id),
            )

    def default_app_profile(self) -> InstalledProfile | None:
        """The ready App/Task compute profile new Apps target (newest registered)."""
        rows = self._store.query(
            """SELECT p.profile_id FROM dependency_profiles p JOIN profile_installations i
               USING(profile_id) WHERE p.role = 'app_task_compute' AND p.kind = 'python_runtime'
               AND i.state = 'ready' ORDER BY p.registered_at DESC LIMIT 1"""
        )
        return self.get(rows[0]["profile_id"]) if rows else None

    def default_ui_profile(self) -> InstalledProfile | None:
        """The ready UI build profile generated App UI compiles against (newest registered)."""
        rows = self._store.query(
            """SELECT p.profile_id FROM dependency_profiles p JOIN profile_installations i
               USING(profile_id) WHERE p.kind = 'ui_build' AND i.state = 'ready'
               ORDER BY p.registered_at DESC LIMIT 1"""
        )
        return self.get(rows[0]["profile_id"]) if rows else None

    def list_profiles(self) -> list[dict[str, Any]]:
        rows = self._store.query(
            """SELECT p.profile_id, p.kind, p.role, p.manifest_json, p.manifest_sha256,
                      i.state, i.reason, i.verified_at, i.integrity_json
               FROM dependency_profiles p JOIN profile_installations i USING(profile_id)
               ORDER BY p.registered_at"""
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "profile_id": row["profile_id"],
                    "kind": row["kind"],
                    "role": row["role"],
                    "manifest": json.loads(row["manifest_json"]),
                    "manifest_sha256": row["manifest_sha256"],
                    "state": row["state"],
                    "reason": row["reason"],
                    "verified_at": row["verified_at"],
                    "installed_tree_sha256": (
                        json.loads(row["integrity_json"]).get("venv_tree")
                        or json.loads(row["integrity_json"]).get("node_modules_tree")
                        or {}
                    ).get("sha256"),
                }
            )
        return out


def _built_at(target: Path) -> tuple[str, str]:
    """When a published profile was built (its installation.json), then its name."""
    try:
        data = json.loads((target / "installation.json").read_text(encoding="utf-8"))
        return (str(data.get("created_at") or ""), target.name)
    except (OSError, ValueError):
        return ("", target.name)


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")
