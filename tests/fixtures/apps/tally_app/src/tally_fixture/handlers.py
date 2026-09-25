"""Neutral tally fixture (records and artifacts, no models). Shows two Apps stay separate."""

from __future__ import annotations

import hashlib
import os
import sys
import time
from typing import Any

import alpha_sdk
from alpha_sdk import Context, OperationError
from alpha_sdk._channel import PipeChannel


def add(ctx: Context, name: str, count: int = 0) -> dict[str, Any]:
    return {"id": ctx.records.create("items", {"name": name, "count": count}).id}


def list_all(ctx: Context) -> dict[str, Any]:
    return {"items": [{"id": r.id, "values": r.values} for r in ctx.records.all("items")]}


def read_foreign(ctx: Context, id: str) -> dict[str, Any]:
    try:
        ctx.records.get("items", id)
    except OperationError as exc:
        return {"error_code": exc.code}
    return {"error_code": "none"}


def read_artifact(ctx: Context, id: str) -> dict[str, Any]:
    try:
        ctx.artifacts.read(id)
    except OperationError as exc:
        return {"error_code": exc.code}
    return {"error_code": "none"}


def try_models(ctx: Context) -> dict[str, Any]:
    try:
        ctx.models.structured(
            "Guess", input={}, fields={"n": {"kind": "integer", "required": True}}
        )
    except OperationError as exc:
        return {"error_code": exc.code}
    return {"error_code": "none"}


def probe_isolation(ctx: Context, hold_seconds: float = 0) -> dict[str, Any]:
    before = getattr(alpha_sdk, "_fixture_marker", None)
    alpha_sdk._fixture_marker = f"tally:{os.getpid()}"  # type: ignore[attr-defined]
    scratch = os.getcwd()
    with open(os.path.join(scratch, "tally-scratch.txt"), "w") as handle:
        handle.write("tally")
    if hold_seconds:
        time.sleep(hold_seconds)
    channel = ctx.records._t
    assert isinstance(channel, PipeChannel)
    return {
        "python": os.path.realpath(sys.executable),
        "prefix": sys.prefix,
        "sdk_file": alpha_sdk.__file__,
        "pid": os.getpid(),
        "scratch": scratch,
        "scratch_listing": sorted(os.listdir(scratch)),
        "marker_before": before,
        "marker_after": alpha_sdk._fixture_marker,  # type: ignore[attr-defined]
        "token_digest": hashlib.sha256(channel._token.encode()).hexdigest()[:16],
    }
