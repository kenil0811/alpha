"""F01.C05: committed locks and exact tool versions govern installs.

- uv version must equal the pin in pyproject (`tool.uv.required-version`).
- pnpm version must equal `packageManager` in package.json.
- `uv lock --check` must pass against the committed uv.lock.
- `pnpm install --frozen-lockfile --offline` must be satisfiable (no lock drift).
- A deliberately altered copy of uv.lock must fail `uv lock --check`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _version(argv: list[str]) -> str:
    out = subprocess.run(argv, capture_output=True, text=True, check=True).stdout.strip()
    match = re.search(r"\d+\.\d+\.\d+", out)
    return match.group(0) if match else out


def main() -> int:
    failures: list[str] = []
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    required_uv = pyproject["tool"]["uv"]["required-version"].lstrip("=")
    actual_uv = _version(["uv", "--version"])
    print(f"uv: required {required_uv}, actual {actual_uv}")
    if actual_uv != required_uv:
        failures.append("uv version mismatch")

    package_json = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    required_pnpm = package_json["packageManager"].split("@", 1)[1]
    actual_pnpm = _version(["pnpm", "--version"])
    print(f"pnpm: required {required_pnpm}, actual {actual_pnpm}")
    if actual_pnpm != required_pnpm:
        failures.append("pnpm version mismatch")

    required_node = package_json["engines"]["node"]
    actual_node = _version(["node", "--version"])
    print(f"node: required {required_node}, actual {actual_node}")
    if actual_node != required_node:
        failures.append("node version mismatch")

    python_version = (REPO_ROOT / ".python-version").read_text().strip()
    print(f"python: pinned {python_version}, running {sys.version.split()[0]}")
    if sys.version.split()[0] != python_version:
        failures.append("python version mismatch")

    lock_check = subprocess.run(
        ["uv", "lock", "--check"], cwd=REPO_ROOT, capture_output=True, text=True
    )
    print(f"uv lock --check: exit {lock_check.returncode}")
    if lock_check.returncode != 0:
        failures.append("uv.lock drift: " + lock_check.stderr.strip()[-300:])

    pnpm_check = subprocess.run(
        ["pnpm", "install", "--frozen-lockfile", "--offline", "--ignore-scripts"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    print(f"pnpm install --frozen-lockfile --offline: exit {pnpm_check.returncode}")
    if pnpm_check.returncode != 0:
        failures.append(
            "pnpm lock drift: " + (pnpm_check.stderr or pnpm_check.stdout).strip()[-300:]
        )

    # Negative control: a changed lock must fail visibly.
    with tempfile.TemporaryDirectory() as tmp:
        clone = Path(tmp) / "repo"
        clone.mkdir()
        for name in ("pyproject.toml", ".python-version", "uv.lock"):
            shutil.copy(REPO_ROOT / name, clone / name)
        for member in ("packages/contracts", "services/core"):
            (clone / member).mkdir(parents=True)
            shutil.copy(REPO_ROOT / member / "pyproject.toml", clone / member / "pyproject.toml")
        lock = clone / "uv.lock"
        text = lock.read_text(encoding="utf-8")
        tampered = text.replace(
            'name = "fastapi"\nversion = "', 'name = "fastapi"\nversion = "0.', 1
        )
        assert tampered != text
        lock.write_text(tampered, encoding="utf-8")
        tampered_check = subprocess.run(
            ["uv", "lock", "--check", "--offline"], cwd=clone, capture_output=True, text=True
        )
        print(f"tampered uv.lock --check: exit {tampered_check.returncode} (expected nonzero)")
        if tampered_check.returncode == 0:
            failures.append("tampered lock was accepted")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("locks and tool versions verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
