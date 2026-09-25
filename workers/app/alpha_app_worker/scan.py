"""Static dependency scan of a sealed Version's Python source, run inside the exact runtime
profile so "standard library" means this interpreter's standard library.

Every import is classified. Anything that is not the standard library, the SDK or the package's
own modules is an undeclared dependency: the profile does not contain it, and nothing will ever
install it at run time. Platform internals (Core, the worker, contracts) are never importable by
generated code. A dynamic import with a computed name hides a dependency and is refused.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

SDK_MODULES = frozenset({"alpha_sdk"})
PLATFORM_MODULES = frozenset({"alpha", "alpha_app_worker", "alpha_contracts", "alpha_core"})
# Standard-library or bundled modules whose purpose is installing packages. Nothing is installed
# at run time, so generated code may not import them.
INSTALLER_MODULES = frozenset({"ensurepip", "pip", "venv", "setuptools", "pkg_resources"})


def local_modules(src: Path) -> set[str]:
    names: set[str] = set()
    for entry in src.iterdir():
        if entry.is_file() and entry.suffix == ".py":
            names.add(entry.stem)
        elif entry.is_dir() and any(entry.rglob("*.py")):
            names.add(entry.name)
    return names


def _dynamic_target(node: ast.Call) -> tuple[bool, str | None]:
    """(is a dynamic import call, its constant module name if any)."""
    func = node.func
    name = None
    if isinstance(func, ast.Name) and func.id == "__import__":
        name = "__import__"
    elif isinstance(func, ast.Attribute) and func.attr == "import_module":
        name = "import_module"
    if name is None:
        return False, None
    if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
        return True, node.args[0].value
    return True, None


def scan(src: Path) -> dict[str, Any]:
    local = local_modules(src)
    found: list[dict[str, Any]] = []
    problems: list[str] = []
    for path in sorted(src.rglob("*.py")):
        rel = path.relative_to(src.parent).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as exc:
            problems.append(f"{rel}:{exc.lineno}: syntax error: {exc.msg}")
            continue
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    modules = [node.module]
            elif isinstance(node, ast.Call):
                dynamic, target = _dynamic_target(node)
                if dynamic and target is None:
                    problems.append(
                        f"{rel}:{node.lineno}: dynamic import with a computed name hides a "
                        "dependency"
                    )
                elif dynamic and target is not None:
                    modules = [target]
            for module in modules:
                top = module.split(".", 1)[0]
                if top in PLATFORM_MODULES:
                    kind = "platform"
                elif top in INSTALLER_MODULES:
                    kind = "installer"
                elif top in SDK_MODULES:
                    kind = "sdk"
                elif top in local:
                    kind = "local"
                elif top in sys.stdlib_module_names:
                    kind = "stdlib"
                else:
                    kind = "undeclared"
                line = getattr(node, "lineno", 0)
                found.append({"module": module, "top": top, "kind": kind, "where": f"{rel}:{line}"})
    undeclared = [f for f in found if f["kind"] == "undeclared"]
    platform = [f for f in found if f["kind"] == "platform"]
    for item in platform:
        problems.append(
            f"{item['where']}: imports platform internals ({item['module']}); use alpha_sdk"
        )
    for item in (f for f in found if f["kind"] == "installer"):
        problems.append(
            f"{item['where']}: imports {item['top']}, which installs packages; nothing is "
            "installed at run time"
        )
    for item in undeclared:
        problems.append(
            f"{item['where']}: imports {item['top']!r}, which is not in the runtime profile"
        )
    return {
        "ok": not problems,
        "problems": problems,
        "undeclared": undeclared,
        "platform": platform,
        "stdlib": sorted({f["top"] for f in found if f["kind"] == "stdlib"}),
        "local": sorted({f["top"] for f in found if f["kind"] == "local"}),
        "uses_sdk": any(f["kind"] == "sdk" for f in found),
    }
