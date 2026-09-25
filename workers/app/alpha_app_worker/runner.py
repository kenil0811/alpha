"""App worker runner (runs only inside the managed App runtime profile).

Launched by Core as `<profile python> -I -B -m alpha_app_worker` in a fresh process group with
private scratch as its working directory. The first stdin line is the job. The worker's original
stdout becomes the protocol stream; anything the handler prints goes to stderr, so generated code
cannot forge protocol messages by printing.

Modes:
  validate  scan every import, then import every declared handler and check its signature
            against the input schema
  tests     run the package's own tests/ with unittest (supplementary evidence only)
  invoke    run one action handler with a Context and emit its JSON result
"""

from __future__ import annotations

import importlib
import inspect
import io
import json
import os
import sys
import traceback
import unittest
from pathlib import Path
from typing import Any, TextIO

from alpha_sdk._channel import PROTOCOL_VERSION, PipeChannel
from alpha_sdk.context import Context, RunInfo
from alpha_sdk.errors import OperationError

from alpha_app_worker.scan import scan


def _emit(stream: TextIO, message: dict[str, Any]) -> None:
    stream.write(json.dumps(message, default=str) + "\n")
    stream.flush()


def _resolve(handler: str) -> Any:
    module_name, _, function_name = handler.partition(":")
    module = importlib.import_module(module_name)
    function = getattr(module, function_name, None)
    if function is None:
        raise AttributeError(f"module {module_name!r} has no attribute {function_name!r}")
    if not callable(function):
        raise TypeError(f"{handler} is not callable")
    return function


def check_signature(function: Any, input_schema: dict[str, Any]) -> list[str]:
    """Problems binding the declared input schema onto the handler (empty when compatible)."""
    problems: list[str] = []
    params = list(inspect.signature(function).parameters.values())
    if not params or params[0].kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        return ["the handler's first parameter must be the context (ctx)"]
    rest = params[1:]
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in rest):
        problems.append("handlers cannot take *args")
    accepts_any = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in rest)
    names = {
        p.name
        for p in rest
        if p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    properties = set((input_schema.get("properties") or {}).keys())
    required = set(input_schema.get("required") or [])
    for p in rest:
        if p.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
            continue
        if p.kind is inspect.Parameter.POSITIONAL_ONLY:
            problems.append(f"parameter {p.name!r} is positional-only")
            continue
        if p.default is inspect.Parameter.empty and p.name not in required:
            problems.append(
                f"parameter {p.name!r} has no default but the input does not require it"
            )
    if not accepts_any:
        for name in sorted(properties - names):
            problems.append(f"input {name!r} is declared but the handler does not accept it")
    return problems


def run_validate(job: dict[str, Any], proto: TextIO, src: Path) -> int:
    # Scan before importing anything: an undeclared import is reported as such, not as whatever
    # error importing it happens to raise.
    imports = scan(src)
    report: list[dict[str, Any]] = []
    for action in job.get("actions", []):
        entry: dict[str, Any] = {"id": action.get("id"), "handler": action.get("handler")}
        try:
            function = _resolve(str(action.get("handler", "")))
            entry["signature"] = str(inspect.signature(function))
            problems = check_signature(function, dict(action.get("input_schema") or {}))
            entry["ok"] = not problems
            if problems:
                entry["problems"] = problems
        except Exception as exc:
            entry["ok"] = False
            entry["problems"] = [f"{type(exc).__name__}: {exc}"[:500]]
        report.append(entry)
    _emit(proto, {"kind": "result", "output": {"actions": report, "imports": imports}})
    return 0


def run_tests(version_dir: Path, proto: TextIO) -> int:
    """Candidate-authored tests: useful signal for repair, never acceptance evidence."""
    tests = version_dir / "tests"
    if not tests.is_dir():
        _emit(proto, {"kind": "result", "output": {"present": False, "ran": 0, "ok": True}})
        return 0
    sys.path.insert(0, str(tests))
    stream = io.StringIO()
    suite = unittest.TestLoader().discover(str(tests), pattern="test*.py", top_level_dir=str(tests))
    result = unittest.TextTestRunner(stream=stream, verbosity=1).run(suite)
    _emit(
        proto,
        {
            "kind": "result",
            "output": {
                "present": True,
                "ran": result.testsRun,
                "ok": result.wasSuccessful(),
                "failures": [
                    {"test": str(test), "detail": text[-1200:]}
                    for test, text in (result.failures + result.errors)[:10]
                ],
                "skipped": len(result.skipped),
                "log_tail": stream.getvalue()[-3000:],
            },
        },
    )
    return 0


def run_invoke(job: dict[str, Any], proto: TextIO, replies: TextIO) -> int:
    channel = PipeChannel(replies, proto, str(job["token"]))
    info = RunInfo(
        run_id=str(job["run_id"]),
        app_id=job.get("app_id"),
        action_id=job.get("action_id"),
        origin=str(job.get("origin", "user")),
        timezone=str(job.get("timezone") or "UTC"),
    )
    context = Context(channel, info)
    payload = job.get("input")
    if not isinstance(payload, dict):
        _emit(
            proto, {"kind": "error", "code": "invalid_input", "message": "input must be an object"}
        )
        return 3
    try:
        function = _resolve(str(job["handler"]))
    except Exception as exc:
        _emit(
            proto,
            {
                "kind": "error",
                "code": "handler_unresolved",
                "message": f"{type(exc).__name__}: {exc}"[:500],
            },
        )
        return 3
    try:
        result = function(context, **payload)
    except OperationError as exc:
        _emit(
            proto,
            {
                "kind": "error",
                "code": "operation_failed",
                "operation_code": exc.code,
                "message": exc.message[:1000],
                "traceback": traceback.format_exc()[-2000:],
            },
        )
        return 4
    except Exception as exc:
        _emit(
            proto,
            {
                "kind": "error",
                "code": "handler_exception",
                "message": f"{type(exc).__name__}: {exc}"[:1000],
                "traceback": traceback.format_exc()[-2000:],
            },
        )
        return 4
    if result is None:
        result = {}
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError) as exc:
        _emit(proto, {"kind": "error", "code": "result_not_json", "message": str(exc)[:500]})
        return 4
    if not isinstance(result, dict):
        _emit(
            proto, {"kind": "error", "code": "result_not_object", "message": type(result).__name__}
        )
        return 4
    _emit(proto, {"kind": "result", "output": result})
    return 0


def main() -> int:
    sys.dont_write_bytecode = True
    replies = sys.stdin
    job_line = replies.readline()
    # Protocol stream = the original stdout. From here on fd 1 and sys.stdout point at stderr, so
    # prints (Python or C level) from generated code cannot masquerade as protocol messages.
    sys.stdout.flush()
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    sys.stdin = io.StringIO("")
    try:
        job = json.loads(job_line or "{}")
    except json.JSONDecodeError as exc:
        _emit(proto, {"kind": "error", "code": "bad_job", "message": str(exc)})
        return 2
    if job.get("protocol") != PROTOCOL_VERSION:
        _emit(
            proto,
            {"kind": "error", "code": "protocol_mismatch", "message": str(job.get("protocol"))},
        )
        return 2
    src = Path(str(job.get("version_dir", ""))) / "src"
    if not src.is_dir():
        _emit(
            proto, {"kind": "error", "code": "package_missing", "message": "sealed src/ not found"}
        )
        return 2
    sys.path.insert(0, str(src))
    mode = job.get("mode")
    if mode == "validate":
        return run_validate(job, proto, src)
    if mode == "tests":
        return run_tests(src.parent, proto)
    if mode == "invoke":
        return run_invoke(job, proto, replies)
    _emit(proto, {"kind": "error", "code": "bad_job", "message": f"unknown mode {mode!r}"})
    return 2
