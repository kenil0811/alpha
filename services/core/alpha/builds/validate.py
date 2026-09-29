"""The builder's own check, before it hands over.

The platform's first verification stages are mechanical: app.yaml parses and matches the
contract, the files follow the layout, the Python compiles, every action's handler resolves.
A builder that cannot run them itself learns of a typo only after a full repair round (found
live: one colon in a description cost eight minutes). So each attempt gets a `validate`
script that applies exactly these rules, from the same code the verifier uses, and prints
what is wrong in plain lines. It never runs an action and never touches stored data.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from alpha.capabilities.errors import OperationFailed
from alpha.data.packages import collect_files, load_source

SCRIPT_NAME = "validate"

# Runs on the App profile's interpreter with the package's src on the path: compiles every
# module and resolves each handler, printing one JSON line per problem.
_HANDLER_PROBE = r"""
import compileall, importlib, json, sys
src, handlers = sys.argv[1], json.loads(sys.argv[2])
sys.path.insert(0, src)
if not compileall.compile_dir(src, quiet=2, force=True):
    print(json.dumps("a Python file under src/ does not compile (run it to see the line)"))
for action, spec in handlers:
    module, _, function = spec.partition(":")
    try:
        target = importlib.import_module(module)
    except Exception as exc:
        print(json.dumps(f"action {action}: cannot import {module}: {type(exc).__name__}: {exc}"))
        continue
    if not callable(getattr(target, function, None)):
        print(json.dumps(f"action {action}: {module} has no function {function}"))
"""


def validate_package(package_dir: Path, app_python: Path) -> list[str]:
    """Every problem the platform's package and handler stages would report, or none."""
    try:
        source = load_source(package_dir)
    except OperationFailed as exc:
        return [exc.message, *(str(p) for p in exc.details.get("problems", []))]
    try:
        collect_files(package_dir, source)
    except OperationFailed as exc:
        return [exc.message]
    src = package_dir / "src"
    if not src.is_dir():
        return ["the package has no src/ directory"]
    handlers = [(a.id, a.handler) for a in source.actions]
    probe = subprocess.run(
        [str(app_python), "-c", _HANDLER_PROBE, str(src), json.dumps(handlers)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(src),
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    problems = [json.loads(line) for line in probe.stdout.splitlines() if line.startswith('"')]
    if probe.returncode != 0 and not problems:
        problems.append(f"the handler check itself failed: {probe.stderr.strip()[-400:]}")
    return problems


def write_validate_script(workspace: Path, app_python: Path) -> Path:
    """An executable `validate` in the attempt directory: the one command the builder runs."""
    script = workspace / SCRIPT_NAME
    script.write_text(
        "#!/bin/sh\n"
        f'exec "{sys.executable}" -m alpha.builds.validate "{workspace / "package"}" '
        f'"{app_python}"\n',
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: validate <package_dir> <app_python>", file=sys.stderr)
        return 2
    problems = validate_package(Path(argv[1]), Path(argv[2]))
    if not problems:
        print("OK: app.yaml matches the contract, files follow the layout, handlers resolve.")
        return 0
    print(f"{len(problems)} problem(s):")
    for problem in problems:
        print(f"- {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
