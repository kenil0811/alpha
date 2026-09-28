# ruff: noqa: E501
"""The third verb: do.

Besides building a module and changing one, a person tells Alpha in a sentence to do something
with a module they already have ("log two eggs", "how many calories today", "fill in ten days
of sample meals") and it happens at once. Alpha works in short steps: each step one model call
sees the modules, the facts (what is running, what earlier sentences led to) and what this
request has done so far, then either runs a batch of actions, reads a view, opens something,
starts a change or a build, or finishes with a reply written from the observed outcomes. So
the reply can only describe what actually happened, and "are you still on it?" is answered
from the facts, never from the story so far.
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

KINDS = ("run", "query", "skill", "open", "build", "change", "answer", "done")
MAX_STEPS = 8
MAX_RUNS_PER_STEP = 40
TIME_BUDGET_SECONDS = 240.0
RUN_WAIT_SECONDS = 60.0
RESULT_CHARS = 3500
ACTIVE_RUN_STATES = {
    RunState.QUEUED,
    RunState.RUNNING,
    RunState.WAITING_INPUT,
    RunState.WAITING_APPROVAL,
    RunState.WAITING_CONNECTION,
}

STEP_SYSTEM = """You are Alpha's assistant on the person's desktop. They said one sentence. You work in short steps; each answer is one step, using only the modules listed.

Step kinds:
- "run": do something with a module through its actions. Give app_id and runs: a list of {action_id, input}. When the sentence covers several entries (days, items, people), plan the whole set first and put ALL of them in this one step, up to 40, spread evenly (for "ten days of meals": every day gets its breakfast, lunch and dinner), with realistic and varied values. Dates are YYYY-MM-DD, counted from TODAY. Prefer the action that takes the fields directly (calories, amounts) over one that estimates, unless the person asked for estimates. Never invent required inputs you were not given and cannot reasonably make up; ask instead.
- "query": read a module's view to answer a question. Give app_id and view_id.
- "skill": use one of the SKILLS (a way Alpha knows to do a job, often by reading the web). Give skill_id and inputs (an object with the skill's input names). Its result arrives as an observation with items you can then save through a module's actions if the person asked for that, or report.
- "open": the person wants to look at a module or a tab. Give app_id and, when clear, tab_id.
- "change": the person wants a listed module to work or look differently. Give app_id.
- "build": the person wants something no listed module can do. Alpha starts making it.
- "done": the work for this sentence is finished (there are OBSERVATIONS). Finish as soon as the observations cover what was asked; do not keep adding. reply says exactly what happened: counts, numbers and dates from the observations, any failure named plainly. Never more than what the observations show.
- "answer": nothing needs doing (a question you can answer, a greeting, a request outside the modules), or a required detail is missing and you ask one short question. It must be true to FACTS: say that something is in progress only if FACTS list it as running. If the person asks whether you are still working and FACTS show nothing running, say so plainly and offer to do it now.

reply is what the person hears: at most 40 words, warm, specific, no technical words, no field names. For "run" and "query" steps the reply is provisional; the "done" step replaces it. Output only the structured object."""


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
    # What the steps did: for the person's record and for grounding later sentences.
    outcome: str | None = None


def step_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["kind", "reply"],
        "properties": {
            "kind": {"type": "string", "enum": list(KINDS)},
            "app_id": {"type": ["string", "null"]},
            "runs": {
                "type": ["array", "null"],
                "maxItems": MAX_RUNS_PER_STEP,
                "items": {
                    "type": "object",
                    "required": ["action_id"],
                    "properties": {
                        "action_id": {"type": "string"},
                        "input": {"type": ["object", "null"]},
                    },
                },
            },
            "view_id": {"type": ["string", "null"]},
            "tab_id": {"type": ["string", "null"]},
            "skill_id": {"type": ["string", "null"]},
            "inputs": {"type": ["object", "null"]},
            "reply": {"type": "string", "maxLength": 400},
        },
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


def step_prompt(
    text: str,
    catalogue: str,
    facts: list[str],
    recent: list[ActTurn],
    observations: list[dict[str, Any]],
    today: str,
    context_app: str | None,
    known: str = "",
    skills: str = "",
) -> str:
    parts = [f"TODAY: {today}", "", "MODULES:", catalogue, ""]
    if skills:
        parts += ["SKILLS (usable with a skill step):", skills, ""]
    if known:
        parts += [
            "WHAT ALPHA KNOWS (profile facts and records; use them, never ask for what is here):",
            known,
            "",
        ]
    parts.append("FACTS (what is true right now; the only source for claims about progress):")
    parts += [f"- {f}" for f in facts] or ["- nothing is running or being made right now"]
    parts.append("")
    if recent:
        parts.append("EARLIER SENTENCES (oldest first) and what each actually led to:")
        for turn in recent:
            parts.append(f"- person: {turn.text}")
            parts.append(f"  outcome: {turn.outcome or 'nothing was done'}")
            parts.append(f"  alpha said: {turn.reply}")
        parts.append("")
    if context_app:
        parts += [f"THE PERSON IS LOOKING AT: {context_app}", ""]
    parts.append(f"THE PERSON SAID: {text}")
    parts.append("")
    parts.append("OBSERVATIONS (what this sentence's steps have done so far):")
    if observations:
        body = json.dumps(observations, default=str)
        if len(body) > RESULT_CHARS:
            body = body[:RESULT_CHARS] + "…"
        parts.append(body)
    else:
        parts.append("(none yet)")
    return "\n".join(parts)


def fake_act(prompt: str) -> dict[str, Any]:
    """Control responder: a `fake:` directive in the sentence picks the steps."""
    said = prompt.split("THE PERSON SAID:")[-1].split("OBSERVATIONS")[0].strip()
    observed = "(none yet)" not in prompt.split("OBSERVATIONS")[-1]
    match = re.search(r"fake:(runs|run|query|skill|open|change|build|answer)\s*(.*)$", said, re.S)
    if not match:
        return {"kind": "answer", "reply": "I can't do that yet, but I could make it."}
    kind, rest = match.group(1), match.group(2).strip()
    if observed:
        results = prompt.split("OBSERVATIONS")[-1]
        succeeded = results.count('"succeeded"')
        failed = results.count('"failed')
        rows = results.count('"rows"')
        return {
            "kind": "done",
            "reply": f"Done: {succeeded} succeeded, {failed} failed, {rows} read.",
        }
    words = rest.split(maxsplit=2)
    out: dict[str, Any] = {"kind": kind, "reply": "On it."}
    if kind == "run":
        payload = json.loads(words[2]) if len(words) > 2 else {}
        out.update(kind="run", app_id=words[0], runs=[{"action_id": words[1], "input": payload}])
    elif kind == "runs":
        inputs = json.loads(words[2]) if len(words) > 2 else [{}]
        out.update(
            kind="run", app_id=words[0], runs=[{"action_id": words[1], "input": i} for i in inputs]
        )
    elif kind == "query":
        out.update(app_id=words[0], view_id=words[1])
    elif kind == "skill":
        out.update(
            skill_id=words[0], inputs=json.loads(" ".join(words[1:])) if len(words) > 1 else {}
        )
    elif kind == "open":
        out.update(app_id=words[0], tab_id=words[1] if len(words) > 1 else None)
    elif kind == "change":
        out.update(app_id=words[0])
    return out


def summary_reply(observations: list[dict[str, Any]]) -> str:
    """When the model could not write the final reply: the outcomes, counted plainly."""
    done = failed = read = 0
    for obs in observations:
        for result in obs.get("results", []):
            if result.get("outcome") == "succeeded":
                done += 1
            else:
                failed += 1
        if "rows" in obs:
            read += 1
        if obs.get("step") == "skill":
            read += 1
    parts = []
    if done:
        parts.append(f"{done} done")
    if failed:
        parts.append(f"{failed} did not go through")
    if read:
        parts.append(f"{read} thing(s) read")
    return ("Finished: " + ", ".join(parts) + ".") if parts else "Nothing was done."


def outcome_line(kind: str, detail: dict[str, Any], app_name: str | None) -> str:
    """One line of truth about a past sentence, for the person's record and for grounding."""
    observations = detail.get("observations") or []
    runs = [r for o in observations for r in o.get("results", [])]
    if runs:
        ok = sum(1 for r in runs if r.get("outcome") == "succeeded")
        names = sorted({str(r.get("action")) for r in runs})
        where = f" in {app_name}" if app_name else ""
        return f"ran {', '.join(names)} {len(runs)} time(s){where}: {ok} succeeded, {len(runs) - ok} failed"
    if any("rows" in o for o in observations):
        return f"read {app_name or 'a module'}; nothing was changed"
    used = [str(o.get("skill")) for o in observations if o.get("step") == "skill"]
    if used:
        return f"used the skill {', '.join(used)}; nothing was changed"
    if kind == "open":
        return f"opened {app_name or 'a module'} in Alpha's window"
    if kind in ("build", "change"):
        return f"started a conversation to {'change ' + app_name if kind == 'change' and app_name else 'make something new'}"
    return "nothing was done; Alpha only replied"


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
        creations: Any | None = None,
        context: Callable[[str], str] | None = None,
        skills: Any | None = None,
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
        self._creations = creations
        self._context = context
        self._skills = skills
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
        """Work the sentence through in steps, then say what happened. Blocks (bounded)."""
        route = self._gateway.route(self._default_route, stage="assistant")
        sources = self._sources()
        names = {app_id: source.name for app_id, source in sources}
        context = names.get(context_app_id or "") if context_app_id else None
        turn_id = new_id("act")
        catalogue = catalogue_text(sources)
        facts = self._facts(names)
        known = ""
        if self._context is not None:
            try:
                known = self._context(text)
            except Exception:
                log.exception("context pack failed; the sentence goes on without it")
        skills_text = self._skills.catalogue_text() if self._skills is not None else ""
        recent = self.recent(5)
        started = time.monotonic()
        deadline = started + TIME_BUDGET_SECONDS
        observations: list[dict[str, Any]] = []
        kind, app_id, action_id, run_id, conversation_id = "answer", None, None, None, None
        opened: dict[str, Any] | None = None
        reply = ""
        for _step in range(MAX_STEPS):
            try:
                decided = self._inference.call(
                    route,
                    system=STEP_SYSTEM,
                    prompt=step_prompt(
                        text,
                        catalogue,
                        facts,
                        recent,
                        observations,
                        self._today(),
                        context,
                        known=known,
                        skills=skills_text,
                    ),
                    schema=step_schema(),
                    scope_kind="act",
                    scope_ref=turn_id,
                    fake=fake_act if route.route_id == "fake" else None,
                )
                output = decided.output if isinstance(decided.output, dict) else {}
            except InferenceError as exc:
                log.warning("act step failed: %s", exc)
                output = {"kind": "done" if observations else "answer", "reply": ""}
            step_kind = str(output.get("kind") or "answer")
            step_app = output.get("app_id") if output.get("app_id") in names else None
            step_reply = str(output.get("reply") or "").strip()
            if step_kind == "run" and step_app and isinstance(output.get("runs"), list):
                app_id, kind = step_app, "run"
                results = self._run_batch(step_app, output["runs"], deadline)
                if results and action_id is None:
                    action_id = str(results[0].get("action"))
                    run_id = next((r.get("run_id") for r in results if r.get("run_id")), None)
                observations.append({"step": "run", "module": names[step_app], "results": results})
                if time.monotonic() > deadline:
                    observations.append({"note": "out of time; the rest was not done"})
                    reply = ""
                    break
                continue
            if step_kind == "query" and step_app:
                app_id = step_app
                kind = kind if kind == "run" else "query"
                observations.append(
                    self._read(step_app, names[step_app], str(output.get("view_id") or ""))
                )
                continue
            if step_kind == "skill" and output.get("skill_id") and self._skills is not None:
                kind = kind if kind == "run" else "skill"
                observations.append(self._use_skill(str(output["skill_id"]), output.get("inputs")))
                if time.monotonic() > deadline:
                    observations.append({"note": "out of time; the rest was not done"})
                    reply = ""
                    break
                continue
            if step_kind == "open" and step_app:
                kind, app_id = "open", step_app
                opened = {"app_id": step_app, "tab_id": output.get("tab_id")}
                reply = step_reply or f"Opening {names[step_app]}."
                break
            if step_kind in ("build", "change"):
                kind = step_kind
                app_id = step_app if step_kind == "change" else None
                try:
                    record = self._assistant.start(text, change_of=app_id)
                    conversation_id = record.conversation_id
                    opened = {"conversation_id": conversation_id}
                    reply = (
                        f"I've asked Alpha to change {names[app_id]}; its window shows the details."
                        if app_id
                        else "I've handed that to Alpha as something new to make; its window shows what happens next."
                    )
                except Exception as exc:  # the conversation could not start; say so
                    log.exception("act could not start a conversation")
                    reply, kind = f"I couldn't start that: {exc}", "answer"
                break
            # done / answer / anything unknown: the reply, grounded on what was observed.
            if step_kind not in ("done", "answer"):
                step_kind = "done" if observations else "answer"
            if not observations:
                kind = "answer"
            reply = step_reply
            break
        if not reply:
            reply = (
                summary_reply(observations)
                if observations
                else "I couldn't work that out just now. Try again?"
            )
        detail = {"observations": observations, "open": opened}
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
                    json.dumps(detail, default=str),
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
            outcome=outcome_line(kind, detail, names.get(app_id or "")),
        )

    # ----- steps --------------------------------------------------------------------------

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

    def _facts(self, names: dict[str, str]) -> list[str]:
        """What is happening right now, from Core's own records."""
        facts: list[str] = []
        try:
            for run in self._store.list_runs_in_states(ACTIVE_RUN_STATES):
                owner = run.owner.model_dump() if hasattr(run.owner, "model_dump") else {}
                app = names.get(str(owner.get("app_id")), str(owner.get("app_id") or "a module"))
                facts.append(f"running now: {owner.get('action_id')} in {app} ({run.state.value})")
        except Exception:
            log.debug("could not list running runs", exc_info=True)
        if self._creations is not None:
            try:
                for creation in self._creations.list_recent(10):
                    if creation.state in ("active", "failed", "cancelled"):
                        continue
                    what = names.get(creation.change_of or "", creation.app_name or "a module")
                    facts.append(f"being made right now: {what} ({creation.label.lower()})")
            except Exception:
                log.debug("could not list creations", exc_info=True)
        for turn in self.recent(5):
            if turn.conversation_id and turn.kind in ("build", "change"):
                state = self._conversation_state(turn.conversation_id)
                facts.append(f'the conversation started for "{turn.text[:60]}" is now: {state}')
        return facts

    def _conversation_state(self, conversation_id: str) -> str:
        try:
            record = self._assistant.get(conversation_id)
        except Exception:
            return "unknown"
        state = str(getattr(record, "state", "unknown"))
        words = {
            "thinking": "Alpha is still reading it",
            "briefed": "planned; a build or change follows in Alpha's window",
            "answered": "answered in Alpha's window; nothing is being built",
            "needs_input": "waiting for the person's answers in Alpha's window",
        }
        return words.get(state, state)

    def _run_batch(self, app_id: str, runs: list[Any], deadline: float) -> list[dict[str, Any]]:
        source = self._registry.current(app_id).source
        results: list[dict[str, Any]] = []
        for item in runs[:MAX_RUNS_PER_STEP]:
            if not isinstance(item, dict):
                continue
            action_id = str(item.get("action_id") or "")
            payload = dict(item.get("input") or {}) if isinstance(item.get("input"), dict) else {}
            entry: dict[str, Any] = {"action": action_id, "input": payload}
            if time.monotonic() > deadline:
                entry["outcome"] = "not done: out of time"
                results.append(entry)
                continue
            action = source.action(action_id)
            if action is None:
                entry["outcome"] = "failed: no such action"
                results.append(entry)
                continue
            try:
                run = self._runs.invoke(app_id, action_id, payload, origin=RunOrigin.ASSISTANT)
            except OperationFailed as exc:
                entry["outcome"] = f"failed: {exc.message}"
                results.append(entry)
                continue
            entry["run_id"] = run.run_id
            final = self._wait(
                run.run_id, min(RUN_WAIT_SECONDS, max(5.0, deadline - time.monotonic()))
            )
            if final is None:
                entry["outcome"] = "still running"
            elif final.state is RunState.SUCCEEDED:
                entry["outcome"] = "succeeded"
                if final.output is not None:
                    entry["output"] = _compact(final.output)
            else:
                why = self._failure(run.run_id) or final.terminal_reason or final.state.value
                entry["outcome"] = f"failed: {why}"
            results.append(entry)
        return results

    def _read(self, app_id: str, app_name: str, view_id: str) -> dict[str, Any]:
        source = self._registry.current(app_id).source
        try:
            view = resolve_view(source, view_id)
            page = run_view(
                self._records.store(app_id), view, ViewQueryRequest(limit=50), self._timezone
            )
        except OperationFailed as exc:
            return {"step": "query", "module": app_name, "view": view_id, "error": exc.message}
        data = page.model_dump(mode="json")
        rows: Any = data.get("records") or data.get("groups") or []
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) and "values" in rows[0]:
            rows = [r["values"] for r in rows]
        return {"step": "query", "module": app_name, "view": view_id, "rows": rows}

    def _use_skill(self, skill_id: str, inputs: Any) -> dict[str, Any]:
        payload = inputs if isinstance(inputs, dict) else {}
        if self._skills is None:
            return {"step": "skill", "skill": skill_id, "error": "skills are not available"}
        try:
            result = self._skills.run(skill_id, payload)
        except OperationFailed as exc:
            return {"step": "skill", "skill": skill_id, "error": exc.message}
        return {
            "step": "skill",
            "skill": skill_id,
            "state": result.state,
            "summary": result.summary,
            "items": result.items[:25],
        }

    def _wait(self, run_id: str, seconds: float) -> Run | None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            run = self._run_lookup(run_id)
            if run.state in TERMINAL_RUN_STATES:
                return run
            time.sleep(0.15)
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

    def _turn(self, row: Any) -> ActTurn:
        detail = json.loads(row["detail_json"]) if row["detail_json"] else {}
        app_name = None
        if row["app_id"]:
            try:
                app_name = self._registry.current(row["app_id"]).source.name
            except Exception:
                app_name = None
        return ActTurn(
            turn_id=row["turn_id"],
            text=row["text"],
            kind=row["kind"],
            app_id=row["app_id"],
            app_name=app_name,
            action_id=row["action_id"],
            run_id=row["run_id"],
            conversation_id=row["conversation_id"],
            open=detail.get("open"),
            reply=row["reply"],
            created_at=row["created_at"],
            outcome=outcome_line(row["kind"], detail, app_name),
        )


def _compact(output: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(output, default=str)
    if len(text) <= 600:
        return output
    return {"summary": text[:600] + "…"}
