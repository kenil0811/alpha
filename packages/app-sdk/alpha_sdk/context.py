"""The Context every action handler receives as its first argument.

    def add_item(ctx: Context, title: str, quantity: int = 1) -> dict:
        record = ctx.records.create("items", {"title": title, "quantity": quantity})
        return {"id": record.id}

Handlers return a JSON object matching the action's output schema. They have no database path,
no credentials and no network access to the platform; everything goes through ctx.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from alpha_sdk._channel import Transport
from alpha_sdk.artifacts import Artifacts
from alpha_sdk.models import Models
from alpha_sdk.records import Records


@dataclass(frozen=True)
class RunInfo:
    run_id: str
    app_id: str | None
    action_id: str | None
    origin: str
    timezone: str


class Context:
    def __init__(self, transport: Transport, info: RunInfo) -> None:
        self._t = transport
        self.info = info
        self.records = Records(transport)
        self.artifacts = Artifacts(transport)
        self.models = Models(transport)

    @property
    def run_id(self) -> str:
        return self.info.run_id

    @property
    def timezone(self) -> str:
        return self.info.timezone

    def now(self) -> datetime:
        """The current time as an aware UTC datetime."""
        return datetime.now(tz=UTC)

    def local_now(self) -> datetime:
        return self.now().astimezone(ZoneInfo(self.info.timezone))

    def today(self) -> date:
        """Today's date in the person's timezone."""
        return self.local_now().date()

    def log(self, message: str, **data: Any) -> None:
        """Record a progress note on the run's activity (not shown as a result)."""
        self._t.progress(message, data)
