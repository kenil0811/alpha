"""ctx.models: bounded structured model calls routed through the platform's model gateway.

You describe the output with record field specs (kind, range, choices). The platform chooses the
route, enforces the App's budget, checks every returned value against your specs and labels the
result an estimate. Store it with `estimated=` so people see it as an estimate and can correct it.

    guess = ctx.models.structured(
        "Estimate the quantity implied by this description.",
        input={"description": text},
        fields={"quantity": {"kind": "integer", "minimum": 0, "maximum": 1000, "required": True}},
    )
    ctx.records.create("items", {"title": text, "quantity": guess["quantity"]},
                       estimated={"quantity": guess})
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from alpha_sdk._channel import Transport


@dataclass(frozen=True)
class ModelResult:
    call_id: str
    output: dict[str, Any]
    route: str
    model: str
    created_at: datetime
    label: str = "estimate"

    def __getitem__(self, name: str) -> Any:
        return self.output[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self.output.get(name, default)


class Models:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def structured(
        self,
        instruction: str,
        *,
        input: Mapping[str, Any] | None = None,
        fields: Mapping[str, Mapping[str, Any]],
    ) -> ModelResult:
        specs = [{"name": name, **dict(spec)} for name, spec in fields.items()]
        data = self._t.call(
            "models.structured",
            {"instruction": instruction, "input": dict(input or {}), "fields": specs},
        )
        return ModelResult(
            call_id=str(data["call_id"]),
            output=dict(data["output"]),
            route=str(data["route"]),
            model=str(data["model"]),
            created_at=datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00")),
            label=str(data.get("label", "estimate")),
        )
