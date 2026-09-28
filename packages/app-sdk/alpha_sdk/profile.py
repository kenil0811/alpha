"""ctx.profile: what Alpha knows about the person, shared across their modules (the `profile`
capability).

    ctx.profile.get("target_roles")          # the accepted value, or None
    ctx.profile.all()                        # {field: value} for every accepted fact
    ctx.profile.set("degree", "MSc Computer Science")      # what the person typed into this App
    ctx.profile.suggest("skills", ["Python", "SQL"], why="from the modules in Academics")

`set` records what the person told this App as an accepted fact (they typed it; the App is
passing it on). `suggest` is for what the App worked out: it waits on the person's own page
until they accept it, and reads return nothing for it before then. Field names are plain
snake_case (degree, university, skills, target_roles, location, dietary_goal); reuse a name
another module would choose so facts meet instead of duplicating.
"""

from __future__ import annotations

from typing import Any

from alpha_sdk._channel import Transport


class Profile:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def get(self, field: str) -> Any:
        data = self._t.call("profile.get", {"field": field})
        return None if data is None else data.get("value")

    def all(self) -> dict[str, Any]:
        data = self._t.call("profile.all", {})
        return {str(f["field"]): f["value"] for f in (data or {}).get("facts", [])}

    def set(self, field: str, value: Any, *, why: str | None = None) -> None:
        self._t.call("profile.set", {"field": field, "value": value, "why": why, "confidence": 1.0})

    def suggest(
        self, field: str, value: Any, *, why: str | None = None, confidence: float = 0.8
    ) -> None:
        self._t.call(
            "profile.suggest",
            {"field": field, "value": value, "why": why, "confidence": confidence},
        )
