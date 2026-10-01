# ruff: noqa: E501
"""The one loop every message goes through.

A person says something in a session (the assistant panel, or the desktop avatar's Quick asks)
and Alpha works it through in short steps: each step one model call sees the modules, the
session's memory (its notes and recent turns, matching turns from other sessions), the project
the session belongs to, the facts (what is running, what earlier turns led to) and what this
message has done so far, then either runs a batch of actions, reads a view, uses a skill, opens
something, starts a change or a build (a conversation that becomes a card in the session), or
finishes with a reply written from the observed outcomes. So the reply can only describe what
actually happened, and "are you still on it?" is answered from the facts, never from the story.

When the session's latest card is a conversation waiting for the person (questions, or a
proposal to choose from), plain text goes to that conversation instead of starting anew.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from alpha_contracts.apps import AppSource, Invocable
from alpha_contracts.runs import TERMINAL_RUN_STATES, Run, RunOrigin, RunState
from pydantic import BaseModel

from alpha.assistant.attachments import AttachmentIn, attachment_summaries, build_context
from alpha.assistant.sessions import SessionService, SessionTurn
from alpha.capabilities.errors import OperationFailed
from alpha.data.views import ViewQueryRequest, resolve_view, run_view
from alpha.models.gateway import RouteUnavailable
from alpha.models.structured import InferenceError, StructuredInference
from alpha.storage.control_store import ControlStore, new_id, utc_now

log = logging.getLogger("alpha.acting")

# Conversation states in which typed text belongs to that conversation, not to a new step.
CONVERSATION_WAITING = {"waiting_for_user", "proposed"}
WAIT_GRACE_SECONDS = 30.0

# The three governance stances the + menu's Access group offers (AP-182 governed-work rule:
# nothing here weakens critical blocks - secret leakage, a residency violation, or an irreversible
# delete of the person's own data still confirms under every mode, enforced where those checks
# already live, not here). Server enforces; the UI only requests (never trust a client-sent mode
# beyond picking which of these three server-side behaviours applies).
ACCESS_MODES = ("ask", "approve_for_me", "full")
DEFAULT_ACCESS_MODE = "ask"

# No risk/unsafe classification exists anywhere in Core today (grep turns up nothing: no
# "is_unsafe", no action-risk registry). This is the explicit fallback the task calls for:
# delete/send/payment-shaped action ids are treated as unsafe/destructive. ponytail: a name
# pattern, not a declared per-action risk field; "writes outside the module's own data" doesn't
# apply yet (every App's records.* calls are already confined to its own collections - see
# AppSource/records isolation) and "new egress host" can't be told apart from a known one at this
# layer (ActService only ever sees {action_id, input}; the actual http.get/browser calls happen
# inside the sandboxed worker, invisible here). Both are flagged as gaps in the commit message,
# not silently assumed done.
_UNSAFE_ACTION_RE = re.compile(
    r"delete|remove|destroy|purge|cancel|send|email|message|post|publish|pay|charge|purchase|"
    r"refund|transfer|withdraw",
    re.I,
)


def _is_unsafe_action(action_id: str) -> bool:
    return bool(_UNSAFE_ACTION_RE.search(action_id or ""))


def needs_approval(access_mode: str, egress: bool, runs: list[dict[str, Any]]) -> bool:
    """Whether a "run" step must wait for the person's yes before Core dispatches it.

    ask: every internet/egress action (the app declares the http or browser capability) or
      anything the unsafe pattern names, needs approval every time - the strict, always-ask stance
      ("Ask for approval - always ask to edit external files and use the internet").
    approve_for_me: only the unsafe/destructive ones; a plain read is never gated.
    full: never gates here (critical blocks are a separate, pre-existing concern - see above)."""
    if access_mode not in ("ask", "approve_for_me"):
        return False
    unsafe = any(_is_unsafe_action(r.get("action_id", "")) for r in runs)
    if access_mode == "ask":
        return egress or unsafe
    return unsafe


# The resume phrase for a pending run's one-click "Approve and run" (see `_offer`): the person's
# own plain yes, typed or clicked, never a hidden sentinel round-tripped through the chat.
_AFFIRM_RE = re.compile(r"^(yes|yeah|yep|sure|ok|okay|go ahead|do it|approve|confirm)\b", re.I)

KINDS = ("run", "query", "skill", "open", "fix", "allow", "build", "change", "answer", "done")
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

STEP_SYSTEM = """You are Alpha's assistant on the person's desktop. They said one thing in an ongoing session. You work in short steps; each answer is one step, using only the projects listed. THIS SESSION SO FAR and the notes are your memory of this session: build on them, never ask again for what is there, and treat "it", "that one", "the same" as referring to what was just discussed.

Step kinds:
- "run": do something with a project through its actions. Give app_id and runs: a list of {action_id, input}. When the sentence covers several entries (days, items, people), plan the whole set first and put ALL of them in this one step, up to 40, spread evenly (for "ten days of meals": every day gets its breakfast, lunch and dinner), with realistic and varied values. Dates are YYYY-MM-DD, counted from TODAY. Prefer the action that takes the fields directly (calories, amounts) over one that estimates, unless the person asked for estimates. Never invent required inputs you were not given and cannot reasonably make up; ask instead.
- "query": read a project's view to answer a question. Give app_id and view_id.
- "skill": use one of the SKILLS (a way Alpha knows to do a job, often by reading the web). Give skill_id and inputs (an object with the skill's input names). Its result arrives as an observation with items you can then save through a project's actions if the person asked for that, or report.
- "open": the person wants to look at a project or a tab. Give app_id and, when clear, tab_id.
- "fix": FACTS list a FAILED run of a project that stopped in its own code and Alpha can fix it, and the person says it is not working, asks why it failed and wants it sorted, asks to fix it, or asks to run that same action again. Give app_id and run_id (from the FACTS line). Alpha then repairs the project's code, switches the fix on with the data kept and runs the action again; the observation says what happened. Never use "change" for something that FACTS show as broken; never claim something is fixed without a fix observation.
- "allow": FACTS say a project got a site's sign-in page because it has not been allowed to read through the person's sign-in, AND the person's message agrees to allow it or asks for it. Give app_id and site. Then, in the next step, run the action that needed it. Without their yes, do not allow: explain in one or two sentences what FACTS say (they are signed in; this project just has not been allowed to use that sign-in) and ask whether to allow it. Never tell them to sign in again when FACTS say they are signed in.
- "change": the person wants a listed project to work or look differently (not a failure: those are "fix"). Give app_id.
- "build": the person wants something no listed project can do. Alpha starts making it.
- "done": the work for this sentence is finished (there are OBSERVATIONS). Finish as soon as the observations cover what was asked; do not keep adding. reply says exactly what happened: counts, numbers and dates from the observations, any failure named plainly. Never more than what the observations show.
- "answer": nothing needs doing (a question you can answer, a greeting, a request outside the projects), or a required detail is missing and you ask one short question. It must be true to FACTS: say that something is in progress only if FACTS list it as running. If the person asks whether you are still working and FACTS show nothing running, say so plainly and offer to do it now.

reply is what the person hears: at most 40 words, warm, specific, no technical words, no field names. For "run" and "query" steps the reply is provisional; the "done" step replaces it. Output only the structured object."""


class ActTurn(BaseModel):
    turn_id: str
    session_id: str | None = None
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
    # What was attached to the person's message (name, kind, size only).
    attachments: list[dict[str, Any]] | None = None
    # Set when the reply is a model-call failure: drives a "not connected" card with a guided
    # fix instead of plain text. {"kind": "sign_in"|"key"|"generic", "provider": route.provider}.
    model_error: dict[str, Any] | None = None


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
            "run_id": {"type": ["string", "null"]},
            "site": {"type": ["string", "null"]},
            "skill_id": {"type": ["string", "null"]},
            "inputs": {"type": ["object", "null"]},
            "reply": {"type": "string", "maxLength": 400},
        },
    }


def catalogue_text(sources: list[tuple[str, AppSource]]) -> str:
    """The modules, in the words the model needs: actions it may run, views it may read."""
    lines: list[str] = []
    for app_id, source in sources[:20]:
        lines.append(f"PROJECT {app_id}: {source.name}. {source.description}")
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
    return "\n".join(lines) if lines else "No projects yet."


def step_prompt(
    text: str,
    catalogue: str,
    facts: list[str],
    memory: str,
    observations: list[dict[str, Any]],
    today: str,
    context_app: str | None,
    known: str = "",
    skills: str = "",
    project: str = "",
    attachments: str = "",
) -> str:
    parts = [f"TODAY: {today}", "", "PROJECTS:", catalogue, ""]
    if skills:
        parts += ["SKILLS (usable with a skill step):", skills, ""]
    if project:
        parts += ["THIS SESSION IS ABOUT THE PROJECT:", project, ""]
    if known:
        parts += [
            "WHAT ALPHA KNOWS (profile facts and records; use them, never ask for what is here):",
            known,
            "",
        ]
    parts.append("FACTS (what is true right now; the only source for claims about progress):")
    parts += [f"- {f}" for f in facts] or ["- nothing is running or being made right now"]
    parts.append("")
    if memory:
        parts += [memory, ""]
    if context_app:
        parts += [f"THE PERSON IS LOOKING AT: {context_app}", ""]
    if attachments:
        parts += [attachments, ""]
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
    match = re.search(
        r"fake:(runs|run|query|skill|open|fix|allow|change|build|answer)\s*(.*)$", said, re.S
    )
    if not match:
        return {"kind": "answer", "reply": "I can't do that yet, but I could make it."}
    kind, rest = match.group(1), match.group(2).strip()
    if observed:
        results = prompt.split("OBSERVATIONS")[-1]
        if '"step": "fix"' in results or '"step": "allow"' in results:
            return {"kind": "done", "reply": ""}  # the summary carries the fix's own words
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
    elif kind == "fix":
        out.update(app_id=words[0], run_id=words[1] if len(words) > 1 else None)
    elif kind == "allow":
        out.update(app_id=words[0], site=words[1] if len(words) > 1 else None)
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
    fixes = [o for o in observations if o.get("step") in ("fix", "allow")]
    if fixes:
        return str(fixes[-1].get("message") or "Alpha looked into the failure.")
    parts = []
    if done:
        parts.append(f"{done} done")
    if failed:
        parts.append(f"{failed} did not go through")
    if read:
        parts.append(f"{read} thing(s) read")
    return ("Finished: " + ", ".join(parts) + ".") if parts else "Nothing was done."


def model_error_reply(exc: InferenceError) -> str:
    """A plain-language reason the model call failed, for known failure shapes; a generic honest
    fallback otherwise. Never hides that something failed."""
    text = str(exc).lower()
    if "subscription" in text and "disabled" in text:
        return (
            "I can't reach the model: your organization turned off Claude sign-in for Claude "
            "Code. Add an Anthropic API key in Settings → Models."
        )
    if exc.code == "cli_not_logged_in" or "not logged in" in text:
        return (
            "I can't reach the model: Claude Code isn't signed in. Run `claude` and sign in, "
            "or add an Anthropic API key in Settings → Models."
        )
    if exc.code == "cli_missing":
        return "I can't reach the model: the `claude` command isn't installed on this machine."
    if exc.code == "no_key":
        return "I can't reach the model: no key is saved for it yet. Add one in Settings → Models."
    if exc.code == "provider_error":
        return f"I can't reach the model: {exc}."
    if exc.code == "timeout":
        return "I can't reach the model: it took too long to respond. Try again."
    if exc.code == "cancelled":
        return "That was stopped."
    return "I can't reach the model right now. Try again in a moment."


# The three shapes the Chief of Staff's "not connected" card knows how to guide someone through:
# a CLI sign-in (claude/codex), a missing/rejected key, or nothing actionable but "try again".
MODEL_ERROR_SIGN_IN_CODES = {"cli_not_logged_in", "cli_missing"}
MODEL_ERROR_KEY_CODES = {"no_key", "provider_error"}


# The gateway's route.provider ids (alpha.models.gateway.ModelGateway) aren't the Settings ->
# Models account ids (alpha.models.accounts.PROVIDERS) - map so the "not connected" card can
# point at the right row (and, for a key, call saveModelKey with an id Core recognizes).
ROUTE_PROVIDER_TO_ACCOUNT = {
    "anthropic-claude-code-cli": "claude",
    "openai-codex-cli": "chatgpt",
    "openai-api": "chatgpt_api",
    "openrouter": "openrouter",
    "xai-grok": "grok",
}


def model_error_kind(exc: InferenceError) -> str:
    text = str(exc).lower()
    if "subscription" in text and "disabled" in text:
        return "key"
    if exc.code in MODEL_ERROR_SIGN_IN_CODES or "not logged in" in text:
        return "sign_in"
    if exc.code in MODEL_ERROR_KEY_CODES:
        return "key"
    return "generic"


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
        return f"read {app_name or 'a project'}; nothing was changed"
    used = [str(o.get("skill")) for o in observations if o.get("step") == "skill"]
    if used:
        return f"used the skill {', '.join(used)}; nothing was changed"
    allowed = [o for o in observations if o.get("step") == "allow" and o.get("state") == "allowed"]
    if allowed and not runs:
        site = allowed[-1].get("site")
        return f"allowed {app_name or 'the project'} to read {site} through the sign-in"
    fixes = [o for o in observations if o.get("step") == "fix"]
    if fixes:
        state = str(fixes[-1].get("state") or "")
        where = f" in {app_name}" if app_name else ""
        return (
            f"fixed the project's code{where} and ran the action again"
            if state == "fixed"
            else f"looked into a failure{where}: {state.replace('_', ' ') or 'no fix'}"
        )
    if kind == "open":
        return f"opened {app_name or 'a project'} in Alpha's window"
    if kind in ("build", "change"):
        return f"started a request to {'change ' + app_name if kind == 'change' and app_name else 'make something new'}"
    if kind == "continue":
        return "answered the open request above"
    return "nothing was done; Alpha only replied"


def access_facts(access: list[dict[str, Any]]) -> list[str]:
    """Why a module got a site's sign-in page, in words the loop can act on."""
    lines = []
    for entry in access:
        head = (
            f"{entry['name']} read {entry['site']} {entry['reads']} time(s) lately and got "
            f"the sign-in page {entry['walled']} time(s)."
        )
        if entry["connected"] and not entry["allowed"]:
            lines.append(
                f"{head} The person IS signed in to {entry['site']} in Alpha's browser; this "
                "project has simply not been allowed to read through that sign-in yet. Say so "
                "and ask whether to allow it (an allow step once they say yes), then run the "
                "action again. Do not tell them to sign in again."
            )
        elif not entry["connected"]:
            lines.append(
                f"{head} {entry['site']} is not signed in in Alpha's browser. They sign in "
                "from Connections (Sign in to a site): Alpha opens its own browser window for "
                "it; being signed in in Safari or Chrome does not count."
            )
        elif entry["last_walled"]:
            lines.append(
                f"{head} The project is allowed and the person signed in earlier, so the "
                f"sign-in to {entry['site']} has probably lapsed; they can sign in again from "
                "Connections."
            )
    return lines


@dataclass
class _Work:
    """One message being worked through: what the steps decided so far and what they saw."""

    turn_id: str
    session_id: str
    text: str
    names: dict[str, str]
    deadline: float
    kind: str = "answer"
    app_id: str | None = None
    action_id: str | None = None
    run_id: str | None = None
    conversation_id: str | None = None
    opened: dict[str, Any] | None = None
    reply: str = ""
    # Set when a model call itself failed (see model_error_kind): drives the Chief of Staff's
    # "not connected" card instead of a plain text reply. None on every ordinary turn.
    model_error: dict[str, Any] | None = None
    observations: list[dict[str, Any]] = field(default_factory=list)
    # Sites a module could not read for want of the person's yes (see BrowserService.access).
    access: list[dict[str, Any]] = field(default_factory=list)
    # What was attached to this message: prompt text, and the summary recorded on the turn.
    attachments_context: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)
    # This turn's governance stance (see ACCESS_MODES) and, when the + menu overrode the model,
    # the Settings -> Models account id to route this call through instead of the stage default.
    access_mode: str = DEFAULT_ACCESS_MODE
    model_override: str | None = None
    model_name_override: str | None = None
    # Sources for this turn's project, keyed by app_id, so a "run" step's gate can see whether the
    # target module declares the http or browser (egress) capability.
    sources: dict[str, AppSource] = field(default_factory=dict)
    # Set instead of running when a step needed the person's yes first; carried onto the turn's
    # detail so the next message (an affirmative) can run exactly this, unchanged.
    pending_run: dict[str, Any] | None = None

    def observe(self, observation: dict[str, Any]) -> None:
        self.observations.append(observation)

    def within_time(self) -> bool:
        """False once the budget is spent: the rest is not done, and the reply says so."""
        if time.monotonic() <= self.deadline:
            return True
        self.observe({"note": "out of time; the rest was not done"})
        self.reply = ""
        return False


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
        sessions: SessionService,
        default_route: str,
        timezone: str = "UTC",
        creations: Any | None = None,
        context: Callable[..., str] | None = None,
        skills: Any | None = None,
        projects: Any | None = None,
        repair: Any | None = None,
        browser: Any | None = None,
        run_lookup: Callable[[str], Run] | None = None,
        today: Callable[[], str] | None = None,
        preferences: Any | None = None,
    ) -> None:
        self._store = store
        self._gateway = gateway
        self._inference = inference
        self._registry = registry
        self._runs = runs
        self._records = records
        self._assistant = assistant
        self._sessions = sessions
        self._creations = creations
        self._context = context
        self._skills = skills
        self._projects = projects
        self._repair = repair
        self._browser = browser
        # Settings -> Access's default stance for a session that hasn't picked its own (see
        # `access.mode` in alpha.models.preferences); None in tests keeps today's DEFAULT_ACCESS_MODE.
        self._preferences = preferences
        self._default_route = default_route
        self._timezone = timezone
        self._run_lookup = run_lookup or store.get_run
        self._today = today or (lambda: utc_now().date().isoformat())
        self._threads: dict[str, threading.Thread] = {}
        self._results: dict[str, ActTurn] = {}
        self._lock = threading.Lock()
        sessions.bind_outcome(self.outcome_for)

    # ----- public ------------------------------------------------------------------------

    def recent(self, limit: int = 10, *, session_id: str | None = None) -> list[ActTurn]:
        """The last turns of a session (the avatar's Quick asks by default), as the avatar
        shows them: each person's message with what Alpha did and said."""
        session_id = session_id or self._sessions.quick_asks().session_id
        turns = self._sessions.get(session_id, window=limit * 2).turns
        found: list[ActTurn] = []
        pending: SessionTurn | None = None
        for turn in turns:
            if turn.role == "user":
                pending = turn
                continue
            found.append(self._as_act_turn(session_id, pending, turn))
            pending = None
        return found[-limit:]

    def act(
        self,
        text: str,
        *,
        context_app_id: str | None = None,
        attachments: list[AttachmentIn] | None = None,
        access_mode: str | None = None,
        model: dict[str, str] | None = None,
    ) -> ActTurn:
        """The avatar's way in: one message to the Quick asks session, answered when done."""
        session = self._sessions.quick_asks()
        turn = self.send(
            session.session_id,
            text,
            wait=True,
            context_app_id=context_app_id,
            attachments=attachments,
            access_mode=access_mode,
            model=model,
        )
        if turn is None:  # the budget ran out before the loop finished; the session has the rest
            raise OperationFailed(
                "timed_out", "Alpha is still working on that; see the session", {}
            )
        return turn

    def send(
        self,
        session_id: str,
        text: str,
        *,
        wait: bool = False,
        context_app_id: str | None = None,
        attachments: list[AttachmentIn] | None = None,
        access_mode: str | None = None,
        model: dict[str, str] | None = None,
    ) -> ActTurn | None:
        """Record the person's message and work it through in a thread. With `wait`, block
        (bounded) and return the outcome; otherwise return None at once and let the session
        be polled (its state is `thinking` meanwhile).

        `access_mode` (see ACCESS_MODES) and `model` ({"provider": ..., "model": ...}, provider an
        account id from Settings -> Models) are this one message's + menu choices; unset falls
        back to the person's Settings -> Access default, then DEFAULT_ACCESS_MODE."""
        clean = text.strip()
        attachments = attachments or []
        if not clean:
            raise OperationFailed("invalid_input", "say something first", {})
        if access_mode is not None and access_mode not in ACCESS_MODES:
            raise OperationFailed("invalid_input", f"unknown access mode {access_mode!r}", {})
        self._sessions.begin_turn(session_id)
        try:
            user_turn = self._sessions.append(
                session_id,
                "user",
                clean,
                detail={"attachments": attachment_summaries(attachments)} if attachments else None,
            )
        except Exception:
            self._sessions.set_state(session_id, "idle")
            raise
        thread = threading.Thread(
            target=self._work_quietly,
            args=(session_id, user_turn, context_app_id, attachments, access_mode, model),
            name=f"session-turn-{session_id[-6:]}",
            daemon=True,
        )
        with self._lock:
            self._threads[session_id] = thread
        thread.start()
        if not wait:
            return None
        thread.join(TIME_BUDGET_SECONDS + WAIT_GRACE_SECONDS)
        with self._lock:
            return self._results.pop(session_id, None)

    def outcome_for(self, turn: SessionTurn) -> str | None:
        """One line of truth about a past turn of Alpha's, computed when read so a card's
        state (a conversation that has since been built) is current."""
        detail = turn.detail or {}
        if turn.kind != "work":
            return None if turn.role != "alpha" else "nothing was done; Alpha only replied"
        kind = str(detail.get("kind") or "answer")
        app_name = self._app_name(detail.get("app_id"))
        line = outcome_line(kind, detail, app_name)
        if turn.conversation_id and kind in ("build", "change", "continue"):
            line += f"; it is now: {self._conversation_state(turn.conversation_id)}"
        return line

    # ----- one message ---------------------------------------------------------------------

    def _work_quietly(
        self,
        session_id: str,
        user_turn: SessionTurn,
        context_app_id: str | None,
        attachments: list[AttachmentIn] | None = None,
        access_mode: str | None = None,
        model: dict[str, str] | None = None,
    ) -> None:
        try:
            result = self._work(
                session_id, user_turn, context_app_id, attachments or [], access_mode, model
            )
        except Exception:  # never leave a session stuck in thinking
            log.exception("session turn crashed for %s", session_id)
            result = self._finish(
                _Work(
                    turn_id=new_id("turn"),
                    session_id=session_id,
                    text=user_turn.text,
                    names={},
                    deadline=0,
                    reply="Something went wrong inside Alpha while working on that. Try again?",
                )
            )
        finally:
            self._sessions.set_state(session_id, "idle")
        with self._lock:
            self._results[session_id] = result
            self._threads.pop(session_id, None)
        try:
            self._sessions.after_turn(session_id)
        except Exception:
            log.exception("could not start compaction for %s", session_id)

    def _default_access_mode(self) -> str:
        if self._preferences is None:
            return DEFAULT_ACCESS_MODE
        try:
            chosen = str(self._preferences.get("access.mode"))
        except Exception:
            return DEFAULT_ACCESS_MODE
        return chosen if chosen in ACCESS_MODES else DEFAULT_ACCESS_MODE

    def _pending_run(self, session_id: str) -> dict[str, Any] | None:
        """A run this session is waiting on the person's yes for (see `needs_approval`), if any."""
        latest = self._sessions.latest_work(session_id)
        if latest is None or not latest.detail:
            return None
        pending = latest.detail.get("pending_run")
        return pending if isinstance(pending, dict) else None

    def _work(
        self,
        session_id: str,
        user_turn: SessionTurn,
        context_app_id: str | None,
        attachments: list[AttachmentIn],
        access_mode: str | None = None,
        model: dict[str, str] | None = None,
    ) -> ActTurn:
        session = self._sessions.get(session_id, window=1)
        sources = self._sources(session.project_id)
        names = {app_id: source.name for app_id, source in sources}
        work = _Work(
            turn_id=new_id("turn"),
            session_id=session_id,
            text=user_turn.text,
            names=names,
            deadline=time.monotonic() + TIME_BUDGET_SECONDS,
            attachments=attachment_summaries(attachments),
            access_mode=access_mode if access_mode in ACCESS_MODES else self._default_access_mode(),
            model_override=(model or {}).get("provider") or None,
            model_name_override=(model or {}).get("model") or None,
            sources={app_id: source for app_id, source in sources},
        )
        log.info("act turn %s access_mode=%s", work.turn_id, work.access_mode)
        # An approved pending run (the offer's "Approve and run" sends the person's plain yes)
        # runs at once, exactly as stored, with no new model call and no re-gating.
        pending = self._pending_run(session_id)
        if pending is not None and _AFFIRM_RE.match(work.text.strip()):
            work.access_mode = "full"  # this one instance only; already approved by the person
            if self._step_run(work, str(pending["app_id"]), list(pending["runs"])):
                pass  # a single stored run never re-enters the step loop
            return self._finish(work)
        waiting = self._waiting_conversation(session_id)
        if waiting is not None:
            return self._continue_conversation(work, waiting)
        focus = context_app_id or session.focus_app_id
        work.access = self._access(sources)
        prompt_parts = dict(
            catalogue=catalogue_text(sources),
            facts=self._facts(names, session_id) + access_facts(work.access),
            memory=self._memory(session_id, work.text),
            context_app=names.get(focus or "") if focus else None,
            known=self._known(work.text, focus, session.project_id),
            skills=self._skills.catalogue_text() if self._skills is not None else "",
            project=self._project_text(session.project_id),
            attachments=self._attachments_context(attachments),
        )
        try:
            route = self._gateway.route(
                self._default_route,
                stage="assistant",
                account_override=work.model_override,
                model_override=work.model_name_override,
            )
        except RouteUnavailable as exc:
            work.model_error = {"kind": "generic", "provider": work.model_override or "unknown"}
            work.reply = (
                f"I can't reach that model right now ({exc}). Pick a connected one from the + "
                "menu or Settings → Models."
            )
            return self._finish(work)
        for _step in range(MAX_STEPS):
            output = self._decide(route, work, prompt_parts)
            if not self._apply(work, output):
                break
        if not work.reply:
            work.reply = (
                summary_reply(work.observations)
                if work.observations
                else "I couldn't work that out just now. Try again?"
            )
        return self._finish(work)

    def _waiting_conversation(self, session_id: str) -> str | None:
        """The session's latest card, when it is a conversation waiting for the person."""
        latest = self._sessions.latest_work(session_id)
        if latest is None or not latest.conversation_id:
            return None
        try:
            record = self._assistant.get(latest.conversation_id)
        except Exception:
            return None
        return (
            latest.conversation_id if getattr(record, "state", "") in CONVERSATION_WAITING else None
        )

    def _continue_conversation(self, work: _Work, conversation_id: str) -> ActTurn:
        work.kind, work.conversation_id = "continue", conversation_id
        try:
            self._assistant.reply(conversation_id, text=work.text)
            work.reply = "Passed on to the request above."
        except Exception as exc:
            log.warning("could not continue %s: %s", conversation_id, exc)
            work.reply = f"I couldn't pass that on: {exc}"
            work.kind = "answer"
        work.opened = {"conversation_id": conversation_id, "session_id": work.session_id}
        return self._finish(work)

    def _attachments_context(self, attachments: list[AttachmentIn]) -> str:
        try:
            return build_context(attachments)
        except Exception:
            log.exception("attachment context failed; the turn goes on without it")
            return ""

    def _memory(self, session_id: str, text: str) -> str:
        try:
            return self._sessions.memory_text(session_id, text)
        except Exception:
            log.exception("session memory failed; the turn goes on without it")
            return ""

    def _project_text(self, project_id: str | None) -> str:
        if not project_id or self._projects is None:
            return ""
        try:
            project = self._projects.get(project_id)
        except Exception:
            return ""
        lines = [f"{project.name}" + (f": {project.goal}" if project.goal else "")]
        if project.summary:
            lines.append(f"Alpha's notes on it: {project.summary}")
        return "\n".join(lines)

    def _known(self, text: str, app_id: str | None, project_id: str | None) -> str:
        if self._context is None:
            return ""
        try:
            return self._context(text, app_id=app_id, project_id=project_id)
        except TypeError:
            try:
                return self._context(text)
            except Exception:
                return ""
        except Exception:
            log.exception("context pack failed; the sentence goes on without it")
            return ""

    def _decide(self, route: Any, work: _Work, parts: dict[str, Any]) -> dict[str, Any]:
        """One model call: the next step, or a grounded ending when the call itself fails."""
        try:
            decided = self._inference.call(
                route,
                system=STEP_SYSTEM,
                prompt=step_prompt(
                    work.text,
                    parts["catalogue"],
                    parts["facts"],
                    parts["memory"],
                    work.observations,
                    self._today(),
                    parts["context_app"],
                    known=parts["known"],
                    skills=parts["skills"],
                    project=parts["project"],
                    attachments=parts["attachments"],
                ),
                schema=step_schema(),
                scope_kind="act",
                scope_ref=work.turn_id,
                fake=fake_act if route.route_id == "fake" else None,
            )
            return decided.output if isinstance(decided.output, dict) else {}
        except InferenceError as exc:
            log.warning("act step failed: %s", exc)
            return {
                "kind": "done" if work.observations else "answer",
                "reply": model_error_reply(exc),
                "model_error": {
                    "kind": model_error_kind(exc),
                    "provider": ROUTE_PROVIDER_TO_ACCOUNT.get(route.provider, route.provider),
                },
            }

    def _apply(self, work: _Work, output: dict[str, Any]) -> bool:
        """Carry out the decided step. True to decide again; False when the message is done."""
        step_kind = str(output.get("kind") or "answer")
        step_app = output.get("app_id") if output.get("app_id") in work.names else None
        step_reply = str(output.get("reply") or "").strip()
        if step_kind == "run" and step_app and isinstance(output.get("runs"), list):
            return self._step_run(work, step_app, output["runs"])
        if step_kind == "query" and step_app:
            work.app_id = step_app
            work.kind = work.kind if work.kind == "run" else "query"
            work.observe(
                self._read(step_app, work.names[step_app], str(output.get("view_id") or ""))
            )
            return True
        if step_kind == "skill" and output.get("skill_id") and self._skills is not None:
            work.kind = work.kind if work.kind == "run" else "skill"
            work.observe(self._use_skill(str(output["skill_id"]), output.get("inputs")))
            return work.within_time()
        if step_kind == "open" and step_app:
            work.kind, work.app_id = "open", step_app
            work.opened = {"app_id": step_app, "tab_id": output.get("tab_id")}
            work.reply = step_reply or f"Opening {work.names[step_app]}."
            return False
        if step_kind == "allow" and step_app:
            work.kind = work.kind if work.kind == "run" else "allow"
            work.app_id = step_app
            work.observe(self._allow(work, step_app, str(output.get("site") or "")))
            return work.within_time()
        if step_kind == "fix" and step_app:
            work.kind = work.kind if work.kind == "run" else "fix"
            work.app_id = step_app
            work.observe(self._fix(step_app, work.names[step_app], output.get("run_id")))
            return work.within_time()
        if step_kind in ("build", "change"):
            self._step_start(work, step_kind, step_app)
            return False
        # done / answer / anything unknown: the reply, grounded on what was observed.
        if not work.observations:
            work.kind = "answer"
        work.reply = step_reply
        if isinstance(output.get("model_error"), dict):
            work.model_error = output["model_error"]
        return False

    def _access(self, sources: list[tuple[str, AppSource]]) -> list[dict[str, Any]]:
        if self._browser is None:
            return []
        found: list[dict[str, Any]] = []
        for app_id, source in sources:
            if "browser" not in source.capabilities:
                continue
            try:
                found.extend(self._browser.access(app_id, source.name))
            except Exception:
                log.debug("could not read browser access of %s", app_id, exc_info=True)
        return found

    def _allow(self, work: _Work, app_id: str, site: str) -> dict[str, Any]:
        """Let the module read a site through the person's sign-in, when that is what stood
        in its way and the person is signed in there."""
        name = work.names[app_id]
        entry = next(
            (
                e
                for e in work.access
                if e["app_id"] == app_id and (not site or e["site"] == site) and not e["allowed"]
            ),
            None,
        )
        if entry is None or self._browser is None:
            return {
                "step": "allow",
                "module": name,
                "state": "nothing",
                "message": f"{name} is not waiting on access to a site.",
            }
        if not entry["connected"]:
            return {
                "step": "allow",
                "module": name,
                "site": entry["site"],
                "state": "not_signed_in",
                "message": f"You are not signed in to {entry['site']} in Alpha's browser yet. "
                "Sign in from Connections, then ask again.",
            }
        try:
            self._browser.allow(app_id, entry["site"])
        except OperationFailed as exc:
            return {"step": "allow", "module": name, "state": "failed", "message": exc.message}
        entry["allowed"] = True
        return {
            "step": "allow",
            "module": name,
            "site": entry["site"],
            "state": "allowed",
            "message": f"{name} may now read {entry['site']} through your sign-in.",
        }

    def _fix(self, app_id: str, app_name: str, run_id: Any) -> dict[str, Any]:
        """Repair the module's code for one failed run and run it again (blocks, bounded)."""
        if self._repair is None:
            return {
                "step": "fix",
                "module": app_name,
                "state": "unavailable",
                "message": "Fixing is not available on this host.",
            }
        chosen = str(run_id or "")
        if not chosen:
            recent = [
                f for f in self._repair.recent(app_id, limit=3) if f.get("kind") == "module_code"
            ]
            chosen = str(recent[0]["run_id"]) if recent else ""
        if not chosen:
            return {
                "step": "fix",
                "module": app_name,
                "state": "nothing",
                "message": f"No recent failure of {app_name} is in its own code, so there is nothing to fix.",
            }
        try:
            result = self._repair.repair(chosen)
        except Exception as exc:
            log.exception("fix step failed")
            return {
                "step": "fix",
                "module": app_name,
                "state": "error",
                "message": f"The fix could not run: {exc}",
            }
        return {"step": "fix", "module": app_name, "run_id": chosen, **result}

    def _step_run(self, work: _Work, app_id: str, runs: list[Any]) -> bool:
        work.app_id, work.kind = app_id, "run"
        source = work.sources.get(app_id)
        egress = bool(source and ("http" in source.capabilities or "browser" in source.capabilities))
        gated = needs_approval(work.access_mode, egress, runs)
        log.info(
            "act run app=%s access_mode=%s egress=%s gated=%s", app_id, work.access_mode, egress, gated
        )
        if gated:
            name = work.names[app_id]
            work.pending_run = {"app_id": app_id, "runs": runs}
            work.reply = (
                f"{name} wants to use the internet to do that — I need your OK first."
                if egress
                else f"{name} wants to do something that looks hard to undo — I need your OK first."
            )
            work.observe(
                {"step": "run", "module": name, "state": "needs_approval", "message": work.reply}
            )
            return False
        results = self._run_batch(app_id, runs, work.deadline)
        if results and work.action_id is None:
            work.action_id = str(results[0].get("action"))
            work.run_id = next((r.get("run_id") for r in results if r.get("run_id")), None)
        work.observe({"step": "run", "module": work.names[app_id], "results": results})
        return work.within_time()

    def _step_start(self, work: _Work, step_kind: str, app_id: str | None) -> None:
        """Hand the message to the assistant as something new to make, or a change; the
        conversation becomes a card in this session."""
        work.kind = step_kind
        work.app_id = app_id if step_kind == "change" else None
        try:
            record = self._assistant.start(
                work.text, change_of=work.app_id, session_id=work.session_id
            )
            work.conversation_id = record.conversation_id
            work.opened = {"conversation_id": work.conversation_id, "session_id": work.session_id}
            work.reply = (
                f"I've started a change to {work.names[work.app_id]}; the card here shows what happens next."
                if work.app_id
                else "I've started making that; the card here shows what happens next."
            )
        except Exception as exc:  # the conversation could not start; say so
            log.exception("act could not start a conversation")
            work.reply, work.kind = f"I couldn't start that: {exc}", "answer"

    def _finish(self, work: _Work) -> ActTurn:
        """Record Alpha's turn in the session and shape it for the avatar."""
        detail = {
            "kind": work.kind,
            "app_id": work.app_id,
            "action_id": work.action_id,
            "run_id": work.run_id,
            "conversation_id": work.conversation_id,
            "open": work.opened,
            "observations": work.observations,
            "attachments": work.attachments,
        }
        if work.model_error is not None:
            detail["model_error"] = work.model_error
        if work.pending_run is not None:
            detail["pending_run"] = work.pending_run
        offer = self._offer(work)
        if offer is not None:
            detail["offer"] = offer
        turn = self._sessions.append(
            work.session_id,
            "alpha",
            work.reply or "(no reply)",
            kind="work" if work.kind != "answer" else "text",
            detail=detail,
            turn_id=work.turn_id,
        )
        app_name = work.names.get(work.app_id or "")
        return ActTurn(
            turn_id=turn.turn_id,
            session_id=work.session_id,
            text=work.text,
            kind=work.kind,
            app_id=work.app_id,
            app_name=app_name,
            action_id=work.action_id,
            run_id=work.run_id,
            conversation_id=work.conversation_id,
            open=work.opened,
            reply=work.reply,
            created_at=turn.created_at,
            outcome=outcome_line(work.kind, detail, app_name),
            attachments=work.attachments or None,
            model_error=work.model_error,
        )

    def _offer(self, work: _Work) -> dict[str, Any] | None:
        """A one-click yes for the thing that stands in the way: a module the person is
        signed in for but has not yet allowed, or a run gated on their approval (see
        `needs_approval`). The click sends their yes as a plain message."""
        if work.pending_run is not None:
            name = work.names.get(str(work.pending_run["app_id"]), "It")
            return {
                "kind": "run_confirm",
                "app_id": work.pending_run["app_id"],
                "label": "Approve and run",
                "say": f"Yes, go ahead and let {name} do that.",
            }
        waiting = [e for e in work.access if e["connected"] and not e["allowed"]]
        if work.app_id:
            waiting = [e for e in waiting if e["app_id"] == work.app_id] or waiting
        if not waiting:
            return None
        entry = waiting[0]
        return {
            "kind": "allow_site",
            "app_id": entry["app_id"],
            "site": entry["site"],
            "label": f"Allow {entry['site']} and try again",
            "say": f"Yes, allow {entry['name']} to read {entry['site']} through my sign-in, "
            "then try again.",
        }

    def _as_act_turn(self, session_id: str, said: SessionTurn | None, turn: SessionTurn) -> ActTurn:
        detail = turn.detail or {}
        return ActTurn(
            turn_id=turn.turn_id,
            session_id=session_id,
            text=said.text if said else "",
            kind=str(detail.get("kind") or "answer"),
            app_id=detail.get("app_id"),
            app_name=self._app_name(detail.get("app_id")),
            action_id=detail.get("action_id"),
            run_id=detail.get("run_id"),
            conversation_id=turn.conversation_id,
            open=turn.open,
            reply=turn.text,
            created_at=turn.created_at,
            outcome=turn.outcome,
            attachments=said.attachments if said else None,
            model_error=detail.get("model_error"),
        )

    # ----- steps --------------------------------------------------------------------------

    def _sources(self, project_id: str | None = None) -> list[tuple[str, AppSource]]:
        """Active modules, the project's own first so the catalogue leads with them."""
        found: list[tuple[str, AppSource]] = []
        for entry in self._registry.list_apps():
            if entry.get("state") != "active":
                continue
            try:
                found.append((entry["app_id"], self._registry.current(entry["app_id"]).source))
            except OperationFailed:
                continue
        if project_id and self._projects is not None:
            try:
                mine = set(self._projects.modules_in(project_id))
            except Exception:
                mine = set()
            found.sort(key=lambda item: item[0] not in mine)
        return found

    def _app_name(self, app_id: Any) -> str | None:
        if not app_id:
            return None
        try:
            return str(self._registry.current(str(app_id)).source.name)
        except Exception:
            return None

    def _facts(self, names: dict[str, str], session_id: str | None = None) -> list[str]:
        """What is happening right now, from Core's own records."""
        facts: list[str] = []
        try:
            for run in self._store.list_runs_in_states(ACTIVE_RUN_STATES):
                owner = run.owner.model_dump() if hasattr(run.owner, "model_dump") else {}
                app = names.get(str(owner.get("app_id")), str(owner.get("app_id") or "a project"))
                facts.append(f"running now: {owner.get('action_id')} in {app} ({run.state.value})")
        except Exception:
            log.debug("could not list running runs", exc_info=True)
        if self._creations is not None:
            try:
                for creation in self._creations.list_recent(10):
                    if creation.state in ("active", "failed", "cancelled"):
                        continue
                    what = names.get(creation.change_of or "", creation.app_name or "a project")
                    facts.append(f"being made right now: {what} ({creation.label.lower()})")
            except Exception:
                log.debug("could not list creations", exc_info=True)
        if self._repair is not None:
            try:
                facts.extend(self._repair.facts(list(names)[:20]))
            except Exception:
                log.debug("could not list failures", exc_info=True)
        if session_id:
            for turn in self._sessions.window(session_id, 8):
                detail = turn.detail or {}
                if turn.conversation_id and detail.get("kind") in ("build", "change"):
                    state = self._conversation_state(turn.conversation_id)
                    facts.append(f"the request started earlier in this session is now: {state}")
        return facts

    def _conversation_state(self, conversation_id: str) -> str:
        try:
            record = self._assistant.get(conversation_id)
        except Exception:
            return "unknown"
        state = str(getattr(record, "state", "unknown"))
        words = {
            "thinking": "Alpha is still reading it",
            "researching": "Alpha is looking around before proposing a shape",
            "proposed": "waiting for the person to pick one of the proposed shapes",
            "waiting_for_user": "waiting for the person's answers",
            "briefed": "planned; a build or change follows",
            "answered": "answered; nothing is being built",
            "failed": "it failed; the person can try again",
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


def _compact(output: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(output, default=str)
    if len(text) <= 600:
        return output
    return {"summary": text[:600] + "…"}
