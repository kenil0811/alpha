# ruff: noqa: E501
"""The first conversation: five short questions, then a proposed first shape.

Alpha asks what the person does, what fills their week, what they are trying to get better at,
where their work lives and where they would like to begin. The answers become accepted profile
facts (they said so), and one model call proposes two or three modules to start with, each a
sentence the person can send as-is. Nothing is built until they pick one.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from alpha.capabilities.errors import invalid
from alpha.context.profile import ProfileService
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, utc_now

log = logging.getLogger("alpha.onboarding")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profile_meta (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

QUESTIONS: tuple[dict[str, str], ...] = (
    {
        "id": "occupation",
        "label": "What do you do?",
        "hint": "Work, study, a hobby or two.",
    },
    {
        "id": "week",
        "label": "What fills your week?",
        "hint": "Where most of your week goes.",
    },
    {
        "id": "goal",
        "label": "What are you trying to get better at right now?",
        "hint": "A job hunt, a habit, a course.",
    },
    {
        "id": "tools",
        "label": "Where does your work live?",
        "hint": "Email, Notion, spreadsheets…",
    },
    {
        "id": "begin",
        "label": "Where would you like Alpha to begin?",
        "hint": "Anything. Alpha suggests a start.",
    },
)
FACT_FIELDS = {
    "occupation": "occupation",
    "week": "week_focus",
    "goal": "current_goal",
    "tools": "work_tools",
    "begin": "wants_to_begin_with",
}

ONBOARD_SYSTEM = """A person just told Alpha, in five short answers, what they do, what fills their week, what they want to get better at, where their work lives, and where they would like to begin. Alpha builds small personal modules on their Mac: trackers, lists, watchers of web pages, summaries, things that run on a schedule.

Propose two or three modules to start with, in the order they should be made. Each: a short title, one sentence the person could send as a request ("Keep a list of the courses I am taking with assignments and due dates"), and one line on why it fits what they said. Prefer what serves their stated goal; the first one should be usable the same day. When the person already has modules (listed), propose what adds to them, not the same again. intro is at most 50 words, warm, specific, no technical words. Output only the structured object."""


def onboard_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["intro", "options"],
        "properties": {
            "intro": {"type": "string", "maxLength": 400},
            "options": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "required": ["title", "request", "why"],
                    "properties": {
                        "title": {"type": "string", "maxLength": 80},
                        "request": {"type": "string", "maxLength": 300},
                        "why": {"type": "string", "maxLength": 200},
                    },
                },
            },
        },
    }


def fake_onboard(prompt: str) -> dict[str, Any]:
    return {
        "intro": "From what you said, I'd start here.",
        "options": [
            {
                "title": "Coursework",
                "request": "Keep a list of my courses with assignments and due dates",
                "why": "It is what fills your week.",
            },
            {
                "title": "Job applications",
                "request": "Keep a list of job openings I find and what I did about each",
                "why": "It is the goal you named.",
            },
        ],
    }


class OnboardingService:
    def __init__(
        self,
        store: ControlStore,
        profile: ProfileService,
        gateway: Any,
        inference: StructuredInference,
        *,
        default_route: str,
        context: Callable[[str], str] | None = None,
    ) -> None:
        self._store = store
        self._profile = profile
        self._gateway = gateway
        self._inference = inference
        self._default_route = default_route
        self._context = context
        store.execute_script(_SCHEMA)

    def status(self) -> dict[str, Any]:
        rows = self._store.query("SELECT value_json FROM profile_meta WHERE key = 'onboarding'")
        done = json.loads(rows[0]["value_json"]) if rows else None
        return {"done": done is not None, "questions": list(QUESTIONS), "proposal": done}

    def skip(self) -> dict[str, Any]:
        self._remember({"skipped": True, "intro": "", "options": []})
        return self.status()

    def answer(self, answers: dict[str, str]) -> dict[str, Any]:
        """Record the answers as facts and propose a first shape."""
        clean = {
            k: str(v).strip() for k, v in answers.items() if k in FACT_FIELDS and str(v).strip()
        }
        if not clean:
            raise invalid("answer at least one question")
        for key, value in clean.items():
            self._profile.claim(
                FACT_FIELDS[key], value[:1000], provenance="person", source="person", accepted=True
            )
        route = self._gateway.route(self._default_route, stage="assistant")
        lines = [f"- {q['label']} {clean[q['id']]}" for q in QUESTIONS if q["id"] in clean]
        prompt = "THE PERSON'S ANSWERS:\n" + "\n".join(lines)
        if self._context is not None:
            try:
                prompt += "\n\nWHAT ALPHA ALREADY KNOWS:\n" + self._context(
                    " ".join(clean.values())
                )
            except Exception:
                log.exception("context pack failed during onboarding")
        proposal: dict[str, Any]
        try:
            result = self._inference.call(
                route,
                system=ONBOARD_SYSTEM,
                prompt=prompt,
                schema=onboard_schema(),
                scope_kind="onboarding",
                scope_ref="onboarding",
                fake=fake_onboard if route.route_id == "fake" else None,
            )
            proposal = result.output if isinstance(result.output, dict) else {}
        except InferenceError as exc:
            log.warning("onboarding proposal failed: %s", exc)
            proposal = {
                "intro": "Thanks. Describe anything you want to keep track of and Alpha builds it.",
                "options": [],
            }
        self._remember(proposal)
        return self.status()

    def _remember(self, proposal: dict[str, Any]) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                "INSERT INTO profile_meta(key, value_json, updated_at) VALUES ('onboarding', ?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json, updated_at = excluded.updated_at",
                (json.dumps(proposal), utc_now().isoformat().replace("+00:00", "Z")),
            )
