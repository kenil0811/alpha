"""Shared pipe handling for supervised workers: the JSON-lines stdout reader and the stderr
drain every worker launch needs."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

from alpha.execution.supervisor import WorkerHandle


def read_worker_messages(
    handle: WorkerHandle,
    on_message: Callable[[dict[str, Any]], None],
    on_raw: Callable[[str], None],
) -> None:
    """Read stdout until EOF; every JSON object goes to on_message, anything else to on_raw."""
    for raw in handle.stdout:
        line = raw.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            on_raw(line[:500])
            continue
        if isinstance(message, dict):
            on_message(message)
        else:
            on_raw(line[:500])


class StderrTail:
    """Drains a worker's stderr from the moment it starts and keeps the last `limit` characters.

    A worker that writes more than the pipe buffer (64 KiB on macOS) to stderr blocks until
    someone reads it. Reading only after exit would stall such a worker until its deadline and
    report a timeout instead of the real failure.
    """

    def __init__(self, handle: WorkerHandle, limit: int = 2000) -> None:
        self._stream = handle.process.stderr
        self._limit = limit
        self._tail = ""
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._drain, daemon=True)
        self._thread.start()

    def _drain(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            for chunk in iter(lambda: stream.read(4096), ""):
                with self._lock:
                    self._tail = (self._tail + chunk)[-self._limit :]
        except (OSError, ValueError):
            pass

    def text(self, wait_seconds: float = 2.0) -> str:
        """The captured tail; waits briefly for the pipe to reach EOF after the worker exits."""
        self._thread.join(timeout=wait_seconds)
        with self._lock:
            return self._tail
