"""Shared JSON-lines reader for supervised workers."""

from __future__ import annotations

import json
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
