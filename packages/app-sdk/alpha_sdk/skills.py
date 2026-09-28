"""ctx.skills: the abilities Alpha keeps outside any module (the `skills` capability).

    for skill in ctx.skills.list():            # [{id, title, description, inputs, produces}]
        ...
    result = ctx.skills.run("find_people_to_cold_call", {"industry": "logistics"})
    result["summary"]                          # plain words on what it found
    result["items"]                            # rows it produced (small dicts), grounded in sources

A skill is how the person taught Alpha to do one kind of job (often by searching and reading
the web). A run is bounded (a couple of minutes at most) and returns what was found so far when
it stops early; `state` is "done" or "failed". Save items through your own records if the
person wants them kept. Only procedure skills run from a module; a skill that names a module
action is that action.
"""

from __future__ import annotations

from typing import Any

from alpha_sdk._channel import Transport


class Skills:
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    def list(self) -> list[dict[str, Any]]:
        data = self._t.call("skills.list", {})
        return [
            {k: s.get(k) for k in ("id", "title", "description", "inputs", "produces")}
            for s in (data or {}).get("skills", [])
        ]

    def run(self, skill: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._t.call("skills.run", {"skill": skill, "inputs": inputs or {}})
        return dict(data or {})
