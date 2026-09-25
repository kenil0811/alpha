"""The worker's only path to platform capabilities: JSON lines over its supervised pipes.

A call is written to the protocol stream (the worker's original stdout) and the reply is read
from stdin. The per-run token issued by Core accompanies every call. Handlers never see this
module; they use the Context facade.
"""

from __future__ import annotations

import itertools
import json
import threading
from typing import Any, Protocol, TextIO

from alpha_sdk.errors import Unavailable, from_reply

# Must equal alpha_contracts.broker.WORKER_PROTOCOL_VERSION. The SDK is standard library only,
# so it keeps a copy; tests/test_contract_sync.py holds the two equal.
PROTOCOL_VERSION = 1


class Transport(Protocol):
    def call(self, operation: str, args: dict[str, Any]) -> Any: ...

    def progress(self, message: str, data: dict[str, Any] | None = None) -> None: ...


class PipeChannel:
    def __init__(self, reader: TextIO, writer: TextIO, token: str) -> None:
        self._reader = reader
        self._writer = writer
        self._token = token
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    def _send(self, message: dict[str, Any]) -> None:
        self._writer.write(json.dumps(message, allow_nan=False) + "\n")
        self._writer.flush()

    def call(self, operation: str, args: dict[str, Any]) -> Any:
        with self._lock:
            call_id = f"c{next(self._ids)}"
            self._send(
                {
                    "kind": "call",
                    "call_id": call_id,
                    "token": self._token,
                    "operation": operation,
                    "version": PROTOCOL_VERSION,
                    "args": args,
                }
            )
            line = self._reader.readline()
            if not line:
                raise Unavailable("the platform channel closed")
            try:
                reply = json.loads(line)
            except json.JSONDecodeError as exc:
                raise Unavailable(f"unreadable platform reply: {exc}") from exc
            if not isinstance(reply, dict) or reply.get("call_id") != call_id:
                raise Unavailable("platform reply did not match the call")
            if reply.get("status") == "completed":
                return reply.get("result")
            error = reply.get("error")
            raise from_reply(error if isinstance(error, dict) else None)

    def progress(self, message: str, data: dict[str, Any] | None = None) -> None:
        with self._lock:
            self._send({"kind": "progress", "message": message[:500], "data": data or {}})
