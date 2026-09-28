# ruff: noqa: E501
"""The third verb: do.

Besides building a module and changing one, a person can tell Alpha in a sentence to run
something in a module they already have ("log two eggs", "how many calories today", "check the
job boards") and it happens at once: one model call decides which module, action or view the
sentence means and fills the inputs; Core runs it; a short second call (or a plain template)
says what happened. Anything the modules cannot do becomes a build or a change conversation,
started on the spot, so the person never has to repeat themselves.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from alpha_contracts.apps import AppSource, Invocable
from alpha_contracts.runs import TERMINAL_RUN_STATES, Run, RunOrigin, RunState
from pydantic import BaseModel

from alpha.capabilities.errors import OperationFailed
from alpha.data.views import ViewQueryRequest, resolve_view, run_view
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, new_id, utc_now

log = logging.getLogger("alpha.acting")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS act_turns (
    turn_id TEXT PRIMARY KEY,
    text TEXT NOT NULL,
    kind TEXT NOT NULL,
    app_id TEXT,
    action_id TEXT,
    run_id TEXT,
    conversation_id TEXT,
    reply TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

KINDS = ("run", "query", "open", "build", "change", "answer")
RUN_WAIT_SECONDS = 90.0
RESULT_CHARS = 4000

ACT_SYSTEM = """You are Alpha's assistant on the person's desktop. They said one sentence. Decide what Alpha should do with it, using only the modules listed.

Choose exactly one kind:
- "run": the sentence asks a listed module to do something its actions cover (log, add, save, check, sync, mark, update, refresh). Give app_id, action_id and the full input object, taken from the sentence: numbers as numbers, dates as YYYY-MM-DD ("today" is given), choices exactly as listed. If a required input is genuinely missing, use kind "answer" instead and ask for it in one short question.
- "query": the sentence asks about what a module has (how many, what did I, show me, what is left). Give app_id and the view_id that answers it best; Alpha reads it and answers with the numbers.
- "open": the person wants to look at a module or one of its tabs. Give app_id and, when clear, tab_id.
- "change": the person wants a listed module to work or look differently. Give app_id.
- "build": the person wants something no listed module does. Alpha starts making it.
- "answer": a question you can answer directly, a greeting, or a request you cannot map; reply plainly and, if useful, say what Alpha could make.

reply is what the person hears, at most 25 words, warm and specific, no technical words. For "run" and "query" the reply is provisional ("Logging that now.", "Let me look."); Alpha replaces it with the outcome. Never invent modules, actions or fields. Output only the structured object."""

PHRASE_SYSTEM = """Say what just happened in Alpha in one or two short sentences a person would say out loud: the numbers that matter, units, what is left or next. Warm, specific, no field names, no technical words, no lists, at most 40 words. If the result shows a problem, say so plainly and what to do. Output only the structured object."""


class ActTurn(BaseModel):
    turn_id: str
    text: str
    kind: str
    app_id: str | None = None
    app_name: str | None = None
    action_id: str | None = None
    run_id: str | None = None
    conversation_id: str | None = None
    # Where the main window should go, when the sentence asked to look at something.
    open: dict[str, Any] | None = None
    reply: str
    created_at: str


def act_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "reply"],
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "app_id": {"type": ["string", "null"]},
            "action_id": {"type": ["string", "null"]},
            "input": {"type": ["object", "null"]},
            "view_id": {"type": ["string", "null"]},
            "tab_id": {"type": ["string", "null"]},
            "reply": {"type": "string", "maxLength": 300},
        },
    }


def phrase_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["reply"],
        "properties": {"reply": {"type": "string", "maxLength": 400}},
    }


def catalogue_text(sources: list[tuple[str, AppSource]]) -> str:
    """The modules, in the words the model needs: actions it may run, views it may read."""
    lines: list[str] = []
    for app_id, source in sources[:20]:
        lines.append(f"MODULE {app_id}: {source.name}. {source.description}")
        actions = [a for a in source.actions if Invocable.ASSISTANT in a.invocable_from][:12]
        for action in actions:
            schema = action.input_schema or {}
            required = set(schema.get("required") or [])
            inputs = []
            for name, spec in (schema.get("properties") or {}).items():
                spec = spec if isinstance(spec, dict) else {}
                kind = spec.get("type", "text")
                if isinstance(kind, list):
                    kind = "/".join(str(k) for k in kind if k != "null")
                extra = f" one of {spec['enum']}" if spec.get("enum") else ""
                inputs.append(f"{name} ({kind}{', required' if name in required else ''}{extra})")
            lines.append(
                f"  action {action.id}: {action.title}. {action.description}"
                + (f" Inputs: {', '.join(inputs)}." if inputs else " No inputs.")
            )
        for view in list(source.views)[:8]:
            what = view.description or f"{view.kind.value} view of {view.collection}"
            lines.append(f"  view {view.id}: {what}")
        if source.screen is not None:
            tabs = ", ".join(f"{t.id} ({t.title})" for t in source.screen.tabs)
            lines.append(f"  tabs: {tabs}")
        if source.screen is not None and source.screen.assistant_hint:
            lines.append(f"  note: {source.screen.assistant_hint}")
    return "\n".join(lines) if lines else "No modules yet."


def act_prompt(
    text: str, catalogue: str, recent: list[ActTurn], today: str, context_app: str | None
) -> str:
    parts = [f"TODAY: {today}", "", "MODULES:", catalogue, ""]
    if recent:
        parts.append("RECENT EXCHANGES (oldest first):")
        for turn in recent:
            parts.append(f"- person: {turn.text}")
            parts.append(f"  alpha: {turn.reply}")
        parts.append("")
    if context_app:
        parts.append(f"THE PERSON IS LOOKING AT: {context_app}")
        parts.append("")
    parts.append(f"THE PERSON SAID: {text}")
    return "\n".join(parts)


def phrase_prompt(text: str, module: str, what: str, result: Any) -> str:
    body = json.dumps(result, default=str)
    if len(body) > RESULT_CHARS:
        body = body[:RESULT_CHARS] + "…"
    return f"THE PERSON SAID: {text}\nMODULE: {module}\nWHAT ALPHA DID: {what}\nRESULT: {body}"


def fake_act(prompt: str) -> dict[str, Any]:
    """Control responder: a `fake:` directive in the sentence picks the outcome."""
    said = prompt.split("THE PERSON SAID:")[-1].strip()
    match = re.search(r"fake:(run|query|open|change|build|answer)\s*(.*)$", said)
    if not match:
        return {"kind": "answer", "reply": "I can't do that yet, but I could make it."}
    kind, rest = match.group(1), match.group(2).strip()
    words = rest.split(maxsplit=2)
    out: dict[str, Any] = {"kind": kind, "reply": "On it."}
    if kind == "run":
        out.update(app_id=words[0], action_id=words[1])
        out["input"] = json.loads(words[2]) if len(words) > 2 else {}
    elif kind == "query":
        out.update(app_id=words[0], view_id=words[1])
    elif kind == "open":
        out.update(app_id=words[0], tab_id=words[1] if len(words) > 1 else None)
    elif kind == "change":
        out.update(app_id=words[0])
    return out


def fake_phrase(prompt: str) -> dict[str, Any]:
    result = prompt.split("RESULT:")[-1].strip()
    return {"reply": f"Done. {result[:120]}"}


def template_reply(what: str, result: Any) -> str:
    """When no model phrasing is available: the result, tidy, no jargon."""
    if isinstance(result, dict):
        shown = {
            k: v
            for k, v in result.items()
            if k not in ("id", "revision") and not isinstance(v, (dict, list))
        }
        if not shown:
            return f"Done: {what}."
        pairs = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in list(shown.items())[:6])
        return f"Done: {what}. {pairs}."
    if isinstance(result, list):
        return f"{what}: {len(result)} item(s)."
    return f"Done: {what}."


def _small(result: Any) -> bool:
    """An outcome with nothing to say beyond "done" (a saved id and revision)."""
    return isinstance(result, dict) and set(result) <= {"id", "revision", "ok", "saved"}


class ActService:
    def __init__(
        self,
        store: ControlStore,
        gateway: Any,
        inference: StructuredInference,
        *,
        registry: Any,
        runs: Any,
        records: Any,
        assistant: Any,
        default_route: str,
        timezone: str = "UTC",
        run_lookup: Callable[[str], Run] | None = None,
        today: Callable[[], str] | None = None,
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._inference = inference
        self._registry = registry
        self._runs = runs
        self._records = records
        self._assistant = assistant
        self._default_route = default_route
        self._timezone = timezone
        self._run_lookup = run_lookup or store.get_run
        self._today = today or (lambda: utc_now().date().isoformat())
        self._lock = threading.Lock()
        store.execute_script(_SCHEMA)

    # ----- public ------------------------------------------------------------------------

    def recent(self, limit: int = 10) -> list[ActTurn]:
        rows = self._store.query(
            "SELECT * FROM act_turns ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        return [self._turn(r) for r in reversed(rows)]

    def act(self, text: str, *, context_app_id: str | None = None) -> ActTurn:
        """Decide and do, then say what happened. Blocks for the run (bounded)."""
        route = self._gateway.route(self._default_route, stage="assistant")
        sources = self._sources()
        names = {app_id: source.name for app_id, source in sources}
        context = names.get(context_app_id or "") if context_app_id else None
        turn_id = new_id("act")
        try:
            decided = self._inference.call(
                route,
                system=ACT_SYSTEM,
                prompt=act_prompt(
                    text, catalogue_text(sources), self.recent(4), self._today(), context
                ),
                schema=act_schema(),
                scope_kind="act",
                scope_ref=turn_id,
                fake=fake_act if route.route_id == "fake" else None,
            )
            output = decided.output if isinstance(decided.output, dict) else {}
        except InferenceError as exc:
            log.warning("act decision failed: %s", exc)
            output = {"kind": "answer", "reply": "I couldn't work that out just now. Try again?"}
        kind = str(output.get("kind") or "answer")
        app_id = output.get("app_id") if output.get("app_id") in names else None
        reply = str(output.get("reply") or "").strip() or "Done."
        detail: dict[str, Any] = {}
        run_id = conversation_id = action_id = None
        opened: dict[str, Any] | None = None
        if kind == "run" and app_id:
            action_id = str(output.get("action_id") or "")
            raw = output.get("input")
            payload: dict[str, Any] = dict(raw) if isinstance(raw, dict) else {}
            reply, run_id, detail = self._run(
                route, turn_id, text, app_id, names[app_id], action_id, payload
            )
        elif kind == "query" and app_id:
            reply, detail = self._query(
                route, turn_id, text, app_id, names[app_id], str(output.get("view_id") or "")
            )
        elif kind == "open" and app_id:
            opened = {"app_id": app_id, "tab_id": output.get("tab_id")}
            reply = reply if reply != "Done." else f"Opening {names[app_id]}."
        elif kind in ("build", "change"):
            change_of = app_id if kind == "change" else None
            try:
                record = self._assistant.start(text, change_of=change_of)
                conversation_id = record.conversation_id
                opened = {"conversation_id": conversation_id}
                if kind == "change":
                    module = names.get(app_id or "", "that module")
                    reply = f"I'm on it: changing {module}. Alpha shows the details."
                else:
                    reply = "I've started on that. Alpha's window shows what I make of it."
            except Exception as exc:  # the conversation could not start; say so
                log.exception("act could not start a conversation")
                reply = f"I couldn't start that: {exc}"
                kind = "answer"
        else:
            if kind not in ("answer",):
                kind = "answer"
        now = utc_now().isoformat().replace("+00:00", "Z")
        with self._store.transaction() as conn:
            conn.execute(
                """INSERT INTO act_turns(turn_id, text, kind, app_id, action_id, run_id,
                   conversation_id, reply, detail_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    turn_id,
                    text,
                    kind,
                    app_id,
                    action_id,
                    run_id,
                    conversation_id,
                    reply,
                    json.dumps({**detail, "open": opened}, default=str),
                    now,
                ),
            )
        return ActTurn(
            turn_id=turn_id,
            text=text,
            kind=kind,
            app_id=app_id,
            app_name=names.get(app_id or ""),
            action_id=action_id,
            run_id=run_id,
            conversation_id=conversation_id,
            open=opened,
            reply=reply,
            created_at=now,
        )

    # ----- doing --------------------------------------------------------------------------

    def _sources(self) -> list[tuple[str, AppSource]]:
        found: list[tuple[str, AppSource]] = []
        for entry in self._registry.list_apps():
            if entry.get("state") != "active":
                continue
            try:
                found.append((entry["app_id"], self._registry.current(entry["app_id"]).source))
            except OperationFailed:
                continue
        return found

    def _run(
        self,
        route: Any,
        turn_id: str,
        text: str,
        app_id: str,
        app_name: str,
        action_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, str | None, dict[str, Any]]:
        source = self._registry.current(app_id).source
        action = source.action(action_id)
        if action is None:
            return f"{app_name} has nothing that does that.", None, {"problem": "no_action"}
        try:
            run = self._runs.invoke(app_id, action_id, payload, origin=RunOrigin.ASSISTANT)
        except OperationFailed as exc:
            return f"{app_name} couldn't take that: {exc.message}", None, {"problem": exc.code}
        final = self._wait(run.run_id)
        detail = {"state": final.state.value if final else "running", "input": payload}
        if final is None:
            return (
                f"{action.title} is still running in {app_name}; Activity shows it.",
                run.run_id,
                detail,
            )
        if final.state is not RunState.SUCCEEDED:
            why = self._failure(run.run_id) or final.terminal_reason or final.state.value
            return f"{action.title} didn't finish: {why}", run.run_id, detail
        result = final.output
        if _small(result):
            return f"Done: {action.title.lower()} in {app_name}.", run.run_id, detail
        return (
            self._phrase(route, turn_id, text, app_name, action.title, result),
            run.run_id,
            detail,
        )

    def _query(
        self, route: Any, turn_id: str, text: str, app_id: str, app_name: str, view_id: str
    ) -> tuple[str, dict[str, Any]]:
        source = self._registry.current(app_id).source
        try:
            view = resolve_view(source, view_id)
            page = run_view(
                self._records.store(app_id), view, ViewQueryRequest(limit=50), self._timezone
            )
        except OperationFailed as exc:
            return f"I couldn't read that from {app_name}: {exc.message}", {"problem": exc.code}
        data = page.model_dump(mode="json")
        rows: Any = data.get("records") or data.get("groups") or []
        if isinstance(rows, list) and rows and "values" in rows[0]:
            rows = [r["values"] for r in rows]
        what = view.description or f"read {view.id}"
        return self._phrase(route, turn_id, text, app_name, what, rows), {"view": view_id}

    def _wait(self, run_id: str) -> Run | None:
        deadline = time.monotonic() + RUN_WAIT_SECONDS
        while time.monotonic() < deadline:
            run = self._run_lookup(run_id)
            if run.state in TERMINAL_RUN_STATES:
                return run
            time.sleep(0.2)
        return None

    def _failure(self, run_id: str) -> str | None:
        try:
            events = self._store.get_events(run_id)
        except Exception:
            return None
        for event in reversed(events):
            if event.kind == "run.failed":
                payload = event.payload or {}
                return str(payload.get("message") or payload.get("error") or "")[:200] or None
        return None

    def _phrase(
        self, route: Any, turn_id: str, text: str, module: str, what: str, result: Any
    ) -> str:
        try:
            phrased = self._inference.call(
                route,
                system=PHRASE_SYSTEM,
                prompt=phrase_prompt(text, module, what, result),
                schema=phrase_schema(),
                scope_kind="act_phrase",
                scope_ref=turn_id,
                fake=fake_phrase if route.route_id == "fake" else None,
            )
            output = phrased.output if isinstance(phrased.output, dict) else {}
            reply = str(output.get("reply") or "").strip()
            if reply:
                return reply
        except InferenceError as exc:
            log.warning("act phrasing failed: %s", exc)
        return template_reply(what, result)

    def _turn(self, row: Any) -> ActTurn:
        detail = json.loads(row["detail_json"]) if row["detail_json"] else {}
        return ActTurn(
            turn_id=row["turn_id"],
            text=row["text"],
            kind=row["kind"],
            app_id=row["app_id"],
            action_id=row["action_id"],
            run_id=row["run_id"],
            conversation_id=row["conversation_id"],
            open=detail.get("open"),
            reply=row["reply"],
            created_at=row["created_at"],
        )
