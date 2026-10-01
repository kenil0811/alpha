# ruff: noqa: E501
"""The weekly look across modules: what Alpha noticed, as suggestions only.

Once a week (and when the person asks), Alpha reads the context pack it already assembles for
every turn and writes at most three plain observations with a next step each: a tracker that
has stayed empty, a source not read for a while, a module that could feed another, a goal with
nothing behind it. Nothing is changed; each nudge is a sentence the person can send to the
assistant or dismiss.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, new_id, utc_now

log = logging.getLogger("alpha.review")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS nudges (
    nudge_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    next_step TEXT NOT NULL,
    module TEXT,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS review_runs (
    run_id TEXT PRIMARY KEY,
    ran_at TEXT NOT NULL,
    nudges INTEGER NOT NULL
);
"""

REVIEW_SYSTEM = """You look over what a person keeps in Alpha once a week and notice at most three things worth a nudge: a table that has stayed empty since it was made, a source that has not been read for days, two projects that would help each other if connected, a goal on the profile with no project behind it, a routine that never runs. Only what the facts show; never invent. Each nudge: one plain sentence of what you noticed (at most 30 words) and one next step the person could send Alpha as a request (at most 20 words). If nothing stands out, return no nudges. No technical words. Output only the structured object."""

EVERY = timedelta(days=7)


def review_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["nudges"],
        "properties": {
            "nudges": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "required": ["text", "next_step"],
                    "properties": {
                        "text": {"type": "string", "maxLength": 240},
                        "next_step": {"type": "string", "maxLength": 160},
                        "module": {"type": ["string", "null"]},
                    },
                },
            }
        },
    }


def fake_review(prompt: str) -> dict[str, Any]:
    if "Keeps: notes (0)" in prompt:
        return {
            "nudges": [
                {
                    "text": "Your notes list has stayed empty since it was made.",
                    "next_step": "Add my first three notes",
                    "module": None,
                }
            ]
        }
    return {"nudges": []}


class ReviewService:
    def __init__(
        self,
        store: ControlStore,
        gateway: Any,
        inference: StructuredInference,
        *,
        default_route: str,
        context: Callable[[str], str],
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._inference = inference
        self._default_route = default_route
        self._context = context
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)

    def nudges(self) -> list[dict[str, Any]]:
        rows = self._store.query(
            "SELECT * FROM nudges WHERE state = 'open' ORDER BY created_at DESC LIMIT 6"
        )
        return [dict(r) for r in rows]

    def dismiss(self, nudge_id: str) -> None:
        with self._store.transaction() as conn:
            conn.execute("UPDATE nudges SET state = 'dismissed' WHERE nudge_id = ?", (nudge_id,))

    def last_run(self) -> datetime | None:
        rows = self._store.query("SELECT ran_at FROM review_runs ORDER BY ran_at DESC LIMIT 1")
        return datetime.fromisoformat(rows[0]["ran_at"].replace("Z", "+00:00")) if rows else None

    def due(self) -> bool:
        last = self.last_run()
        return last is None or datetime.now(UTC) - last >= EVERY

    def start_if_due(self) -> None:
        if self.due():
            threading.Thread(target=self._run_quietly, name="weekly-review", daemon=True).start()

    def _run_quietly(self) -> None:
        try:
            self.run()
        except Exception:
            log.exception("the weekly review failed")

    def run(self) -> list[dict[str, Any]]:
        """Look now. Open nudges from the last look are replaced by this one's."""
        with self._lock:
            route = self._gateway.route(self._default_route, stage="assistant")
            pack = self._context("weekly review of everything")
            if "THEIR PROJECTS" not in pack:
                self._record(0)
                return []
            try:
                result = self._inference.call(
                    route,
                    system=REVIEW_SYSTEM,
                    prompt=pack,
                    schema=review_schema(),
                    scope_kind="weekly_review",
                    scope_ref="review",
                    fake=fake_review if route.route_id == "fake" else None,
                )
            except InferenceError as exc:
                log.warning("weekly review failed: %s", exc)
                return self.nudges()
            output = result.output if isinstance(result.output, dict) else {}
            found = [n for n in output.get("nudges", []) if isinstance(n, dict) and n.get("text")][
                :3
            ]
            now = utc_now().isoformat().replace("+00:00", "Z")
            with self._store.transaction() as conn:
                conn.execute("UPDATE nudges SET state = 'superseded' WHERE state = 'open'")
                for nudge in found:
                    conn.execute(
                        "INSERT INTO nudges(nudge_id, text, next_step, module, state, created_at)"
                        " VALUES (?,?,?,?, 'open', ?)",
                        (
                            new_id("nudge"),
                            str(nudge["text"])[:240],
                            str(nudge.get("next_step") or "")[:160],
                            nudge.get("module"),
                            now,
                        ),
                    )
            self._record(len(found))
            return self.nudges()

    def _record(self, count: int) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                "INSERT INTO review_runs(run_id, ran_at, nudges) VALUES (?,?,?)",
                (new_id("review"), utc_now().isoformat().replace("+00:00", "Z"), count),
            )
