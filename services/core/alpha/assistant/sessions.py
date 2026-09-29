# ruff: noqa: E501
"""Sessions: the durable, resumable chats between the person and Alpha.

A session belongs to a project or to none (global), may focus on one module as a hint, and
holds turns: what the person said, what Alpha replied, and the work that came of it (a build
or change conversation, runs, a skill run) as cards. Every turn is kept verbatim in SQLite and
indexed with FTS5, so "what did we say about X" is a bounded keyword search over the person's
own words rather than a lossy extraction. When a session outgrows its window, the older turns
are folded into a summary in one call that also proposes facts worth keeping (the person
accepts them on About you or the project page) and refreshes the project's notes. Nothing is
extracted per turn; the turn stays fast.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from alpha.capabilities.errors import conflict, invalid, not_found
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, new_id, utc_now

log = logging.getLogger("alpha.sessions")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    project_id TEXT,
    title TEXT,
    focus_app_id TEXT,
    origin TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'idle',
    summary TEXT,
    summarised_before INTEGER NOT NULL DEFAULT 0,
    latest_sequence INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT
);
CREATE INDEX IF NOT EXISTS sessions_project ON sessions(project_id, updated_at);
CREATE TABLE IF NOT EXISTS session_turns (
    turn_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(session_id),
    sequence INTEGER NOT NULL,
    role TEXT NOT NULL,
    kind TEXT NOT NULL,
    text TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, sequence)
);
CREATE VIRTUAL TABLE IF NOT EXISTS session_turns_fts USING fts5(
    text, content='session_turns', content_rowid='rowid', tokenize='porter unicode61'
);
CREATE TRIGGER IF NOT EXISTS session_turns_ai AFTER INSERT ON session_turns BEGIN
    INSERT INTO session_turns_fts(rowid, text) VALUES (new.rowid, new.text);
END;
CREATE TRIGGER IF NOT EXISTS session_turns_ad AFTER DELETE ON session_turns BEGIN
    INSERT INTO session_turns_fts(session_turns_fts, rowid, text) VALUES ('delete', old.rowid, old.text);
END;
"""

QUICK_ASKS_TITLE = "Quick asks"
# Turns kept verbatim in the prompt; beyond COMPACT_AT unsummarised turns, the oldest fold
# into the summary and WINDOW_TURNS stay.
WINDOW_TURNS = 12
COMPACT_AT = 24
MAX_TEXT = 8000
MAX_SUMMARY = 3000
MAX_TITLE = 80
SEARCH_LIMIT = 5

COMPACT_SYSTEM = """You keep Alpha's notes on a conversation between a person and their assistant. Given the notes so far and the turns being folded away, write:
- summary: the notes after folding, at most 200 words: what the person wanted, what was done (counts, names, dates), what is still open, and decisions or preferences they stated. Keep what still matters from the earlier notes; drop chatter.
- project_notes: only when PROJECT NOTES are given: the project's notes updated with anything from these turns that matters to the project as a whole (goal, progress, decisions, what failed), at most 200 words. Otherwise null.
- facts: things worth remembering beyond this conversation that the person stated or clearly implied: each {field (snake_case, e.g. target_roles, dietary_goal, preferred_tone), value (short), why (one sentence quoting what they said), scope ("person" for facts about them in general, "project" for facts that only matter to this project)}. At most 4. Nothing invented, nothing already in the notes as a fact.
Output only the structured object."""


def compact_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["summary"],
        "properties": {
            "summary": {"type": "string", "maxLength": 2000},
            "project_notes": {"type": ["string", "null"], "maxLength": 2000},
            "facts": {
                "type": ["array", "null"],
                "maxItems": 4,
                "items": {
                    "type": "object",
                    "required": ["field", "value"],
                    "properties": {
                        "field": {"type": "string"},
                        "value": {"type": "string"},
                        "why": {"type": ["string", "null"]},
                        "scope": {"type": ["string", "null"], "enum": ["person", "project", None]},
                    },
                },
            },
        },
    }


def fake_compact(prompt: str) -> dict[str, Any]:
    """Control responder: a plain summary counting the folded turns; a `fact:` line in the
    turns becomes a suggested fact."""
    folded = prompt.split("TURNS BEING FOLDED AWAY")[-1]
    said = re.findall(r"^person: (.*)$", folded, re.M)
    facts = []
    for line in said:
        match = re.search(r"fact:(\w+)=(\S+)", line)
        if match:
            facts.append(
                {
                    "field": match.group(1),
                    "value": match.group(2),
                    "why": line[:100],
                    "scope": "person",
                }
            )
    notes = "PROJECT NOTES" in prompt
    return {
        "summary": f"Folded {len(said)} turn(s): " + "; ".join(s[:40] for s in said[:6]),
        "project_notes": f"Project notes after {len(said)} turn(s)." if notes else None,
        "facts": facts,
    }


def _now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


class SessionTurn(BaseModel):
    turn_id: str
    sequence: int
    role: str  # user | alpha
    kind: str  # text | work
    text: str
    # For a work turn: the conversation it started or continued, what was opened, the
    # observations behind the reply, and one line of outcome (computed when read).
    conversation_id: str | None = None
    open: dict[str, Any] | None = None
    outcome: str | None = None
    detail: dict[str, Any] | None = None
    created_at: str


class Session(BaseModel):
    session_id: str
    project_id: str | None = None
    title: str | None = None
    focus_app_id: str | None = None
    origin: str
    state: str
    # Alpha's notes on the turns folded away (the oldest ones); the rest are in `turns`.
    summary: str | None = None
    turns: list[SessionTurn]
    turn_count: int
    created_at: str
    updated_at: str
    archived_at: str | None = None


class SessionSummary(BaseModel):
    session_id: str
    project_id: str | None = None
    title: str | None = None
    focus_app_id: str | None = None
    origin: str
    state: str
    turn_count: int
    last_text: str | None = None
    created_at: str
    updated_at: str


class SessionService:
    def __init__(
        self,
        store: ControlStore,
        *,
        gateway: Any | None = None,
        inference: StructuredInference | None = None,
        default_route: str = "fake",
        profile: Any | None = None,
        projects: Any | None = None,
        outcome: Callable[[SessionTurn], str | None] | None = None,
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._inference = inference
        self._default_route = default_route
        self._profile = profile
        self._projects = projects
        # Computes a work turn's outcome line at read time (the acting service knows how).
        self._outcome = outcome
        self._lock = threading.Lock()
        self._compacting: set[str] = set()
        store.execute_script(_SCHEMA)
        self._import_act_turns()

    def bind_outcome(self, outcome: Callable[[SessionTurn], str | None]) -> None:
        self._outcome = outcome

    # ----- sessions ----------------------------------------------------------------------

    def create(
        self,
        *,
        project_id: str | None = None,
        focus_app_id: str | None = None,
        origin: str = "shell",
        title: str | None = None,
    ) -> Session:
        if self._projects is not None and project_id is not None:
            self._projects.get(project_id)
        now = _now()
        session_id = new_id("sess")
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO sessions(session_id, project_id, title, focus_app_id, origin, state,
                   created_at, updated_at) VALUES (?,?,?,?,?,'idle',?,?)""",
                (session_id, project_id, _clip(title, MAX_TITLE), focus_app_id, origin, now, now),
            )
        return self.get(session_id)

    def get(self, session_id: str, *, window: int = 60) -> Session:
        row = self._row(session_id)
        rows = self._store.query(
            "SELECT * FROM session_turns WHERE session_id = ? AND sequence > ?"
            " ORDER BY sequence DESC LIMIT ?",
            (session_id, row["summarised_before"], window),
        )
        turns = [self._turn(r) for r in reversed(rows)]
        return Session(
            session_id=row["session_id"],
            project_id=row["project_id"],
            title=row["title"],
            focus_app_id=row["focus_app_id"],
            origin=row["origin"],
            state=row["state"],
            summary=row["summary"],
            turns=turns,
            turn_count=row["latest_sequence"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived_at=row["archived_at"],
        )

    def list_sessions(
        self,
        *,
        project_id: str | None = None,
        scope: str = "all",
        limit: int = 30,
        include_archived: bool = False,
    ) -> list[SessionSummary]:
        """`scope`: "global" (no project), "project" (the given one), or "all"."""
        where = [] if include_archived else ["archived_at IS NULL"]
        params: list[Any] = []
        if scope == "global":
            where.append("project_id IS NULL")
        elif scope == "project":
            where.append("project_id = ?")
            params.append(project_id)
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        rows = self._store.query(
            f"SELECT * FROM sessions{clause} ORDER BY updated_at DESC LIMIT ?", (*params, limit)
        )
        return [self._summary(r) for r in rows]

    def latest(self, *, project_id: str | None, origin: str = "shell") -> SessionSummary | None:
        found = self.list_sessions(
            project_id=project_id, scope="project" if project_id else "global", limit=20
        )
        for session in found:
            if session.origin == origin:
                return session
        return None

    def quick_asks(self) -> Session:
        """The one global session the desktop avatar talks to, made on first use."""
        rows = self._store.query(
            "SELECT session_id FROM sessions WHERE origin = 'avatar' AND archived_at IS NULL"
            " ORDER BY created_at LIMIT 1"
        )
        if rows:
            return self.get(rows[0]["session_id"])
        return self.create(origin="avatar", title=QUICK_ASKS_TITLE)

    def update(
        self,
        session_id: str,
        *,
        title: str | None = None,
        focus_app_id: str | None = None,
        archived: bool | None = None,
        summary: str | None = None,
    ) -> Session:
        self._row(session_id)
        sets, values = [], []
        if title is not None:
            sets.append("title = ?")
            values.append(_clip(title, MAX_TITLE))
        if focus_app_id is not None:
            sets.append("focus_app_id = ?")
            values.append(focus_app_id or None)
        if archived is not None:
            sets.append("archived_at = ?")
            values.append(_now() if archived else None)
        if summary is not None:
            sets.append("summary = ?")
            values.append(_clip(summary, MAX_SUMMARY))
        if sets:
            values.append(session_id)
            with self._store.transaction() as conn:
                conn.execute(f"UPDATE sessions SET {', '.join(sets)} WHERE session_id = ?", values)
        return self.get(session_id)

    def set_state(self, session_id: str, state: str) -> None:
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET state = ?, updated_at = ? WHERE session_id = ?",
                (state, _now(), session_id),
            )

    def begin_turn(self, session_id: str) -> None:
        """Claim the session for one turn; a second sender while it thinks is refused."""
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT state FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise not_found("no such session", session_id=session_id)
            if row["state"] == "thinking":
                raise conflict("Alpha is still working on the last message; wait for it to finish")
            conn.execute(
                "UPDATE sessions SET state = 'thinking', updated_at = ? WHERE session_id = ?",
                (_now(), session_id),
            )

    def reconcile_on_startup(self) -> list[str]:
        rows = self._store.query("SELECT session_id FROM sessions WHERE state = 'thinking'")
        for row in rows:
            self.set_state(row["session_id"], "idle")
        return [r["session_id"] for r in rows]

    # ----- turns -------------------------------------------------------------------------

    def append(
        self,
        session_id: str,
        role: str,
        text: str,
        *,
        kind: str = "text",
        detail: dict[str, Any] | None = None,
        turn_id: str | None = None,
    ) -> SessionTurn:
        clean = text.strip()
        if not clean and kind == "text":
            raise invalid("a turn needs some text")
        turn_id = turn_id or new_id("turn")
        now = _now()
        with self._store.transaction() as conn:
            row = conn.execute(
                "SELECT latest_sequence, title FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if row is None:
                raise not_found("no such session", session_id=session_id)
            sequence = int(row["latest_sequence"]) + 1
            conn.execute(
                """INSERT INTO session_turns(turn_id, session_id, sequence, role, kind, text,
                   detail_json, created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    turn_id,
                    session_id,
                    sequence,
                    role,
                    kind,
                    clean[:MAX_TEXT],
                    json.dumps(detail or {}, default=str),
                    now,
                ),
            )
            title = row["title"]
            if title is None and role == "user":
                title = _title_from(clean)
            conn.execute(
                "UPDATE sessions SET latest_sequence = ?, updated_at = ?, title = ? WHERE session_id = ?",
                (sequence, now, title, session_id),
            )
        rows = self._store.query("SELECT * FROM session_turns WHERE turn_id = ?", (turn_id,))
        return self._turn(rows[0])

    def window(self, session_id: str, limit: int = WINDOW_TURNS) -> list[SessionTurn]:
        """The most recent turns not yet folded into the summary, oldest first."""
        row = self._row(session_id)
        rows = self._store.query(
            "SELECT * FROM session_turns WHERE session_id = ? AND sequence > ?"
            " ORDER BY sequence DESC LIMIT ?",
            (session_id, row["summarised_before"], limit),
        )
        return [self._turn(r) for r in reversed(rows)]

    def latest_work(self, session_id: str) -> SessionTurn | None:
        rows = self._store.query(
            "SELECT * FROM session_turns WHERE session_id = ? AND kind = 'work'"
            " ORDER BY sequence DESC LIMIT 1",
            (session_id,),
        )
        return self._turn(rows[0]) if rows else None

    def session_of_conversation(self, conversation_id: str) -> str | None:
        rows = self._store.query(
            "SELECT session_id FROM session_turns WHERE kind = 'work'"
            " AND json_extract(detail_json, '$.conversation_id') = ? LIMIT 1",
            (conversation_id,),
        )
        return rows[0]["session_id"] if rows else None

    def search(
        self,
        query: str,
        *,
        project_id: str | None = None,
        scope: str = "all",
        except_session: str | None = None,
        limit: int = SEARCH_LIMIT,
    ) -> list[dict[str, Any]]:
        """Verbatim turns that match the words of `query`, best first, with their session."""
        match = _fts_query(query)
        if not match:
            return []
        where = ["s.archived_at IS NULL"]
        params: list[Any] = [match]
        if scope == "global":
            where.append("s.project_id IS NULL")
        elif scope == "project" and project_id:
            where.append("s.project_id = ?")
            params.append(project_id)
        if except_session:
            where.append("t.session_id != ?")
            params.append(except_session)
        params.append(limit)
        try:
            rows = self._store.query(
                f"""SELECT t.*, s.title AS session_title, s.project_id AS session_project
                    FROM session_turns_fts f
                    JOIN session_turns t ON t.rowid = f.rowid
                    JOIN sessions s ON s.session_id = t.session_id
                    WHERE session_turns_fts MATCH ? AND {" AND ".join(where)}
                    ORDER BY bm25(session_turns_fts) LIMIT ?""",
                tuple(params),
            )
        except Exception:
            log.debug("session search failed for %r", query, exc_info=True)
            return []
        return [
            {
                "session_id": r["session_id"],
                "session_title": r["session_title"],
                "project_id": r["session_project"],
                "turn_id": r["turn_id"],
                "role": r["role"],
                "text": r["text"][:400],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    # ----- memory ------------------------------------------------------------------------

    def memory_text(self, session_id: str, sentence: str) -> str:
        """What a turn's prompt carries about this session: the notes, the recent turns and
        matching turns from other sessions in the same scope, each labelled."""
        row = self._row(session_id)
        parts: list[str] = []
        if row["summary"]:
            parts += ["EARLIER IN THIS SESSION (Alpha's notes):", row["summary"], ""]
        recent = self.window(session_id)
        if recent:
            parts.append("THIS SESSION SO FAR (oldest first) and what each turn actually led to:")
            for turn in recent:
                if turn.role == "user":
                    parts.append(f"- person: {turn.text}")
                else:
                    if turn.outcome:
                        parts.append(f"  outcome: {turn.outcome}")
                    parts.append(f"  alpha said: {turn.text}")
            parts.append("")
        scope = "project" if row["project_id"] else "global"
        related = self.search(
            sentence, project_id=row["project_id"], scope=scope, except_session=session_id, limit=4
        )
        if related:
            parts.append(
                "FROM OTHER SESSIONS THAT MENTION THIS (their own words, for context only):"
            )
            for hit in related:
                who = "person" if hit["role"] == "user" else "alpha"
                parts.append(
                    f"- [{hit['session_title'] or 'untitled'}, {hit['created_at'][:10]}] {who}: {hit['text'][:200]}"
                )
            parts.append("")
        return "\n".join(parts).strip()

    def after_turn(self, session_id: str) -> None:
        """Fold older turns into the notes when the session has outgrown its window. Runs in
        the background; a session is compacted by one thread at a time."""
        row = self._row(session_id)
        unsummarised = int(row["latest_sequence"]) - int(row["summarised_before"])
        if unsummarised < COMPACT_AT or self._inference is None or self._gateway is None:
            return
        with self._lock:
            if session_id in self._compacting:
                return
            self._compacting.add(session_id)
        threading.Thread(
            target=self._compact_quietly, args=(session_id,), name="session-compact", daemon=True
        ).start()

    def _compact_quietly(self, session_id: str) -> None:
        try:
            self.compact(session_id)
        except Exception:
            log.exception("compacting %s failed", session_id)
        finally:
            with self._lock:
                self._compacting.discard(session_id)

    def compact(self, session_id: str) -> Session:
        """One model call: fold every turn but the last WINDOW_TURNS into the notes, refresh
        the project's notes, and suggest facts worth keeping (never accepted here)."""
        assert self._inference is not None and self._gateway is not None
        row = self._row(session_id)
        keep_from = int(row["latest_sequence"]) - WINDOW_TURNS
        rows = self._store.query(
            "SELECT * FROM session_turns WHERE session_id = ? AND sequence > ? AND sequence <= ?"
            " ORDER BY sequence",
            (session_id, row["summarised_before"], keep_from),
        )
        if not rows:
            return self.get(session_id)
        folded = [self._turn(r) for r in rows]
        project = None
        if row["project_id"] and self._projects is not None:
            try:
                project = self._projects.get(row["project_id"])
            except Exception:
                project = None
        prompt = _compact_prompt(row["summary"], folded, project)
        route = self._gateway.route(self._default_route, stage="assistant")
        try:
            result = self._inference.call(
                route,
                system=COMPACT_SYSTEM,
                prompt=prompt,
                schema=compact_schema(),
                scope_kind="session_compact",
                scope_ref=session_id,
                fake=fake_compact if route.route_id == "fake" else None,
            )
        except InferenceError as exc:
            log.warning("compacting %s failed: %s", session_id, exc)
            return self.get(session_id)
        output = result.output if isinstance(result.output, dict) else {}
        summary = _clip(str(output.get("summary") or ""), MAX_SUMMARY)
        if not summary:
            return self.get(session_id)
        with self._store.transaction() as conn:
            conn.execute(
                "UPDATE sessions SET summary = ?, summarised_before = ? WHERE session_id = ?",
                (summary, folded[-1].sequence, session_id),
            )
        if project is not None and output.get("project_notes") and self._projects is not None:
            try:
                self._projects.update(project.project_id, summary=str(output["project_notes"]))
            except Exception:
                log.debug("project notes not updated", exc_info=True)
        self._suggest_facts(output.get("facts"), session_id, row["project_id"])
        return self.get(session_id)

    def _suggest_facts(self, facts: Any, session_id: str, project_id: str | None) -> None:
        if self._profile is None or not isinstance(facts, list):
            return
        for fact in facts[:4]:
            if not isinstance(fact, dict) or not fact.get("field") or not fact.get("value"):
                continue
            field = re.sub(r"[^a-z0-9_]", "_", str(fact["field"]).strip().lower())[:64]
            if not re.match(r"^[a-z][a-z0-9_]*$", field):
                continue
            scope = "person"
            if fact.get("scope") == "project" and project_id:
                scope = f"project:{project_id}"
            try:
                self._profile.claim(
                    field,
                    str(fact["value"])[:400],
                    provenance="assistant",
                    source=session_id,
                    why=_clip(str(fact.get("why") or ""), 400),
                    confidence=0.7,
                    accepted=False,
                    scope=scope,
                )
            except Exception:
                log.debug("fact suggestion dropped", exc_info=True)

    # ----- pieces ------------------------------------------------------------------------

    def _import_act_turns(self) -> None:
        """One-time: the avatar's earlier flat turns become the Quick asks session."""
        try:
            rows = self._store.query("SELECT * FROM act_turns ORDER BY created_at")
        except Exception:
            return
        if not rows:
            return
        existing = self._store.query("SELECT 1 FROM sessions WHERE origin = 'avatar' LIMIT 1")
        if existing:
            return
        session = self.create(origin="avatar", title=QUICK_ASKS_TITLE)
        for row in rows:
            detail = json.loads(row["detail_json"]) if row["detail_json"] else {}
            self.append(session.session_id, "user", row["text"])
            self.append(
                session.session_id,
                "alpha",
                row["reply"] or "(no reply)",
                kind="work" if row["kind"] != "answer" else "text",
                detail={
                    "kind": row["kind"],
                    "app_id": row["app_id"],
                    "action_id": row["action_id"],
                    "run_id": row["run_id"],
                    "conversation_id": row["conversation_id"],
                    "open": detail.get("open"),
                    "observations": detail.get("observations") or [],
                },
            )
        with self._store.transaction() as conn:
            conn.execute("DELETE FROM act_turns")
        log.info("moved %d earlier avatar turn(s) into %s", len(rows), QUICK_ASKS_TITLE)

    def _row(self, session_id: str) -> Any:
        rows = self._store.query("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
        if not rows:
            raise not_found("no such session", session_id=session_id)
        return rows[0]

    def _turn(self, row: Any) -> SessionTurn:
        detail = json.loads(row["detail_json"]) if row["detail_json"] else {}
        turn = SessionTurn(
            turn_id=row["turn_id"],
            sequence=row["sequence"],
            role=row["role"],
            kind=row["kind"],
            text=row["text"],
            conversation_id=detail.get("conversation_id"),
            open=detail.get("open"),
            detail=detail or None,
            created_at=row["created_at"],
        )
        if turn.role == "alpha" and self._outcome is not None:
            try:
                turn.outcome = self._outcome(turn)
            except Exception:
                turn.outcome = None
        return turn

    def _summary(self, row: Any) -> SessionSummary:
        last = self._store.query(
            "SELECT text FROM session_turns WHERE session_id = ? AND role = 'user'"
            " ORDER BY sequence DESC LIMIT 1",
            (row["session_id"],),
        )
        return SessionSummary(
            session_id=row["session_id"],
            project_id=row["project_id"],
            title=row["title"],
            focus_app_id=row["focus_app_id"],
            origin=row["origin"],
            state=row["state"],
            turn_count=row["latest_sequence"],
            last_text=last[0]["text"][:160] if last else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _compact_prompt(summary: str | None, folded: list[SessionTurn], project: Any) -> str:
    parts = ["NOTES SO FAR:", summary or "(none yet)", ""]
    if project is not None:
        parts += [
            f"PROJECT NOTES ({project.name}; goal: {project.goal or 'not stated'}):",
            project.summary or "(none yet)",
            "",
        ]
    parts.append("TURNS BEING FOLDED AWAY (oldest first):")
    for turn in folded:
        who = "person" if turn.role == "user" else "alpha"
        line = f"{who}: {turn.text[:600]}"
        if turn.role == "alpha" and turn.outcome:
            line += f" [outcome: {turn.outcome}]"
        parts.append(line)
    return "\n".join(parts)


def _fts_query(text: str) -> str:
    words = [
        w for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9'_-]{2,}", text.lower()) if w not in _STOP
    ]
    if not words:
        return ""
    return " OR ".join(f'"{w}"' for w in dict.fromkeys(words[:12]))


_STOP = {
    "the",
    "and",
    "for",
    "you",
    "your",
    "with",
    "that",
    "this",
    "what",
    "have",
    "from",
    "are",
    "was",
    "were",
    "can",
    "could",
    "would",
    "should",
    "will",
    "did",
    "does",
    "about",
    "into",
    "just",
    "like",
    "also",
    "then",
    "than",
    "them",
    "they",
    "there",
    "here",
    "when",
    "where",
    "how",
    "why",
    "who",
    "which",
    "please",
    "alpha",
    "make",
    "want",
    "need",
    "get",
    "let",
    "me",
    "my",
    "our",
    "its",
    "it's",
    "i'm",
    "don't",
    "not",
    "but",
    "all",
    "any",
    "some",
}


def _title_from(text: str) -> str:
    words = " ".join(text.split())
    return (words[: MAX_TITLE - 1] + "…") if len(words) > MAX_TITLE else words


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    clean = text.strip()
    return clean[:limit] if clean else None
