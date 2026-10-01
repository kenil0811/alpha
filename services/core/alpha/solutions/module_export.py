"""Export an installed module as a portable `.alphamodule` file, and import one back in.

An `.alphamodule` is a zip of the module's *source* only — `app.yaml`, `src/`, `ui/src/` (never
the built `ui/dist/`), `tests/` and `README.md` — plus an `alphamodule.manifest.json` naming the
format, the module, this Alpha's core version, and a sha256 for every file it carries. Nothing
else: no records, no memories or facts, no secrets, tokens or connection credentials, no run
history. That is enforced structurally (only these source areas are ever read off disk) and
double-checked by name against common data/secret file patterns.

Importing re-runs the normal build pipeline (`AppRegistry.install`) on the extracted source, so an
imported module is validated and bound exactly like one Alpha built for itself — the same
dependency resolution, the same handler binding, the same rejections.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from alpha_contracts.apps import AppSource

from alpha import __version__ as ALPHA_CORE_VERSION
from alpha.capabilities.errors import OperationFailed, conflict, invalid
from alpha.solutions.registry import Activation, AppRegistry, AppVersion

FORMAT_VERSION = 1
MANIFEST_NAME = "alphamodule.manifest.json"
FILE_SUFFIX = ".alphamodule"

# A module can only ever contain code, its manifest and docs. Anything named like data or a
# secret is refused by name, even though the source areas below could never produce one.
_FORBIDDEN_NAME = re.compile(
    r"(?i)^(\.env(\..*)?|.*\.key|.*\.pem|.*secret.*|.*credential.*|.*token.*|records?\.db|"
    r"memories?\.db|\.git.*)$"
)


def _source_files(version_dir: Path, source: AppSource) -> list[str]:
    """Relative paths that make up the reusable capability: never the platform-produced
    `dependencies/`, `dist/`, `package.index.json` or `dependency.manifest.json` a sealed Version
    also carries, and never `ui/dist` — only the ui *source* a module was written with."""
    rels: list[str] = ["app.yaml"]
    if (version_dir / "README.md").is_file():
        rels.append("README.md")
    areas = ["src", "tests"]
    if source.ui is not None and source.ui.entry is not None:
        areas.append("ui/src")
    for area in areas:
        base = version_dir / area
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                rels.append(path.relative_to(version_dir).as_posix())
    return rels


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def export_module(registry: AppRegistry, app_id: str) -> bytes:
    """Package the module's current source into a portable `.alphamodule` zip's bytes."""
    version = registry.current(app_id)
    rels = _source_files(version.location, version.source)
    hashes: dict[str, str] = {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in rels:
            if _FORBIDDEN_NAME.match(Path(rel).name):
                # Defense in depth: a sealed Version never contains these (the build pipeline
                # refuses them by name before anything is sealed), so this should never fire.
                raise invalid(f"{rel} cannot be exported: it looks like data or a secret")
            data = (version.location / rel).read_bytes()
            hashes[rel] = _sha256(data)
            zf.writestr(rel, data)
        manifest = {
            "format_version": FORMAT_VERSION,
            "app_id": version.app_id,
            "name": version.source.name,
            "version_id": version.version_id,
            "release_id": version.release_id,
            "alpha_core_version": ALPHA_CORE_VERSION,
            "files": hashes,
        }
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True))
    return buf.getvalue()


@dataclass(frozen=True)
class ImportedModule:
    app_id: str
    name: str
    version_id: str
    release_id: str


def _unique_app_id(registry: AppRegistry, base_id: str) -> str:
    """`base_id` if free, else `base_id-2`, `base_id-3`, ... (an imported module never replaces
    one already installed)."""
    candidate = base_id
    suffix = 1
    while True:
        try:
            registry.current(candidate)
        except OperationFailed:
            return candidate
        suffix += 1
        candidate = f"{base_id}-{suffix}"[:64]


def import_module(registry: AppRegistry, data: bytes) -> ImportedModule:
    """Validate an `.alphamodule` file's bytes and install it as a new module. Raises
    `OperationFailed` with a plain-language reason for anything malformed, tampered with, or
    carrying something a module can't carry."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise invalid("that file isn't a project export — it's not even a zip file") from None

    names = set(zf.namelist())
    if MANIFEST_NAME not in names:
        raise invalid("that file is missing its project manifest — it isn't a valid project export")
    try:
        manifest = json.loads(zf.read(MANIFEST_NAME))
    except json.JSONDecodeError:
        raise invalid("the project manifest is unreadable") from None

    if manifest.get("format_version") != FORMAT_VERSION:
        raise invalid(f"this Alpha only reads project exports in format {FORMAT_VERSION}")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise invalid("the project manifest lists no files")
    for rel in files:
        if rel not in names:
            raise conflict(f"{rel} is listed in the manifest but missing from the file")
        if _FORBIDDEN_NAME.match(Path(rel).name):
            raise invalid(f"{rel} looks like data or a secret — projects can't carry either")
    extra = names - set(files) - {MANIFEST_NAME}
    if extra:
        raise invalid(f"{sorted(extra)[0]} isn't declared in the manifest — it can't be trusted")

    with tempfile.TemporaryDirectory(prefix="alpha-import-") as tmp:
        root = Path(tmp)
        for rel, expected_hash in files.items():
            raw = zf.read(rel)
            if _sha256(raw) != expected_hash:
                raise conflict(
                    f"{rel} doesn't match the manifest's hash — this file may have been altered "
                    "since it was exported"
                )
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)

        if not (root / "app.yaml").is_file():
            raise invalid("the project has no app.yaml — it isn't a valid project export")
        declared = manifest.get("app_id")
        if not isinstance(declared, str) or not declared:
            raise invalid("the project manifest names no project id")

        app_id = _unique_app_id(registry, declared)
        if app_id != declared:
            doc = yaml.safe_load((root / "app.yaml").read_text(encoding="utf-8")) or {}
            doc["app_id"] = app_id
            (root / "app.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")

        # The same pipeline a fresh build goes through: dependency resolution, file rules, the UI
        # build, sealing and handler binding. Anything that would fail a fresh module fails here.
        version: AppVersion = registry.install(root, Activation(kind="imported", origin="imported"))

    return ImportedModule(
        app_id=version.app_id,
        name=version.source.name,
        version_id=version.version_id,
        release_id=version.release_id,
    )
