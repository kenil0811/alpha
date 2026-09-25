"""SDK facade behaviour against an in-memory transport (no platform needed)."""

from __future__ import annotations

import io
import json
from typing import Any

import pytest
from alpha_sdk import Conflict, Context, NotFound, OperationError, RunInfo
from alpha_sdk._channel import PipeChannel
from alpha_sdk.models import ModelResult
from alpha_sdk.query import all_of, by_day, contains, count, eq, gte, not_, one_of, total

NOW = "2026-09-25T10:00:00.000000Z"


def wire_record(**values: Any) -> dict[str, Any]:
    return {
        "id": "rec_" + "1" * 32,
        "collection": "items",
        "revision": 1,
        "values": values,
        "provenance": {},
        "created_at": NOW,
        "updated_at": NOW,
    }


class FakeTransport:
    def __init__(self, replies: list[Any]) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.replies = replies

    def call(self, operation: str, args: dict[str, Any]) -> Any:
        self.calls.append((operation, args))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def progress(self, message: str, data: dict[str, Any] | None = None) -> None:
        self.calls.append(("progress", {"message": message, **(data or {})}))


def context(replies: list[Any]) -> tuple[Context, FakeTransport]:
    transport = FakeTransport(replies)
    return Context(transport, RunInfo("run_1", "app", "act", "user", "Asia/Kolkata")), transport


def test_query_builders_produce_the_typed_filter_ast() -> None:
    ctx, transport = context([{"records": [wire_record(title="x")], "next_cursor": "abc"}])
    page = ctx.records.query(
        "items",
        where=all_of(eq("category", "work"), gte("quantity", 2), not_(contains("title", "old")))
        | one_of("code", ["A", "B"]),
        order_by=["-noted_on", "title"],
        limit=5,
    )
    op, args = transport.calls[0]
    assert op == "records.query"
    assert args["where"]["any"][0]["all"][2] == {
        "not": {"field": "title", "op": "contains", "value": "old"}
    }
    assert args["order_by"] == [
        {"field": "noted_on", "direction": "desc"},
        {"field": "title", "direction": "asc"},
    ]
    assert page.next_cursor == "abc" and page.records[0]["title"] == "x"


def test_plain_mapping_where_means_equality() -> None:
    ctx, transport = context([{"records": []}])
    ctx.records.query("items", where={"category": "work", "done": False})
    assert transport.calls[0][1]["where"] == {
        "all": [
            {"field": "category", "op": "eq", "value": "work"},
            {"field": "done", "op": "eq", "value": False},
        ]
    }


def test_aggregate_arguments() -> None:
    ctx, transport = context([{"groups": [{"key": {"d": "2026-09-25"}, "values": {"n": 2}}]}])
    result = ctx.records.aggregate(
        "items", metrics={"n": count(), "q": total("quantity")}, group_by=["category", by_day("at")]
    )
    args = transport.calls[0][1]
    assert args["metrics"] == [
        {"name": "n", "fn": "count"},
        {"name": "q", "fn": "sum", "field": "quantity"},
    ]
    assert args["group_by"] == [{"field": "category"}, {"field": "at", "bucket": "day"}]
    assert result.groups[0].values == {"n": 2}


def test_batch_commits_once_and_sends_nothing_on_error() -> None:
    ctx, transport = context([{"results": [wire_record(title="a"), None]}])
    with ctx.records.batch() as batch:
        batch.create("items", {"title": "a"})
        batch.delete("items", "rec_x", expected_revision=1)
    assert [c[0] for c in transport.calls] == ["records.batch"]
    assert batch.results[0] is not None and batch.results[1] is None
    ctx2, transport2 = context([])
    with pytest.raises(RuntimeError), ctx2.records.batch() as batch2:
        batch2.create("items", {"title": "a"})
        raise RuntimeError("handler failed")
    assert transport2.calls == []


def test_estimates_are_cited_by_call_id() -> None:
    result = ModelResult(
        "mcall_1", {"q": 3}, "fake", "none", created_at=__import__("datetime").datetime.now()
    )
    ctx, transport = context([wire_record(q=3)])
    ctx.records.create("items", {"q": result["q"]}, estimated={"q": result})
    assert transport.calls[0][1]["estimated"] == {"q": "mcall_1"}
    with pytest.raises(TypeError):
        ctx.records.create("items", {"q": 3}, estimated={"q": 3})  # type: ignore[dict-item]


def test_pipe_channel_maps_failures_to_typed_errors() -> None:
    replies = io.StringIO(
        "\n".join(
            [
                json.dumps(
                    {
                        "kind": "reply",
                        "call_id": "c1",
                        "status": "failed",
                        "error": {"code": "conflict", "message": "stale"},
                    }
                ),
                json.dumps(
                    {
                        "kind": "reply",
                        "call_id": "c2",
                        "status": "failed",
                        "error": {"code": "not_found", "message": "gone"},
                    }
                ),
                json.dumps(
                    {
                        "kind": "reply",
                        "call_id": "c3",
                        "status": "failed",
                        "error": {"code": "timed_out", "message": "slow"},
                    }
                ),
                json.dumps({"kind": "reply", "call_id": "WRONG", "status": "completed"}),
            ]
        )
        + "\n"
    )
    out = io.StringIO()
    channel = PipeChannel(replies, out, "t" * 43)
    with pytest.raises(Conflict):
        channel.call("records.update", {})
    with pytest.raises(NotFound):
        channel.call("records.get", {})
    with pytest.raises(OperationError) as excinfo:
        channel.call("models.structured", {})
    assert excinfo.value.code == "timed_out"
    with pytest.raises(OperationError, match="did not match"):
        channel.call("records.get", {})
    sent = [json.loads(line) for line in out.getvalue().splitlines()]
    assert all(m["token"] == "t" * 43 and m["kind"] == "call" for m in sent)
