"""Prepare the platform-managed Core runtime at <repo>/.alpha-runtime.

The desktop host launches Core from this directory, never from the user's Python. It contains a
uv-managed CPython matching .python-version and an environment synced exactly from uv.lock
(workspace members are development links, which Implementation Blueprint §10 allows for platform
development; F22 replaces this with a signed, relocatable resource bundle).

The result is idempotent and records a manifest (core-runtime.json) with the interpreter path,
Python version and the uv.lock digest it was synced from.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME = REPO_ROOT / ".alpha-runtime"
PYTHON_DIR = RUNTIME / "python"
VENV = RUNTIME / "venv"
MANIFEST = RUNTIME / "core-runtime.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_digest() -> str:
    """Digest of the Core/contracts source that the runtime installs (non-editable), so a
    source edit invalidates the bundled runtime just like a lock change does."""
    digest = hashlib.sha256()
    for root in ("packages/contracts", "services/core"):
        base = REPO_ROOT / root
        for path in sorted(base.rglob("*")):
            if path.is_file() and path.suffix in {".py", ".toml"} and "tests" not in path.parts:
                digest.update(path.relative_to(REPO_ROOT).as_posix().encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def run(argv: list[str], **env: str) -> None:
    print("+", " ".join(argv), flush=True)
    subprocess.run(argv, cwd=REPO_ROOT, check=True, env={**os.environ, **env})


def main() -> int:
    version = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    lock_digest = sha256(REPO_ROOT / "uv.lock")
    sources = source_digest()
    if MANIFEST.exists():
        current = json.loads(MANIFEST.read_text(encoding="utf-8"))
        python = RUNTIME / current.get("python", "")
        if (
            current.get("uv_lock_sha256") == lock_digest
            and current.get("source_sha256") == sources
            and python.exists()
        ):
            print(f"core runtime up to date: {python} (python {current.get('python_version')})")
            return 0
    RUNTIME.mkdir(parents=True, exist_ok=True)
    run(
        ["uv", "python", "install", version, "--install-dir", str(PYTHON_DIR)],
        UV_PYTHON_INSTALL_DIR=str(PYTHON_DIR),
    )
    candidates = sorted(PYTHON_DIR.glob(f"cpython-{version}-*/bin/python3*"))
    interpreter = next((c for c in candidates if c.name == "python3"), candidates[0])
    run(["uv", "venv", str(VENV), "--python", str(interpreter), "--clear"])
    run(
        [
            "uv",
            "sync",
            "--frozen",
            "--no-dev",
            "--no-editable",
            "--reinstall-package",
            "alpha-core",
            "--reinstall-package",
            "alpha-contracts",
        ],
        UV_PROJECT_ENVIRONMENT=str(VENV),
        UV_PYTHON=str(interpreter),
    )
    venv_python = VENV / "bin" / "python"
    probe = (
        "import alpha.main, pathlib, sys;"
        " sys.stdout.write(pathlib.Path(alpha.main.__file__).read_text())"
    )
    installed = subprocess.run(
        [str(venv_python), "-I", "-c", probe], capture_output=True, text=True, check=True, env={}
    ).stdout
    if installed != (REPO_ROOT / "services/core/alpha/main.py").read_text(encoding="utf-8"):
        print("installed alpha.main differs from source; runtime is stale", file=sys.stderr)
        return 1
    check = subprocess.run(
        [
            str(venv_python),
            "-I",
            "-c",
            "import alpha, alpha_contracts, sys; print(sys.version.split()[0])",
        ],
        capture_output=True,
        text=True,
        check=True,
        env={},
    )
    observed = check.stdout.strip()
    if observed != version:
        print(f"runtime python {observed} != pinned {version}", file=sys.stderr)
        return 1
    manifest = {
        "python": str(venv_python.relative_to(RUNTIME)),
        "python_version": observed,
        "interpreter_source": str(interpreter.relative_to(RUNTIME)),
        "uv_lock_sha256": lock_digest,
        "source_sha256": sources,
        "created_at": datetime.now(UTC).isoformat(),
        "note": "development runtime; F22 supplies the signed relocatable bundle",
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"core runtime ready: {venv_python} (python {observed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
