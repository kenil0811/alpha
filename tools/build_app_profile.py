"""Build and publish the default App/Task Python runtime profile (Implementation Blueprint §10).

Trusted build path, run by `just bundle-core` (never by Core at App startup, never by a builder):

1. build the SDK and App worker wheels from source (hatchling builds are reproducible, so the
   same source always yields the same bytes and therefore the same profile identity);
2. write a hash-pinned lock (requirements.lock) that names every artifact with its SHA-256;
3. in a staging directory, create a venv on the pinned uv-managed CPython and install exactly the
   locked artifacts (`--require-hashes --no-deps --no-index`, bytecode compiled at install time
   so workers never need to write bytecode);
4. validate (imports, versions, no unexpected distributions), compute the portable manifest and
   the host-local installation record (tree digest of the installed files);
5. seal (read-only) and publish atomically by renaming staging to `<root>/<profile_id>`.

Publishing is idempotent: if the derived profile already exists and verifies, nothing changes.
A crash leaves only a `.staging-*` directory, which the next run removes.

Usage: python tools/build_app_profile.py [--root DIR] [--python INTERPRETER]
Prints one JSON line: {"profile_id": ..., "manifest_sha256": ..., "path": ..., "published": bool}
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Core verifies published profiles with exactly these functions at startup.
from alpha.execution.profiles import sha256_file, tree_digest, verify_profile_dir
from alpha_contracts import CONTRACT_VERSION
from alpha_contracts.broker import WORKER_PROTOCOL_VERSION
from alpha_contracts.profiles import seal_profile

REPO_ROOT = Path(__file__).resolve().parents[1]

MEMBERS = (
    ("alpha-sdk", "alpha_sdk", REPO_ROOT / "packages" / "app-sdk"),
    ("alpha-app-worker", "alpha_app_worker", REPO_ROOT / "workers" / "app"),
)
SDK_NAME = "alpha-sdk"
DEFAULT_ROOT = REPO_ROOT / ".alpha-runtime" / "profiles"
PYTHON_VERSION = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()


def run(argv: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(
            f"command failed ({result.returncode}): {' '.join(argv)}\n{result.stderr[-2000:]}"
        )
    return result.stdout


def default_interpreter() -> Path:
    runtime = sorted(
        (REPO_ROOT / ".alpha-runtime" / "python").glob(f"cpython-{PYTHON_VERSION}-*/bin/python3")
    )
    if runtime:
        return runtime[0]
    return Path(sys.base_prefix) / "bin" / "python3"


def interpreter_build(interpreter: Path) -> str:
    return interpreter.resolve().parent.parent.name


def seal_readonly(root: Path) -> None:
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_symlink():
            continue
        mode = path.stat().st_mode
        path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    root.chmod(root.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


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


def verify_published(target: Path) -> list[str]:
    """Re-verify a published profile directory; empty list means intact."""
    return verify_profile_dir(target)[2]


def build(root: Path, interpreter: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    for leftover in root.glob(".staging-*"):
        remove_tree(leftover)
    staging = root / f".staging-{uuid.uuid4().hex[:12]}"
    wheels = staging / "wheels"
    wheels.mkdir(parents=True)
    try:
        uv_version = run(["uv", "--version"]).strip()
        pins: list[dict[str, object]] = []
        lock_lines = [
            "# Alpha default App/Task runtime profile lock (tools/build_app_profile.py).",
            "# Every artifact is pinned by SHA-256; install with --require-hashes --no-deps.",
        ]
        for name, _module, source in MEMBERS:
            before = set(wheels.glob("*.whl"))
            run(["uv", "build", "--wheel", "--no-sources", str(source), "-o", str(wheels), "-q"])
            built = sorted(set(wheels.glob("*.whl")) - before)
            if len(built) != 1:
                raise SystemExit(f"expected one wheel for {name}, got {built}")
            wheel = built[0]
            version = wheel.name.split("-")[1]
            digest = sha256_file(wheel)
            pins.append(
                {
                    "name": name,
                    "version": version,
                    "artifact_sha256": digest,
                    "artifact": wheel.name,
                }
            )
            lock_lines.append(f"{name} @ ./wheels/{wheel.name} --hash=sha256:{digest}")
        lock = staging / "requirements.lock"
        lock.write_text("\n".join(lock_lines) + "\n", encoding="utf-8")
        sdk = next(p for p in pins if p["name"] == SDK_NAME)
        content = {
            "kind": "python_runtime",
            "role": "app_task_compute",
            "target": {
                "os": {"Darwin": "macos"}.get(platform.system(), platform.system().lower()),
                "arch": platform.machine(),
                "python_implementation": "cpython",
                "python_version": PYTHON_VERSION,
                "python_abi": "cp" + "".join(PYTHON_VERSION.split(".")[:2]),
                "interpreter_build": interpreter_build(interpreter),
            },
            "locks": [{"path": "requirements.lock", "sha256": sha256_file(lock)}],
            "packages": pins,
            "compatibility": {
                "contract_version": CONTRACT_VERSION,
                "sdk_version": sdk["version"],
                "worker_protocol": WORKER_PROTOCOL_VERSION,
            },
        }
        profile = seal_profile(content)
        target = root / profile.profile_id
        if target.exists():
            problems = verify_published(target)
            if not problems:
                remove_tree(staging)
                return {
                    "profile_id": profile.profile_id,
                    "manifest_sha256": profile.manifest_sha256,
                    "path": str(target),
                    "published": False,
                }
            raise SystemExit(
                f"published profile {profile.profile_id} fails verification: {problems}; "
                "it will not be replaced in place (quarantine and remove it explicitly)"
            )
        venv = staging / "venv"
        run(["uv", "venv", str(venv), "--python", str(interpreter), "-q"])
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(venv / "bin" / "python"),
                "--require-hashes",
                "--no-deps",
                "--no-index",
                "--no-cache",
                "--compile-bytecode",
                "-r",
                "requirements.lock",
            ],
            cwd=staging,
        )
        # Activation scripts embed the staging path and are never used (workers run the
        # interpreter directly), so they are not part of the sealed installation.
        for script in (venv / "bin").glob("activate*"):
            script.unlink()
        for script in (venv / "bin").glob("deactivate*"):
            script.unlink()
        probe = (
            "import importlib.metadata as m, json, sys, alpha_sdk, alpha_app_worker.runner;"
            "print(json.dumps({'python': sys.version.split()[0],"
            " 'dists': sorted(d.metadata['Name'] + '==' + d.version for d in m.distributions()),"
            " 'sdk': alpha_sdk.__version__}))"
        )
        observed = json.loads(
            run([str(venv / "bin" / "python"), "-I", "-B", "-c", probe]).strip().splitlines()[-1]
        )
        expected = sorted(f"{p['name']}=={p['version']}" for p in pins)
        if observed["python"] != PYTHON_VERSION:
            raise SystemExit(f"profile python {observed['python']} != pinned {PYTHON_VERSION}")
        if observed["dists"] != expected:
            raise SystemExit(f"installed distributions {observed['dists']} != locked {expected}")
        (staging / "manifest.json").write_text(
            profile.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        resolved = interpreter.resolve()
        installation = {
            "profile_id": profile.profile_id,
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "uv_version": uv_version,
            "interpreter": str(resolved),
            "interpreter_sha256": sha256_file(resolved),
            "venv_tree": tree_digest(venv),
            "note": "host-local installation record; not portable",
        }
        (staging / "installation.json").write_text(
            json.dumps(installation, indent=2) + "\n", encoding="utf-8"
        )
        seal_readonly(staging)
        root.chmod(root.stat().st_mode | stat.S_IWUSR)
        staging.chmod(staging.stat().st_mode | stat.S_IWUSR)
        os.rename(staging, target)  # atomic publish on the same filesystem
        target.chmod(target.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        problems = verify_published(target)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--python", type=Path, default=None)
    args = parser.parse_args(argv)
    interpreter = args.python or default_interpreter()
    result = build(args.root.resolve(), interpreter)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
