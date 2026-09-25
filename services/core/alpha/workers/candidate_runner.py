"""Disposable candidate runner.

Resolves a declared action's real handler inside the candidate package and executes it with the
supplied inputs, in this throwaway process, never in Core. Output is JSON lines: one result line
with per-call outcomes, or an error line with a precise reason (missing module, missing symbol,
not callable, signature mismatch, exception).

Job shape: {"package_dir": "<dir>", "action_id": "<id>", "calls": [{"input": {...}}, ...]}
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
import traceback
from pathlib import Path
from typing import Any

import yaml


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, default=str) + "\n")
    sys.stdout.flush()


def load_manifest(package_dir: Path) -> dict[str, Any]:
    manifest_path = package_dir / "app.yaml"
    if not manifest_path.is_file():
        raise FileNotFoundError("app.yaml missing")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("app.yaml is not a mapping")
    return data


def main() -> int:
    sys.dont_write_bytecode = True
    job = json.loads(sys.stdin.readline() or "{}")
    package_dir = Path(str(job.get("package_dir", "")))
    action_id = str(job.get("action_id", ""))
    calls = list(job.get("calls", []))
    try:
        manifest = load_manifest(package_dir)
        actions = manifest.get("actions") or []
        action = next(
            (a for a in actions if isinstance(a, dict) and a.get("id") == action_id), None
        )
        if action is None:
            raise LookupError(f"action {action_id!r} not declared in app.yaml")
        handler = str(action.get("handler", ""))
        module_name, _, function_name = handler.partition(":")
        if not module_name or not function_name:
            raise ValueError(f"handler must be module:function, got {handler!r}")
        src = package_dir / "src"
        if not src.is_dir():
            raise FileNotFoundError("package src/ directory missing")
        # The only import path is the candidate's src/; -I already excludes ambient paths.
        sys.path[:0] = [str(src)]
        module = importlib.import_module(module_name)
        function = getattr(module, function_name, None)
        if function is None:
            raise AttributeError(f"module {module_name!r} has no attribute {function_name!r}")
        if not callable(function):
            raise TypeError(f"{handler} is not callable")
        signature = inspect.signature(function)
    except Exception as exc:
        emit({"kind": "error", "code": type(exc).__name__, "message": str(exc)[:500]})
        return 3

    outcomes: list[dict[str, Any]] = []
    for index, call in enumerate(calls):
        payload = call.get("input") if isinstance(call, dict) else None
        if not isinstance(payload, dict):
            outcomes.append({"index": index, "ok": False, "error": "input must be an object"})
            continue
        try:
            signature.bind(**payload)
        except TypeError as exc:
            outcomes.append({"index": index, "ok": False, "error": f"signature mismatch: {exc}"})
            continue
        try:
            result = function(**payload)
            json.dumps(result)
            outcomes.append({"index": index, "ok": True, "output": result})
        except Exception as exc:
            outcomes.append(
                {
                    "index": index,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}"[:500],
                    "traceback": traceback.format_exc()[-1500:],
                }
            )
    emit(
        {
            "kind": "result",
            "output": {"handler": handler, "signature": str(signature), "calls": outcomes},
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
