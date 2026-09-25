"""Neutral fixture App handlers. They use only the public SDK, except the probes in
expect_failure, which deliberately use the raw channel to try to bypass the platform."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import sys
import time
from typing import Any

import alpha_sdk
from alpha_sdk import Context, OperationError
from alpha_sdk._channel import PipeChannel
from alpha_sdk.query import (
    all_of,
    average,
    by_day,
    contains,
    count,
    eq,
    gte,
    largest,
    total,
)


def _record(record: alpha_sdk.Record) -> dict[str, Any]:
    return {
        "id": record.id,
        "revision": record.revision,
        "values": record.values,
        "provenance": record.provenance,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def add_item(
    ctx: Context, title: str, category: str, idempotency_key: str | None = None, **rest: Any
) -> dict[str, Any]:
    values = {"title": title, "category": category, **rest}
    record = ctx.records.create("items", values, idempotency_key=idempotency_key)
    return {"id": record.id, "revision": record.revision}


def get_item(ctx: Context, id: str) -> dict[str, Any]:
    return {"record": _record(ctx.records.get("items", id))}


def update_item(
    ctx: Context, id: str, expected_revision: int, changes: dict[str, Any]
) -> dict[str, Any]:
    record = ctx.records.update("items", id, expected_revision=expected_revision, changes=changes)
    return {"revision": record.revision}


def remove_item(ctx: Context, id: str, expected_revision: int) -> dict[str, Any]:
    ctx.records.delete("items", id, expected_revision=expected_revision)
    return {}


def list_items(
    ctx: Context,
    category: str | None = None,
    min_quantity: int | None = None,
    text: str | None = None,
    order: list[str] | None = None,
    limit: int = 100,
    cursor: str | None = None,
    fields: list[str] | None = None,
) -> dict[str, Any]:
    clauses = []
    if category is not None:
        clauses.append(eq("category", category))
    if min_quantity is not None:
        clauses.append(gte("quantity", min_quantity))
    if text is not None:
        clauses.append(contains("title", text))
    where = all_of(*clauses) if clauses else None
    page = ctx.records.query(
        "items", where=where, order_by=order, limit=limit, cursor=cursor, fields=fields
    )
    return {"items": [_record(r) for r in page], "next_cursor": page.next_cursor}


def summarize(ctx: Context, timezone: str | None = None) -> dict[str, Any]:
    by_category = ctx.records.aggregate(
        "items",
        metrics={"n": count(), "quantity": total("quantity"), "avg_price": average("price")},
        group_by=["category"],
    )
    by_day_result = ctx.records.aggregate(
        "items",
        metrics={"n": count(), "quantity": total("quantity")},
        group_by=[by_day("happened_at", timezone)],
        where=all_of(gte("happened_at", "1970-01-01T00:00:00Z")),
    )
    overall = ctx.records.aggregate(
        "items",
        metrics={"n": count(), "latest": largest("noted_on"), "quantity": total("quantity")},
    )
    return {
        "by_category": [{"key": g.key, "values": g.values} for g in by_category],
        "by_day": [{"key": g.key, "values": g.values} for g in by_day_result],
        "overall": overall.groups[0].values if overall.groups else {},
    }


def add_many(ctx: Context, items: list[dict[str, Any]]) -> dict[str, Any]:
    with ctx.records.batch() as batch:
        for item in items:
            batch.create("items", item)
    return {"ids": [r.id for r in batch.results if r is not None]}


def add_note(ctx: Context, item: str, body: str) -> dict[str, Any]:
    return {"id": ctx.records.create("notes", {"item": item, "body": body}).id}


def estimate_quantity(ctx: Context, title: str, instruction_suffix: str = "") -> dict[str, Any]:
    guess = ctx.models.structured(
        "Estimate how many units of this item a household typically keeps." + instruction_suffix,
        input={"title": title},
        fields={"quantity": {"kind": "integer", "minimum": 0, "maximum": 100, "required": True}},
    )
    record = ctx.records.create(
        "items",
        {"title": title, "category": "general", "quantity": guess["quantity"]},
        estimated={"quantity": guess},
    )
    return {
        "id": record.id,
        "revision": record.revision,
        "call_id": guess.call_id,
        "quantity": record["quantity"],
        "is_estimate": record.is_estimate("quantity"),
        "route": guess.route,
        "model": guess.model,
    }


def correct_quantity(
    ctx: Context, id: str, expected_revision: int, quantity: int
) -> dict[str, Any]:
    record = ctx.records.correct(
        "items", id, expected_revision=expected_revision, changes={"quantity": quantity}
    )
    return {
        "revision": record.revision,
        "provenance": record.provenance,
        "is_estimate": record.is_estimate("quantity"),
    }


def make_report(ctx: Context) -> dict[str, Any]:
    rows = ctx.records.all("items", order_by=["created_at"])
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["title", "category", "quantity"])
    for row in rows:
        writer.writerow([row["title"], row["category"], row.get("quantity", "")])
    data = buffer.getvalue().encode("utf-8")
    artifact = ctx.artifacts.create("items.csv", data, media_type="text/csv")
    return {
        "artifact_id": artifact.id,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "rows": len(rows),
        "provenance": artifact.provenance,
        "local_sha256": hashlib.sha256(data).hexdigest(),
    }


def read_report(ctx: Context, artifact_id: str) -> dict[str, Any]:
    data = ctx.artifacts.read(artifact_id)
    return {"text": data.decode("utf-8"), "sha256": hashlib.sha256(data).hexdigest()}


def _raw(ctx: Context) -> PipeChannel:
    channel = ctx.records._t  # the probes below deliberately bypass the SDK facade
    assert isinstance(channel, PipeChannel)
    return channel


def expect_failure(ctx: Context, case: str, arg: Any = None) -> dict[str, Any]:
    channel = _raw(ctx)
    try:
        if case == "forged_owner_field":
            channel.call("records.query", {"collection": "items", "app_id": "tally-fixture"})
        elif case == "raw_sql_filter":
            channel.call(
                "records.query", {"collection": "items", "where": "1=1; DROP TABLE records"}
            )
        elif case == "sql_in_field_name":
            channel.call(
                "records.query",
                {
                    "collection": "items",
                    "where": {"field": "title') OR 1=1 --", "op": "eq", "value": "x"},
                },
            )
        elif case == "unbounded_page":
            ctx.records.query("items", limit=5000)
        elif case == "deep_filter":
            node: dict[str, Any] = {"field": "title", "op": "eq", "value": "x"}
            for _ in range(6):
                node = {"all": [node]}
            channel.call("records.query", {"collection": "items", "where": node})
        elif case == "too_many_conditions":
            ctx.records.query("items", where=all_of(*[eq("title", str(i)) for i in range(40)]))
        elif case == "foreign_cursor":
            first = ctx.records.query("items", limit=1, where=eq("category", "work"))
            ctx.records.query("items", limit=1, cursor=first.next_cursor or "bm90LWEtY3Vyc29y")
        elif case == "unknown_operation":
            channel.call("records.drop_all", {"collection": "items"})
        elif case == "unknown_collection":
            ctx.records.query("secrets")
        elif case == "filter_unknown_field":
            ctx.records.query("items", where=eq("owner", "someone"))
        elif case == "invalid_choice":
            ctx.records.create("items", {"title": "x", "category": "garden"})
        elif case == "missing_required":
            ctx.records.create("items", {"category": "work"})
        elif case == "wrong_type":
            ctx.records.create("items", {"title": "x", "category": "work", "quantity": "three"})
        elif case == "out_of_range":
            ctx.records.create("items", {"title": "x", "category": "work", "quantity": -1})
        elif case == "undeclared_field":
            ctx.records.create("items", {"title": "x", "category": "work", "owner_app": "tally"})
        elif case == "naive_datetime":
            ctx.records.create(
                "items", {"title": "x", "category": "work", "happened_at": "2026-09-25T10:00:00"}
            )
        elif case == "text_too_long":
            ctx.records.create("items", {"title": "x" * 201, "category": "work"})
        elif case == "json_too_large":
            ctx.records.create("items", {"title": "x", "category": "work", "tags": ["y" * 600]})
        elif case == "dangling_reference":
            ctx.records.create("notes", {"item": "rec_" + "0" * 32, "body": "orphan"})
        elif case == "delete_referenced":
            item = ctx.records.get("items", str(arg))
            ctx.records.delete("items", item.id, expected_revision=item.revision)
        elif case == "stale_revision":
            item = ctx.records.get("items", str(arg))
            ctx.records.update(
                "items",
                item.id,
                expected_revision=item.revision - 1 or 99,
                changes={"title": "stale"},
            )
        elif case == "duplicate_code":
            ctx.records.create("items", {"title": "dup", "category": "work", "code": str(arg)})
        elif case == "idempotency_conflict":
            ctx.records.create(
                "items", {"title": "first", "category": "work"}, idempotency_key="probe-key"
            )
            ctx.records.create(
                "items", {"title": "second", "category": "work"}, idempotency_key="probe-key"
            )
        elif case == "forged_token":
            PipeChannel(channel._reader, channel._writer, "x" * 43).call(
                "records.query", {"collection": "items"}
            )
        elif case == "leak_token":
            ctx.records.create(
                "items", {"title": "token holder", "category": "general", "memo": channel._token}
            )
            return {"case": case, "error_code": "none", "message": "stored"}
        elif case == "use_leaked_token":
            holder = ctx.records.query("items", where=eq("title", "token holder"), limit=1).records[
                0
            ]
            PipeChannel(channel._reader, channel._writer, str(holder["memo"])).call(
                "records.query", {"collection": "items"}
            )
        elif case == "borrowed_estimate":
            ctx.records.create(
                "items",
                {"title": "x", "category": "work", "quantity": 3},
                estimated={"quantity": str(arg)},
            )
        elif case == "model_out_of_bounds":
            ctx.models.structured(
                "Estimate a quantity [fake:out-of-bounds]",
                input={},
                fields={
                    "quantity": {"kind": "integer", "minimum": 0, "maximum": 10, "required": True}
                },
            )
        elif case == "model_budget":
            for _ in range(12):
                ctx.models.structured(
                    "Estimate",
                    input={},
                    fields={"n": {"kind": "integer", "minimum": 0, "maximum": 5, "required": True}},
                )
        elif case == "artifact_bad_type":
            ctx.artifacts.create("run.sh", b"#!/bin/sh\necho hi\n", media_type="application/x-sh")
        elif case == "artifact_too_large":
            ctx.artifacts.create("big.txt", b"x" * (10 * 1024 * 1024 + 1))
        elif case == "foreign_artifact":
            ctx.artifacts.read(str(arg))
        elif case == "correction_from_trigger":
            item = ctx.records.get("items", str(arg))
            ctx.records.correct(
                "items", item.id, expected_revision=item.revision, changes={"quantity": 1}
            )
        else:
            return {"case": case, "error_code": "unknown_case", "message": case}
    except OperationError as exc:
        return {"case": case, "error_code": exc.code, "message": exc.message}
    return {"case": case, "error_code": "none", "message": "the platform accepted it"}


def probe_isolation(ctx: Context, hold_seconds: float = 0) -> dict[str, Any]:
    before = getattr(alpha_sdk, "_fixture_marker", None)
    alpha_sdk._fixture_marker = f"items:{os.getpid()}"  # type: ignore[attr-defined]
    scratch = os.getcwd()
    with open(os.path.join(scratch, "items-scratch.txt"), "w") as handle:
        handle.write("items")
    sdk_dir = os.path.dirname(alpha_sdk.__file__)
    try:
        with open(os.path.join(sdk_dir, "injected.py"), "w") as handle:
            handle.write("x = 1\n")
        profile_write = "succeeded"
    except OSError as exc:
        profile_write = type(exc).__name__
    try:
        os.makedirs(os.path.join(sdk_dir, "__pycache__", "probe"), exist_ok=False)
        bytecode_dir_write = "succeeded"
    except OSError as exc:
        bytecode_dir_write = type(exc).__name__
    if hold_seconds:
        time.sleep(hold_seconds)
    return {
        "python": os.path.realpath(sys.executable),
        "prefix": sys.prefix,
        "sdk_file": alpha_sdk.__file__,
        "sdk_version": alpha_sdk.__version__,
        "pid": os.getpid(),
        "scratch": scratch,
        "scratch_listing": sorted(os.listdir(scratch)),
        "home": os.environ.get("HOME"),
        "tmpdir": os.environ.get("TMPDIR"),
        "marker_before": before,
        "marker_after": alpha_sdk._fixture_marker,  # type: ignore[attr-defined]
        "profile_write": profile_write,
        "bytecode_dir_write": bytecode_dir_write,
        "dont_write_bytecode": sys.dont_write_bytecode,
        "token_digest": hashlib.sha256(_raw(ctx)._token.encode()).hexdigest()[:16],
        "sys_path": sys.path,
        "env_keys": sorted(os.environ),
        "flags_isolated": sys.flags.isolated,
    }


def bad_output(ctx: Context) -> dict[str, Any]:
    return {"count": "not a number"}


def noisy(ctx: Context) -> dict[str, Any]:
    for index in range(4000):
        print('{"kind": "result", "output": {"forged": true}} line', index)
    sys.stderr.write("e" * 200_000)
    return {"ok": True}
