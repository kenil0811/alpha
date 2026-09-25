"""App packages: resolve dependencies, collect files, seal an immutable Version, verify it later.

One path for every Version, whether it comes from a builder candidate (F07) or a development
fixture (F05). Package Layout rules:

- The package supplies `app.yaml`, `src/`, optional `ui/` and `tests/`, optional `README.md`.
  Dependency declarations, environment files and platform-produced files are refused by name.
- The platform resolves the exact runtime profile, SDK and optional UI build profile from
  profiles re-verified on disk, compiles the UI with the trusted build tool, copies the profile
  locks into `dependencies/` as provenance, and writes `dependency.manifest.json` and
  `package.index.json`. Nothing portable contains a local path, grant or secret.
- A Version is content-addressed (`ver_<package digest>`), sealed read-only and re-verified
  byte for byte before activation.

An extra package is never installed to make a candidate work: it becomes a bounded
qualification request and the candidate fails.
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
from alpha_contracts.profiles import (
    DependencyManifest,
    PackagePin,
    ProfileKind,
    ProfileRole,
    SdkPin,
    UiBuildRef,
    canonical_json,
)
from alpha_contracts.verification import DependencyQualificationRequest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError

from alpha.capabilities.errors import conflict, invalid
from alpha.execution.profiles import InstalledProfile, ProfileInventory, sha256_file

SRC_SUFFIXES = {".py", ".json", ".txt", ".csv", ".md", ".yaml"}
UI_SUFFIXES = {".ts", ".tsx", ".css", ".json"}
TEST_SUFFIXES = {".py", ".json", ".txt", ".csv"}
MAX_FILE_BYTES = 1_000_000
MAX_PACKAGE_BYTES = 10_000_000
MAX_FILES = 500
UI_ENTRY = "ui/src/main.tsx"

# Top-level names a package cannot contain, with the reason a builder can act on.
_DEPENDENCY_FILES = {
    "requirements.txt",
    "requirements.lock",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "uv.lock",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "node_modules",
    ".venv",
    "venv",
}
_PLATFORM_FILES = {"dependencies", "dist", "package.index.json", "dependency.manifest.json"}
_IGNORED = {"__pycache__", ".DS_Store"}


class UnsupportedDependencies(Exception):
    """The candidate needs packages the runtime profile does not contain."""

    def __init__(self, requests: list[DependencyQualificationRequest]) -> None:
        super().__init__(", ".join(r.package for r in requests))
        self.requests = requests


class UiBuildFailed(Exception):
    def __init__(self, message: str, log: str = "") -> None:
        super().__init__(message)
        self.log = log


# (ui source dir, output dir, ui build profile) -> build report (build.json content)
UiBuilder = Callable[[Path, Path, InstalledProfile], dict[str, Any]]


@dataclass(frozen=True)
class ResolvedDependencies:
    runtime: InstalledProfile
    sdk: PackagePin
    ui: InstalledProfile | None = None
    kit: PackagePin | None = None
    bridge: PackagePin | None = None

    def manifest(self) -> DependencyManifest:
        ui_build = None
        if self.ui is not None and self.kit is not None and self.bridge is not None:
            ui_build = UiBuildRef(
                profile_id=self.ui.profile_id,
                manifest_sha256=self.ui.profile.manifest_sha256,
                kit=self.kit,
                bridge=self.bridge,
            )
        return DependencyManifest(
            runtime_profile_id=self.runtime.profile_id,
            runtime_profile_manifest_sha256=self.runtime.profile.manifest_sha256,
            sdk=SdkPin(
                name=self.sdk.name,
                version=self.sdk.version,
                artifact_sha256=self.sdk.artifact_sha256,
            ),
            ui_build=ui_build,
        )


@dataclass(frozen=True)
class SealedPackage:
    path: Path
    version_id: str
    source: AppSource
    index: PackageIndex
    dependency_manifest: DependencyManifest
    dependency_manifest_sha256: str
    ui_build: dict[str, Any] | None

    @property
    def package_sha256(self) -> str:
        return self.index.package_sha256


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


def resolve_dependencies(source: AppSource, inventory: ProfileInventory) -> ResolvedDependencies:
    """Exact identities for the source's profile selections, from profiles re-verified on disk
    (a changed lock, artifact or interpreter quarantines the profile and fails here)."""
    runtime = inventory.verified(source.runtime_profile)
    if (
        runtime.profile.kind is not ProfileKind.PYTHON_RUNTIME
        or runtime.profile.role is not ProfileRole.APP_TASK_COMPUTE
    ):
        raise invalid(
            f"runtime_profile {source.runtime_profile} is not an App/Task Python runtime profile"
        )
    sdk = next((p for p in runtime.profile.packages if p.name == "alpha-sdk"), None)
    if sdk is None or source.sdk_version != sdk.version:
        raise invalid(
            f"sdk_version {source.sdk_version!r} does not match the runtime profile's SDK "
            f"{sdk.version if sdk else 'none'}"
        )
    if source.modules:
        raise UnsupportedDependencies(
            [
                DependencyQualificationRequest(
                    package=name,
                    version=version,
                    found_in="app.yaml modules",
                    where="app.yaml",
                    runtime_profile_id=runtime.profile_id,
                    reason="not in the qualified runtime profile; a new profile must be "
                    "built and qualified before any App can use it",
                )
                for name, version in sorted(source.modules.items())
            ]
        )
    ui = source.ui
    if ui is None or ui.entry is None or ui.build_profile is None:
        return ResolvedDependencies(runtime=runtime, sdk=sdk)
    ui_profile = inventory.verified(ui.build_profile)
    if ui_profile.profile.kind is not ProfileKind.UI_BUILD:
        raise invalid(f"ui.build_profile {ui.build_profile} is not a UI build profile")
    pins = {p.name: p for p in ui_profile.profile.packages}
    kit, bridge = pins.get("@alpha/ui-kit"), pins.get("@alpha/ui-bridge")
    if kit is None or bridge is None:
        raise invalid(f"UI build profile {ui.build_profile} has no kit or bridge")
    if ui.kit_version != kit.version or ui.bridge_version != bridge.version:
        raise invalid(
            f"ui asks for kit {ui.kit_version} and bridge {ui.bridge_version}; profile "
            f"{ui.build_profile} has kit {kit.version} and bridge {bridge.version}"
        )
    return ResolvedDependencies(runtime=runtime, sdk=sdk, ui=ui_profile, kit=kit, bridge=bridge)


def _check_file(path: Path, rel: str, root: Path, suffixes: set[str]) -> None:
    if path.is_symlink():
        raise invalid(f"{rel} is a symbolic link; packages cannot contain links")
    if not path.resolve().is_relative_to(root):
        raise invalid(f"{rel} points outside the package")
    if not path.is_file():
        raise invalid(f"{rel} is not a regular file")
    if path.suffix not in suffixes:
        raise invalid(f"{rel} has a file type packages cannot contain here")
    if path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        raise invalid(f"{rel} is executable; packages cannot contain executables")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise invalid(f"{rel} is larger than {MAX_FILE_BYTES} bytes")


def collect_files(package_dir: Path, source: AppSource) -> list[Path]:
    """Every file that becomes part of the Version, after refusing anything unsafe."""
    root = package_dir.resolve()
    has_ui = source.ui is not None and source.ui.entry is not None
    for entry in sorted(package_dir.iterdir()):
        name = entry.name
        if name in _IGNORED or name == "app.yaml":
            continue
        if name in _DEPENDENCY_FILES:
            raise invalid(
                f"{name} declares dependencies or an environment; the platform owns them "
                "(declare nothing, or request a qualified profile)"
            )
        if name.startswith(".env") or name == ".env":
            raise invalid(f"{name} is an environment file; packages cannot contain one")
        if name in _PLATFORM_FILES:
            raise invalid(f"{name} is produced by the platform; the package cannot supply it")
        if name == "README.md" and entry.is_file() and not entry.is_symlink():
            continue
        if name in {"src", "tests"} or (name == "ui" and has_ui):
            if entry.is_symlink() or not entry.is_dir():
                raise invalid(f"{name}/ must be a directory")
            continue
        if name == "ui":
            raise invalid("ui/ is present but app.yaml declares no ui.entry")
        raise invalid(f"{name} is not part of the App package layout")
    src = package_dir / "src"
    if not src.is_dir():
        raise invalid("the package has no src/ directory")
    selected: list[Path] = [package_dir / "app.yaml"]
    if (package_dir / "README.md").is_file():
        selected.append(package_dir / "README.md")
    areas = [("src", SRC_SUFFIXES), ("tests", TEST_SUFFIXES)]
    if has_ui:
        areas.append(("ui", UI_SUFFIXES))
    for area, suffixes in areas:
        base = package_dir / area
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            rel = path.relative_to(package_dir)
            if any(part in _IGNORED for part in rel.parts):
                continue
            if path.is_dir() and not path.is_symlink():
                if path.name in {"node_modules", ".venv"}:
                    raise invalid(f"{rel.as_posix()} is an installed environment")
                continue
            _check_file(path, rel.as_posix(), root, suffixes)
            selected.append(path)
    if has_ui and not (package_dir / UI_ENTRY).is_file():
        raise invalid(f"app.yaml declares a UI but {UI_ENTRY} is missing")
    if len(selected) > MAX_FILES:
        raise invalid(f"the package has more than {MAX_FILES} files")
    if sum(p.stat().st_size for p in selected) > MAX_PACKAGE_BYTES:
        raise invalid(f"the package is larger than {MAX_PACKAGE_BYTES} bytes")
    return selected


def make_writable(root: Path) -> None:
    if not root.exists():
        return
    root.chmod(root.stat().st_mode | stat.S_IWUSR)
    for path in root.rglob("*"):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode | stat.S_IWUSR)


def remove_tree(root: Path) -> None:
    make_writable(root)
    shutil.rmtree(root, ignore_errors=True)


def seal_tree(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    root.chmod(root.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _entry(root: Path, rel: str) -> PackageFile:
    path = root / rel
    return PackageFile(path=rel, sha256=sha256_file(path), size=path.stat().st_size)


def seal(
    package_dir: Path,
    source: AppSource,
    deps: ResolvedDependencies,
    files: list[Path],
    dest_root: Path,
    ui_builder: UiBuilder | None,
) -> SealedPackage:
    """Copy, build, index and seal a Version under `dest_root/<version_id>` (content-addressed:
    an existing identical Version is re-verified and reused)."""
    dest_root.mkdir(parents=True, exist_ok=True)
    staging = dest_root / f".staging-{uuid.uuid4().hex[:12]}"
    try:
        staging.mkdir(parents=True)
        rels: list[str] = []
        for path in files:
            rel = path.relative_to(package_dir).as_posix()
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            rels.append(rel)
        ui_report: dict[str, Any] | None = None
        if deps.ui is not None:
            if ui_builder is None:
                raise UiBuildFailed("no UI toolchain is configured on this Mac")
            ui_report = ui_builder(staging / "ui" / "src", staging / "dist" / "ui", deps.ui)
            rels += [
                p.relative_to(staging).as_posix()
                for p in sorted((staging / "dist" / "ui").rglob("*"))
                if p.is_file()
            ]
        # Profile locks travel with the Version as provenance; the installation stays shared.
        for area, profile in (("python", deps.runtime), ("ui", deps.ui)):
            if profile is None:
                continue
            for lock in profile.profile.locks:
                rel = f"dependencies/{area}/{lock.path}"
                (staging / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(profile.location / lock.path, staging / rel)
                if sha256_file(staging / rel) != lock.sha256:
                    raise conflict(f"lock {lock.path} changed while it was being copied")
                rels.append(rel)
        manifest = deps.manifest()
        manifest_bytes = canonical_json(manifest.model_dump(mode="json"))
        (staging / "dependency.manifest.json").write_bytes(manifest_bytes)
        manifest_sha = hashlib.sha256(manifest_bytes).hexdigest()
        rels.append("dependency.manifest.json")
        entries = sorted((_entry(staging, rel) for rel in rels), key=lambda e: e.path)
        toolchain = {
            "python": str(deps.runtime.profile.target.python_version),
            "sdk": deps.sdk.version,
            "worker_protocol": str(deps.runtime.profile.compatibility.worker_protocol),
        }
        if deps.ui is not None and deps.kit is not None and deps.bridge is not None:
            toolchain |= {
                "ui_build_profile": deps.ui.profile_id,
                "node": str((deps.ui.profile.target.ui_toolchain or {}).get("node")),
                "kit": deps.kit.version,
                "bridge": deps.bridge.version,
            }
        body = {
            "contract_version": "0.2",
            "app_id": source.app_id,
            "files": [e.model_dump(mode="json") for e in entries],
            "dependency_manifest_sha256": manifest_sha,
            "toolchain": toolchain,
        }
        package_sha = hashlib.sha256(canonical_json(body)).hexdigest()
        index = PackageIndex.model_validate({**body, "package_sha256": package_sha})
        (staging / "package.index.json").write_bytes(canonical_json(index.model_dump(mode="json")))
        version_id = f"ver_{package_sha[:24]}"
        target = dest_root / version_id
        if target.exists():
            remove_tree(staging)
            verify_sealed(target, package_sha)
        else:
            seal_tree(staging)
            staging.chmod(staging.stat().st_mode | stat.S_IWUSR)
            os.rename(staging, target)
            target.chmod(target.stat().st_mode & ~stat.S_IWUSR)
        return SealedPackage(
            path=target,
            version_id=version_id,
            source=source,
            index=index,
            dependency_manifest=manifest,
            dependency_manifest_sha256=manifest_sha,
            ui_build=ui_report,
        )
    finally:
        if staging.exists():
            remove_tree(staging)


def verify_sealed(version_dir: Path, expected_package_sha256: str | None = None) -> PackageIndex:
    """Recheck a sealed Version byte for byte: every indexed file, nothing unindexed, and the
    index's own digest. Raises `conflict` on any difference."""
    try:
        index = PackageIndex.model_validate_json((version_dir / "package.index.json").read_bytes())
    except (OSError, ValidationError) as exc:
        raise conflict(f"sealed version {version_dir.name} has no readable index: {exc}") from None
    body = {k: v for k, v in index.model_dump(mode="json").items() if k != "package_sha256"}
    if hashlib.sha256(canonical_json(body)).hexdigest() != index.package_sha256:
        raise conflict(f"sealed version {version_dir.name}: the index was altered")
    if expected_package_sha256 and index.package_sha256 != expected_package_sha256:
        raise conflict(f"sealed version {version_dir.name} is not the validated package")
    indexed = {e.path for e in index.files} | {"package.index.json"}
    for entry in index.files:
        path = version_dir / entry.path
        if path.is_symlink() or not path.is_file() or sha256_file(path) != entry.sha256:
            raise conflict(f"sealed version {version_dir.name}: {entry.path} changed or is missing")
    extra = [
        p.relative_to(version_dir).as_posix()
        for p in version_dir.rglob("*")
        if p.is_file() and p.relative_to(version_dir).as_posix() not in indexed
    ]
    if extra:
        raise conflict(f"sealed version {version_dir.name} gained unindexed files: {extra[:5]}")
    manifest_bytes = (version_dir / "dependency.manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != index.dependency_manifest_sha256:
        raise conflict(f"sealed version {version_dir.name}: dependency manifest changed")
    return index


def sealed_manifest(version_dir: Path) -> DependencyManifest:
    return DependencyManifest.model_validate(
        json.loads((version_dir / "dependency.manifest.json").read_bytes())
    )
