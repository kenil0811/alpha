"""AssistantService: conversation → interpretation, material questions, versioned SolutionBrief.

Each user turn runs one structured model call (in a thread; the conversation is `thinking`
meanwhile). The model proposes delivery, interpretation, questions and a brief draft; Core owns
the brief's identity, revision lineage and assumption provenance. An `answer` delivery creates
no brief and no App/Task record. Nothing here grants authority.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from alpha_contracts.briefs import Assumption, Delivery, Interpretation, OpenQuestion, SolutionBrief
from pydantic import BaseModel, ValidationError

from alpha.assistant.fake_model import fake_assistant
from alpha.assistant.prompts import (
    TRIAGE_SYSTEM,
    fake_triage,
    system_prompt,
    triage_prompt,
    triage_schema,
    turn_prompt,
)
from alpha.assistant.research import (
    PROPOSE_SYSTEM,
    Evidence,
    Researcher,
    fake_propose,
    fake_research,
    propose_prompt,
    propose_schema,
)
from alpha.assistant.turn import AssistantTurnOutput, turn_output_schema
from alpha.models.disclosure import data_notice, ground_output, is_remote
from alpha.models.gateway import ModelGateway, ModelRoute
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, NotFoundError, new_id, utc_now

log = logging.getLogger("alpha.assistant")

# What a person reads when a turn fails; the technical cause stays in the log.
_PLAIN_FAILURE = {
    "timeout": "the model service took too long to answer",
    "cli_missing": "Alpha could not reach its model service",
    "cli_not_logged_in": "Alpha's model service is not signed in",
    "cli_error": "the model service returned an error",
    "cli_bad_json": "the model service's answer could not be read",
    "route_unavailable": "no model service is available for this request",
}
RESTARTED = "Alpha was closed or restarted while it was thinking about this"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    route_id TEXT NOT NULL,
    delivery TEXT,
    current_brief_id TEXT,
    current_revision INTEGER,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    latest_sequence INTEGER NOT NULL DEFAULT 0,
    change_of TEXT,
    quick_change INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS conversation_turns (
    turn_id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(conversation_id, sequence)
);
CREATE TABLE IF NOT EXISTS briefs (
    brief_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id),
    source_turn_id TEXT NOT NULL,
    brief_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (brief_id, revision)
);
"""


def _dt(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


class ConversationTurn(BaseModel):
    turn_id: str
    sequence: int
    role: str
    kind: str
    content: dict[str, Any]
    created_at: str


class ConversationRecord(BaseModel):
    conversation_id: str
    # Where this conversation's data goes, from the configured routes (never from the model).
    data_notice: str | None = None
    state: str
    route_id: str
    created_at: str
    updated_at: str
    turns: list[ConversationTurn]
    current_brief: SolutionBrief | None
    interpretation: Interpretation | None
    questions: list[OpenQuestion]
    reply: str | None
    delivery: Delivery | None
    error: str | None
    brief_history: list[int]
    # The App this conversation changes (rebuilt in place, data kept); None for a new one.
    change_of: str | None = None
    # After Alpha looked around: the shaped options for the person to choose from (state
    # `proposed`), with the evidence they rest on.
    proposal: dict[str, Any] | None = None
    # True when the change is small enough for Alpha to edit the App's files directly (no
    # brief, no plan): the creation starts on its own and the panel follows it.
    quick_change: bool = False
    # The session this conversation was started from (a card in that session), if any.
    session_id: str | None = None


class AssistantService:
    def __init__(
        self,
        store: ControlStore,
        gateway: ModelGateway,
        inference: StructuredInference,
        *,
        default_route: str,
        app_model_route: str | None = None,
        describe_app: Callable[[str], str | None] | None = None,
        context: Callable[[str], str] | None = None,
        researcher: Researcher | None = None,
    ) -> None:
        # What Alpha knows about the person and their modules, assembled for one sentence.
        self._context = context
        # Looks around the web before a new module is proposed (None: propose without it).
        self._researcher = researcher
        self._store = store
        self._gateway = gateway
        self._inference = inference
        self._default_route = default_route
        self._app_model_route = app_model_route
        # A plain summary of an installed App by id (None when there is no such App), so a
        # conversation can change one; wired from the registry.
        self._describe_app = describe_app or (lambda _app_id: None)
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)
        store.add_missing_columns(
            "conversations",
            {
                "change_of": "TEXT",
                "quick_change": "INTEGER NOT NULL DEFAULT 0",
                "proposal_json": "TEXT",
                "researched": "INTEGER NOT NULL DEFAULT 0",
                "session_id": "TEXT",
            },
        )
        # Set by main once the creation service exists: starts a quick change for a conversation.
        self.on_quick_change: Callable[[str], Any] | None = None
        self._no_triage: set[str] = set()  # conversations continuing a declined quick change

    # ----- public ------------------------------------------------------------------------

    def start(
        self,
        text: str,
        route_id: str | None = None,
        *,
        change_of: str | None = None,
        session_id: str | None = None,
    ) -> ConversationRecord:
        """Begin a conversation: about something new, or (`change_of`) about changing an App
        that already exists, which the brief then describes in full. `session_id` is the
        session it is a card in."""
        route = self._gateway.route(route_id or self._default_route, stage="assistant")
        if change_of is not None and self._describe_app(change_of) is None:
            raise UnknownApp(f"there is no project {change_of!r} to change")
        conversation_id = new_id("conv")
        now = _dt(utc_now())
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO conversations(conversation_id, state, route_id, created_at,
                   updated_at, latest_sequence, change_of, session_id) VALUES (?,?,?,?,?,0,?,?)""",
                (conversation_id, "thinking", route.route_id, now, now, change_of, session_id),
            )
            self._append_turn_locked(conn, conversation_id, "user", "request", {"text": text})
        self._spawn_turn(conversation_id, route, {"text": text})
        return self.get(conversation_id)

    def reply(
        self,
        conversation_id: str,
        *,
        text: str | None = None,
        answers: dict[str, str] | None = None,
        use_defaults: bool = False,
    ) -> ConversationRecord:
        record = self.get(conversation_id)
        if record.state == "thinking":
            raise ConflictError("the assistant is still thinking")
        if not text and not answers and not use_defaults:
            raise ValueError("a reply needs text, answers or use_defaults")
        route = self._gateway.route(record.route_id, stage="assistant")
        content: dict[str, Any] = {}
        if text:
            content["text"] = text
        if answers:
            content["answers"] = answers
        if use_defaults:
            content["use_defaults"] = True
        kind = "answer" if answers or use_defaults else "correction"
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE conversations SET state = 'thinking', error = NULL, updated_at = ?"
                " WHERE conversation_id = ?",
                (_dt(utc_now()), conversation_id),
            )
            self._append_turn_locked(conn, conversation_id, "user", kind, content)
        self._spawn_turn(conversation_id, route, content)
        return self.get(conversation_id)

    def cancel(self, conversation_id: str) -> ConversationRecord:
        """Stop a turn that is still thinking. The conversation ends up failed with a plain
        reason, so the person can try again or start over."""
        record = self.get(conversation_id)
        if record.state != "thinking":
            raise ConflictError(f"there is nothing to stop (the conversation is {record.state})")
        self._fail(conversation_id, "You stopped it")
        self._inference.cancel(conversation_id)
        return self.get(conversation_id)

    def escalate(self, conversation_id: str) -> ConversationRecord:
        """A quick change that turned out to need more: run the person's latest request through
        the full path (brief, plan, build) without asking them to repeat it."""
        record = self.get(conversation_id)
        latest = next((t for t in reversed(record.turns) if t.role == "user"), None)
        if latest is None:
            raise ConflictError("there is nothing to continue")
        route = self._gateway.route(record.route_id, stage="assistant")
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE conversations SET state = 'thinking', error = NULL, quick_change = 0,"
                " updated_at = ? WHERE conversation_id = ?",
                (_dt(utc_now()), conversation_id),
            )
        with self._lock:
            self._no_triage.add(conversation_id)
        self._spawn_turn(conversation_id, route, dict(latest.content))
        return self.get(conversation_id)

    def retry(self, conversation_id: str) -> ConversationRecord:
        """Run a failed turn again from the same user input (nothing new is appended)."""
        record = self.get(conversation_id)
        if record.state != "failed":
            raise ConflictError(f"only a failed turn can be retried (this one is {record.state})")
        latest = next((t for t in reversed(record.turns) if t.role == "user"), None)
        if latest is None:
            raise ConflictError("there is nothing to retry")
        route = self._gateway.route(record.route_id, stage="assistant")
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE conversations SET state = 'thinking', error = NULL, updated_at = ?"
                " WHERE conversation_id = ? AND state = 'failed'",
                (_dt(utc_now()), conversation_id),
            )
        self._spawn_turn(conversation_id, route, dict(latest.content))
        return self.get(conversation_id)

    def _notice(self, route: ModelRoute) -> str:
        apps = None
        if self._app_model_route:
            try:
                apps = self._gateway.route(self._app_model_route)
            except Exception:
                apps = None
        return data_notice(route, apps)

    def reconcile_on_startup(self) -> list[str]:
        """A turn cannot continue across a restart: say so, so the person can retry it."""
        rows = self._store.query(
            "SELECT conversation_id FROM conversations WHERE state = 'thinking'"
        )
        for row in rows:
            self._fail(row["conversation_id"], RESTARTED)
        return [r["conversation_id"] for r in rows]

    def get(self, conversation_id: str) -> ConversationRecord:
        rows = self._store.query(
            "SELECT * FROM conversations WHERE conversation_id = ?", (conversation_id,)
        )
        if not rows:
            raise NotFoundError(conversation_id)
        return self._record(rows[0])

    def list_conversations(self, limit: int = 20) -> list[ConversationRecord]:
        rows = self._store.query(
            "SELECT * FROM conversations ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
        )
        return [self._record(r) for r in rows]

    def brief_revision(self, brief_id: str, revision: int) -> SolutionBrief:
        rows = self._store.query(
            "SELECT brief_json FROM briefs WHERE brief_id = ? AND revision = ?",
            (brief_id, revision),
        )
        if not rows:
            raise NotFoundError(f"{brief_id}.r{revision}")
        return SolutionBrief.model_validate_json(rows[0]["brief_json"])

    # ----- turn ---------------------------------------------------------------------------

    def _spawn_turn(self, conversation_id: str, route: ModelRoute, latest: dict[str, Any]) -> None:
        thread = threading.Thread(
            target=self._run_turn, args=(conversation_id, route, latest), daemon=True
        )
        thread.start()

    def _run_turn(self, conversation_id: str, route: ModelRoute, latest: dict[str, Any]) -> None:
        try:
            record = self.get(conversation_id)
            # Every plain-text turn on a change is triaged: small edits go the quick way even
            # when typed into an older thread of the same module.
            with self._lock:
                skip_triage = conversation_id in self._no_triage
                self._no_triage.discard(conversation_id)
            if (
                record.change_of
                and latest.get("text")
                and not latest.get("answers")
                and not skip_triage
            ):
                if self._triage_change(conversation_id, record, route, str(latest["text"])):
                    return
            history = [
                {"role": t.role, "content": t.content}
                for t in record.turns[:-1]  # the latest user turn is passed separately
            ]
            current = record.current_brief.model_dump(mode="json") if record.current_brief else None
            existing = self._describe_app(record.change_of) if record.change_of else None
            known = self._known(str(latest.get("text") or ""))
            prompt = turn_prompt(history, current, latest, existing=existing, known=known)
            result = self._inference.call(
                route,
                system=system_prompt(self._notice(route)),
                prompt=prompt,
                schema=turn_output_schema(),
                scope_kind="assistant_turn",
                scope_ref=conversation_id,
                fake=fake_assistant if route.route_id == "fake" else None,
            )
            output = AssistantTurnOutput.model_validate(result.output)
            grounded: list[str] = []
            if is_remote(route):
                output, grounded = ground_output(output, self._notice(route))
            if grounded:
                log.info("grounded data-location claims in %s: %s", conversation_id, grounded)
        except InferenceError as exc:
            if exc.code == "cancelled":
                return  # the person stopped it; cancel() already said so
            log.warning("assistant turn failed for %s: %s", conversation_id, exc)
            self._fail(conversation_id, _PLAIN_FAILURE.get(exc.code, "the model service failed"))
            return
        except ValidationError as exc:
            log.warning("assistant turn unusable for %s: %s", conversation_id, exc)
            self._fail(conversation_id, "the model's answer was incomplete")
            return
        except Exception:  # never leave a conversation stuck in thinking
            log.exception("assistant turn crashed for %s", conversation_id)
            self._fail(conversation_id, "something went wrong inside Alpha")
            return
        proposal: dict[str, Any] | None = None
        if self._should_research(record, output):
            proposal = self._research_and_propose(conversation_id, route, output, known)
        self._apply_turn(
            conversation_id,
            latest,
            output,
            result.model,
            result.usage.model_dump(mode="json"),
            grounded,
            proposal=proposal,
        )
        # A change the person asked for needs no second approval: once it is briefed, it goes.
        after = self.get(conversation_id)
        if after.change_of and after.state == "briefed" and self.on_quick_change is not None:
            try:
                self.on_quick_change(conversation_id)
            except Exception:
                log.exception("could not start the change for %s", conversation_id)

    def _should_research(self, record: ConversationRecord, output: AssistantTurnOutput) -> bool:
        """Once per new-module conversation: when the brief is complete (no questions left) and
        nothing has been proposed yet. Changes and answers are never researched."""
        if record.change_of or output.delivery is not Delivery.APP or output.questions:
            return False
        if output.brief_draft is None:
            return False
        rows = self._store.query(
            "SELECT researched FROM conversations WHERE conversation_id = ?",
            (record.conversation_id,),
        )
        return bool(rows) and not rows[0]["researched"]

    def _research_and_propose(
        self,
        conversation_id: str,
        route: ModelRoute,
        output: AssistantTurnOutput,
        known: str | None,
    ) -> dict[str, Any] | None:
        """Look around, then propose two or three shapes. Never blocks the brief: any failure
        means the conversation is briefed as before, without options."""
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE conversations SET state = 'researching', researched = 1, updated_at = ?"
                " WHERE conversation_id = ? AND state = 'thinking'",
                (_dt(utc_now()), conversation_id),
            )
        goal = output.brief_draft.goal if output.brief_draft else output.interpretation.outcome
        brief = output.brief_draft.model_dump(mode="json") if output.brief_draft else {}
        evidence: list[Evidence] = []
        try:
            if route.route_id == "fake":
                evidence = fake_research(goal)
            elif self._researcher is not None:
                evidence = self._researcher.run(goal, brief, scope_ref=conversation_id)
        except Exception:
            log.exception("research failed for %s; proposing without it", conversation_id)
        try:
            result = self._inference.call(
                route,
                system=PROPOSE_SYSTEM,
                prompt=propose_prompt(goal, brief, evidence, known, self._told(conversation_id)),
                schema=propose_schema(),
                scope_kind="proposal",
                scope_ref=conversation_id,
                fake=fake_propose if route.route_id == "fake" else None,
            )
        except InferenceError as exc:
            log.warning("proposal failed for %s: %s", conversation_id, exc)
            return None
        proposal: dict[str, Any] = result.output if isinstance(result.output, dict) else {}
        raw_options = proposal.get("options")
        options: list[dict[str, Any]] = [
            o for o in (raw_options if isinstance(raw_options, list) else []) if isinstance(o, dict)
        ]
        if len(options) < 2:
            return None
        ids = {str(o.get("id")) for o in options}
        default = str(proposal.get("default") or "")
        return {
            "intro": str(proposal.get("intro") or ""),
            "options": options,
            "default": default if default in ids else str(options[0].get("id")),
            "evidence": [e.as_dict() for e in evidence],
        }

    def _told(self, conversation_id: str) -> list[str]:
        """What the person said and chose in this conversation, oldest first, for the options."""
        told: list[str] = []
        for turn in self.get(conversation_id).turns:
            if turn.role != "user":
                continue
            content = turn.content
            if content.get("text"):
                told.append(f"- said: {content['text']}")
            for key, value in (content.get("answers") or {}).items():
                told.append(f"- {key}: {value}")
        return told

    def _known(self, text: str) -> str | None:
        if self._context is None:
            return None
        try:
            return self._context(text) or None
        except Exception:
            log.exception("context pack failed; the turn goes on without it")
            return None

    def _triage_change(
        self, conversation_id: str, record: ConversationRecord, route: ModelRoute, text: str
    ) -> bool:
        """First look at a change request: a small edit is made directly (quick change) and
        needs no brief; anything bigger goes through the usual turn. Returns True when the
        quick path took the conversation."""
        assert record.change_of is not None
        existing = self._describe_app(record.change_of) or ""
        try:
            result = self._inference.call(
                route,
                system=TRIAGE_SYSTEM,
                prompt=triage_prompt(text, existing),
                schema=triage_schema(),
                scope_kind="change_triage",
                scope_ref=conversation_id,
                fake=fake_triage if route.route_id == "fake" else None,
            )
        except InferenceError as exc:
            if exc.code == "cancelled":
                return True
            log.warning("change triage failed for %s (%s); planning instead", conversation_id, exc)
            return False
        output = result.output if isinstance(result.output, dict) else {}
        if output.get("path") != "quick":
            with self._store.transaction() as conn:
                conn.execute(
                    "UPDATE conversations SET quick_change = 0 WHERE conversation_id = ?",
                    (conversation_id,),
                )
            return False
        summary = str(output.get("summary") or text)[:400]
        reply = str(output.get("reply") or "I'm making that change now; your data is kept.")
        now = utc_now()
        with self._store.transaction() as conn:
            self._append_turn_locked(
                conn,
                conversation_id,
                "assistant",
                "assistant",
                {
                    "reply": reply,
                    "delivery": "app",
                    "interpretation": {
                        "outcome": summary,
                        "main_input": "The project as it is today.",
                        "useful_result": "The same project with this change, data kept.",
                        "important_assumptions": [],
                    },
                    "questions": [],
                    "quick_change": True,
                    "model": result.model,
                    "usage": result.usage.model_dump(mode="json"),
                },
            )
            conn.execute(
                """UPDATE conversations SET state = 'briefed', delivery = 'app', quick_change = 1,
                   updated_at = ? WHERE conversation_id = ?""",
                (_dt(now), conversation_id),
            )
        if self.on_quick_change is not None:
            try:
                self.on_quick_change(conversation_id)
            except Exception:
                log.exception("could not start the quick change for %s", conversation_id)
        return True

    def _apply_turn(
        self,
        conversation_id: str,
        latest: dict[str, Any],
        output: AssistantTurnOutput,
        model: str,
        usage: dict[str, Any],
        grounded: list[str] | None = None,
        proposal: dict[str, Any] | None = None,
    ) -> None:
        record = self.get(conversation_id)
        user_turn = record.turns[-1]
        now = utc_now()
        with self._store.transaction() as conn:
            turn = self._append_turn_locked(
                conn,
                conversation_id,
                "assistant",
                "assistant",
                {
                    "reply": output.reply,
                    "delivery": output.delivery.value,
                    "interpretation": output.interpretation.model_dump(),
                    "questions": [q.model_dump() for q in output.questions],
                    "model": model,
                    "usage": usage,
                    # Parts where Core replaced an untrue data-location claim (F11).
                    **({"grounded": grounded} if grounded else {}),
                },
            )
            brief: SolutionBrief | None = None
            if output.delivery is not Delivery.ANSWER and output.brief_draft is not None:
                brief = self._next_brief(record, output, latest, user_turn.turn_id, now)
                conn.execute(
                    "INSERT INTO briefs(brief_id, revision, conversation_id, source_turn_id,"
                    " brief_json, created_at) VALUES (?,?,?,?,?,?)",
                    (
                        brief.id,
                        brief.revision,
                        conversation_id,
                        turn,
                        brief.model_dump_json(),
                        _dt(now),
                    ),
                )
                conn.execute(
                    "UPDATE conversation_turns SET content_json ="
                    " json_set(content_json, '$.brief_revision', ?) WHERE turn_id = ?",
                    (brief.revision, turn),
                )
            if output.delivery is Delivery.ANSWER:
                state = "answered"
            elif output.questions:
                state = "waiting_for_user"
            elif proposal is not None:
                state = "proposed"
            else:
                state = "briefed"
            if proposal is not None:
                conn.execute(
                    "UPDATE conversations SET proposal_json = ? WHERE conversation_id = ?",
                    (json.dumps(proposal), conversation_id),
                )
            conn.execute(
                """UPDATE conversations SET state = ?, delivery = ?, current_brief_id = ?,
                   current_revision = ?, updated_at = ? WHERE conversation_id = ?""",
                (
                    state,
                    output.delivery.value,
                    brief.id
                    if brief
                    else record.current_brief.id
                    if record.current_brief
                    else None,
                    brief.revision
                    if brief
                    else record.current_brief.revision
                    if record.current_brief
                    else None,
                    _dt(now),
                    conversation_id,
                ),
            )

    def _next_brief(
        self,
        record: ConversationRecord,
        output: AssistantTurnOutput,
        latest: dict[str, Any],
        user_turn_id: str,
        now: datetime,
    ) -> SolutionBrief:
        assert output.brief_draft is not None
        previous = record.current_brief
        brief_id = previous.id if previous else new_id("brief")
        revision = (previous.revision + 1) if previous else 1
        # Provenance: assumptions that restate a user answer/correction are attributed to the
        # user turn; everything else is a model default. Prior user-sourced assumptions are kept
        # unless the model dropped them deliberately.
        answered_texts = set()
        if latest.get("answers"):
            answered_texts = {str(v).strip().lower() for v in latest["answers"].values()}
        source_for_new: Literal["model_default", "user_answer", "user_correction"]
        # Only assumptions that restate an answer are the person's (matched below); everything
        # else the model added, even on a turn that carried answers, is its own default.
        if latest.get("text") and previous and not latest.get("answers"):
            source_for_new = "user_correction"
        else:
            source_for_new = "model_default"
        assumptions: list[Assumption] = []
        seen: set[str] = set()
        for text in output.assumptions:
            key = text.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            if any(a and a in key for a in answered_texts):
                assumptions.append(
                    Assumption(text=text, source="user_answer", turn_ref=user_turn_id)
                )
            else:
                prior = next(
                    (
                        a
                        for a in (previous.assumptions if previous else [])
                        if a.text.strip().lower() == key
                    ),
                    None,
                )
                if prior is not None:
                    assumptions.append(prior)
                else:
                    assumptions.append(
                        Assumption(
                            text=text,
                            source=source_for_new,
                            turn_ref=user_turn_id if source_for_new != "model_default" else None,
                        )
                    )
        draft = output.brief_draft
        return SolutionBrief(
            id=brief_id,
            revision=revision,
            conversation_id=record.conversation_id,
            created_at=now,
            goal=draft.goal,
            success_summary=draft.success_summary,
            delivery=output.delivery,
            surfaces=draft.surfaces,
            inputs=previous.inputs if previous else [],
            primary_journey=draft.primary_journey,
            data_needs=draft.data_needs,
            actions=draft.actions,
            recurrence=draft.recurrence,
            constraints=draft.constraints,
            acceptance_examples=draft.acceptance_examples,
            assumptions=assumptions,
            open_questions=output.questions,
            unavailable_capabilities=draft.unavailable_capabilities,
            selected_context_snapshot_id=f"{record.conversation_id}.context.r{revision}",
            supersedes_revision=previous.revision if previous else None,
        )

    def _fail(self, conversation_id: str, error: str) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE conversations SET state = 'failed', error = ?, updated_at = ?"
                " WHERE conversation_id = ? AND state IN ('thinking', 'researching')",
                (error, _dt(utc_now()), conversation_id),
            )

    # ----- persistence ----------------------------------------------------------------------

    def _append_turn_locked(
        self, conn: Any, conversation_id: str, role: str, kind: str, content: dict[str, Any]
    ) -> str:
        row = conn.execute(
            "SELECT latest_sequence FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        sequence = int(row["latest_sequence"]) + 1
        turn_id = new_id("turn")
        now = _dt(utc_now())
        conn.execute(
            "INSERT INTO conversation_turns(turn_id, conversation_id, sequence, role, kind,"
            " content_json, created_at) VALUES (?,?,?,?,?,?,?)",
            (turn_id, conversation_id, sequence, role, kind, json.dumps(content, default=str), now),
        )
        conn.execute(
            "UPDATE conversations SET latest_sequence = ?, updated_at = ?"
            " WHERE conversation_id = ?",
            (sequence, now, conversation_id),
        )
        return turn_id

    def _record(self, row: Any) -> ConversationRecord:
        turns = [
            ConversationTurn(
                turn_id=t["turn_id"],
                sequence=int(t["sequence"]),
                role=t["role"],
                kind=t["kind"],
                content=json.loads(t["content_json"]),
                created_at=t["created_at"],
            )
            for t in self._store.query(
                "SELECT * FROM conversation_turns WHERE conversation_id = ? ORDER BY sequence",
                (row["conversation_id"],),
            )
        ]
        brief = None
        history: list[int] = []
        if row["current_brief_id"]:
            brief = self.brief_revision(row["current_brief_id"], int(row["current_revision"]))
            history = [
                int(r["revision"])
                for r in self._store.query(
                    "SELECT revision FROM briefs WHERE brief_id = ? ORDER BY revision",
                    (row["current_brief_id"],),
                )
            ]
        latest_assistant = next((t for t in reversed(turns) if t.role == "assistant"), None)
        interpretation = None
        questions: list[OpenQuestion] = []
        reply = None
        if latest_assistant is not None:
            content = latest_assistant.content
            interpretation = (
                Interpretation.model_validate(content["interpretation"])
                if content.get("interpretation")
                else None
            )
            reply = content.get("reply")
            if row["state"] == "waiting_for_user":
                questions = [OpenQuestion.model_validate(q) for q in content.get("questions", [])]
        return ConversationRecord(
            conversation_id=row["conversation_id"],
            change_of=row["change_of"],
            session_id=row["session_id"] if "session_id" in row.keys() else None,
            quick_change=bool(row["quick_change"]),
            proposal=json.loads(row["proposal_json"])
            if "proposal_json" in row.keys() and row["proposal_json"]
            else None,
            state=row["state"],
            route_id=row["route_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            turns=turns,
            current_brief=brief,
            interpretation=interpretation,
            questions=questions,
            reply=reply,
            delivery=Delivery(row["delivery"]) if row["delivery"] else None,
            error=row["error"],
            brief_history=history,
            data_notice=self._notice_for(row["route_id"]),
        )

    def _notice_for(self, route_id: str) -> str | None:
        try:
            return self._notice(self._gateway.route(route_id))
        except Exception:
            return None


class ConflictError(Exception):
    pass


class UnknownApp(Exception):
    pass
