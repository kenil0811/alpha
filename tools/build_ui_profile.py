"""Build and publish the managed UI build profile (Implementation Blueprint §10, F06).

Trusted build path, run by `just bundle-core`. Generated App UI is compiled only against this
profile, never against the repository's workspace sources:

1. compile `@alpha/ui-bridge` and `@alpha/ui-kit` to JavaScript and `pnpm pack` them (the tarballs
   are byte-reproducible, so identical sources give identical identities);
2. in a staging directory outside the pnpm workspace, write an exact package.json (tarballs by
   file, React/Vite/plugin at exact versions, the kit's bridge dependency overridden to the same
   tarball) and install offline with copied files, no lifecycle scripts, then re-install with
   `--frozen-lockfile` to prove the lock is complete;
3. inventory the whole installed closure (name, version, installed-tree SHA-256, lock integrity),
   remove `.bin` shims (they embed staging paths and nothing runs them), seal read-only and publish
   atomically as `<root>/uiprof-<id>`.

Usage: python tools/build_ui_profile.py [--root DIR]
Prints one JSON line: {"profile_id", "manifest_sha256", "path", "published"}.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from alpha.execution.profiles import sha256_file, tree_digest, verify_profile_dir
from alpha_contracts import CONTRACT_VERSION
from alpha_contracts.profiles import seal_profile

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = REPO_ROOT / ".alpha-runtime" / "profiles"
MEMBERS = (
    ("@alpha/ui-bridge", REPO_ROOT / "packages" / "ui-bridge"),
    ("@alpha/ui-kit", REPO_ROOT / "packages" / "ui-kit"),
)
# Third-party packages the UI build needs, pinned to the versions the kit is developed against.
EXTERNAL = ("react", "react-dom", "vite", "@vitejs/plugin-react")


def run(argv: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stdout[-1500:]}\n"
            f"{result.stderr[-1500:]}"
        )
    return result.stdout


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


def seal_readonly(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    root.chmod(root.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def external_versions() -> dict[str, str]:
    kit = json.loads((REPO_ROOT / "packages" / "ui-kit" / "package.json").read_text("utf-8"))
    pins = {**kit.get("devDependencies", {}), **kit.get("peerDependencies", {})}
    out = {}
    for name in EXTERNAL:
        version = pins.get(name)
        if not version or not version[0].isdigit():
            raise SystemExit(f"{name} must be pinned to an exact version in packages/ui-kit")
        out[name] = version
    return out


def lock_integrity(lock: dict[str, Any]) -> dict[str, str]:
    """name@version -> integrity (or tarball) from the pnpm lock's packages section."""
    out: dict[str, str] = {}
    for key, entry in (lock.get("packages") or {}).items():
        resolution = (entry or {}).get("resolution") or {}
        value = resolution.get("integrity") or resolution.get("tarball")
        if value:
            out[str(key)] = str(value)
    return out


def inventory(node_modules: Path, integrity: dict[str, str]) -> list[dict[str, Any]]:
    """Every installed package in the closure (the real directory inside each .pnpm entry)."""
    pins: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in sorted((node_modules / ".pnpm").iterdir()):
        inner = entry / "node_modules"
        if not inner.is_dir():
            continue
        candidates: list[Path] = []
        for child in inner.iterdir():
            if child.name.startswith("@") and child.is_dir() and not child.is_symlink():
                candidates += [c for c in child.iterdir() if c.is_dir() and not c.is_symlink()]
            elif child.is_dir() and not child.is_symlink() and child.name != ".bin":
                candidates.append(child)
        for package_dir in candidates:
            meta = json.loads((package_dir / "package.json").read_text("utf-8"))
            name, version = str(meta["name"]), str(meta["version"])
            digest = str(tree_digest(package_dir)["sha256"])
            key = next(
                (k for k in integrity if k == f"{name}@{version}" or k.startswith(f"{name}@file:")),
                None,
            )
            pins[(name, version, digest)] = {
                "name": name,
                "version": version,
                "artifact_sha256": digest,
                "artifact": integrity.get(key, "installed-tree") if key else "installed-tree",
            }
    return sorted(pins.values(), key=lambda p: (p["name"], p["version"]))


def build(root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    for leftover in root.glob(".staging-ui-*"):
        remove_tree(leftover)
    staging = root / f".staging-ui-{uuid.uuid4().hex[:12]}"
    packages = staging / "packages"
    packages.mkdir(parents=True)
    try:
        node_version = run(["node", "--version"]).strip().lstrip("v")
        pnpm_version = run(["pnpm", "--version"]).strip()
        tarballs: dict[str, dict[str, str]] = {}
        for name, source in MEMBERS:
            dist = source / "dist"
            if dist.exists():
                shutil.rmtree(dist)
            run(["pnpm", "run", "build"], cwd=source)
            before = set(packages.glob("*.tgz"))
            run(["pnpm", "pack", "--pack-destination", str(packages)], cwd=source)
            (tgz,) = sorted(set(packages.glob("*.tgz")) - before)
            version = json.loads((source / "package.json").read_text("utf-8"))["version"]
            tarballs[name] = {"file": tgz.name, "version": version, "sha256": sha256_file(tgz)}
            shutil.rmtree(dist, ignore_errors=True)
        externals = external_versions()
        manifest_pkg = {
            "name": "alpha-ui-build-profile",
            "private": True,
            "type": "module",
            "dependencies": {
                **{name: f"file:./packages/{t['file']}" for name, t in tarballs.items()},
                **externals,
            },
            "pnpm": {
                "overrides": {
                    "@alpha/ui-bridge": f"file:./packages/{tarballs['@alpha/ui-bridge']['file']}"
                }
            },
        }
        (staging / "package.json").write_text(json.dumps(manifest_pkg, indent=2) + "\n", "utf-8")
        install = [
            "pnpm",
            "install",
            "--ignore-workspace",
            "--offline",
            "--config.package-import-method=copy",
            "--config.node-linker=isolated",
            "--ignore-scripts",
        ]
        run(install, cwd=staging)
        run([*install, "--frozen-lockfile"], cwd=staging)
        node_modules = staging / "node_modules"
        for bin_dir in [p for p in node_modules.rglob(".bin") if p.is_dir()]:
            shutil.rmtree(bin_dir)
        for name, version in {
            **{n: t["version"] for n, t in tarballs.items()},
            **externals,
        }.items():
            installed = json.loads((node_modules / name / "package.json").read_text("utf-8"))
            if installed["version"] != version:
                raise SystemExit(f"{name} installed {installed['version']}, expected {version}")
        lock = yaml.safe_load((staging / "pnpm-lock.yaml").read_text("utf-8"))
        pins = inventory(node_modules, lock_integrity(lock))
        for name, t in tarballs.items():
            for pin in pins:
                if pin["name"] == name:
                    pin["artifact"] = t["file"]
                    pin["tarball_sha256"] = t["sha256"]
        content = {
            "kind": "ui_build",
            "role": "app_task_compute",
            "target": {
                "os": {"Darwin": "macos"}.get(platform.system(), platform.system().lower()),
                "arch": platform.machine(),
                "ui_toolchain": {"node": node_version, "pnpm": pnpm_version, **externals},
            },
            "locks": [
                {"path": "package.json", "sha256": sha256_file(staging / "package.json")},
                {"path": "pnpm-lock.yaml", "sha256": sha256_file(staging / "pnpm-lock.yaml")},
            ],
            "packages": [
                {
                    k: v
                    for k, v in pin.items()
                    if k in ("name", "version", "artifact_sha256", "artifact")
                }
                for pin in pins
            ],
            "compatibility": {
                "contract_version": CONTRACT_VERSION,
                "kit_version": tarballs["@alpha/ui-kit"]["version"],
                "bridge_version": tarballs["@alpha/ui-bridge"]["version"],
            },
        }
        profile = seal_profile(content, prefix="ui")
        target = root / profile.profile_id
        if target.exists():
            problems = verify_profile_dir(target)[2]
            remove_tree(staging)
            if problems:
                raise SystemExit(
                    f"published profile {profile.profile_id} fails verification: {problems}"
                )
            return {
                "profile_id": profile.profile_id,
                "manifest_sha256": profile.manifest_sha256,
                "path": str(target),
                "published": False,
            }
        (staging / "manifest.json").write_text(profile.model_dump_json(indent=2) + "\n", "utf-8")
        installation = {
            "profile_id": profile.profile_id,
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "node": {"version": node_version, "path": shutil.which("node")},
            "pnpm_version": pnpm_version,
            "tarballs": tarballs,
            "node_modules_tree": tree_digest(node_modules),
            "note": "host-local installation record; not portable",
        }
        (staging / "installation.json").write_text(
            json.dumps(installation, indent=2) + "\n", "utf-8"
        )
        seal_readonly(staging)
        staging.chmod(staging.stat().st_mode | stat.S_IWUSR)
        os.rename(staging, target)
        target.chmod(target.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        problems = verify_profile_dir(target)[2]
        if problems:
            raise SystemExit(f"published profile failed verification: {problems}")
        return {
            "profile_id": profile.profile_id,
            "manifest_sha256": profile.manifest_sha256,
            "path": str(target),
            "published": True,
        }
    finally:
        if staging.exists():
            remove_tree(staging)
        for _name, source in MEMBERS:
            shutil.rmtree(source / "dist", ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.root.resolve())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
