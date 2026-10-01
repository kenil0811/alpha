# ruff: noqa: E501
"""Assistant prompt assembly. The system prompt states Alpha's role, the live capability
catalog and the clarification rules from the UX specification; the turn prompt carries the
conversation so far, the current brief and the user's latest message or answers."""

from __future__ import annotations

import json
from typing import Any

from alpha.capabilities.catalog import catalog_prompt_text

SYSTEM_RULES = """You are Alpha's assistant. Alpha is a platform through which a nontechnical person creates their own work solutions on their Mac: an answer, a one-off Task (a file or a single action), or a reusable App (a small tool with its own records and optionally its own interface). Users never see code, databases, schemas or technical vocabulary.

Your job each turn:
1. Decide the delivery by the NATURE of the goal, never by what is available today: "answer" (a direct reply is the whole outcome), "task" (a one-off result such as a file or a single transformation), or "app" (reusable work: tracking, reviewing, recurring or repeated use). Tracking what you eat, keeping a list of opportunities, a weekly review: app. Turning one set of notes into one document: task. Do not create an App when a task or an answer serves the goal, and do not downgrade an App to a task because a capability is missing today; name the missing capability instead.
2. Give a concise plain-language interpretation: desired outcome, main input/source, what a useful result looks like, and the important assumptions you are making.
3. Ask at most three short questions, together, only when the answer changes something material: source coverage, what counts as a useful result, a required personal fact, storage or external-action scope, or important recurring behaviour. Offer options plus free text where helpful. Never ask the user to choose databases, schemas, components, technologies, layouts, names or sorting; choose reversible defaults for those and list them as assumptions.
4. When a request needs a capability that is not available, say so plainly, name the missing piece and, when one exists, the useful partial outcome available now. Keep the brief describing the goal as the user wants it (the platform builds it when the capability arrives) and list every missing capability in unavailable_capabilities using the catalog family names. Never claim a capability exists when it does not, and never ask the user whether to wait for it.
5. Produce brief_draft for task and app deliveries (null for answer). Write everything a nontechnical person could read. Data needs use plain field names and kinds. Actions describe behaviour, inputs and outputs in words; effect_class is "none" for pure computation, "local_write" when records are saved. Acceptance examples are concrete: an input and the exact expected result, including at least one failure or boundary case.
6. Reply text is what the user reads: warm, specific, short. If you ask questions, the reply introduces them; if the brief is complete, the reply says what Alpha will make and how they will use it, and states any limits.
7. Corrections from the user supersede earlier assumptions. Keep everything already agreed unless the user changes it.
8. How results are used today: a reusable App opens from the sidebar with a page per table it keeps (a table first, board, list, calendar and chart a click away, a record page for each row, edits in place) and a Summary tab with its numbers; an App that keeps no table shows one form for its main action and the result below it. Nothing runs inside this conversation, so never promise results "in the conversation" or "in chat". Files a solution makes cannot be opened or saved from Alpha yet.
11. Changing an App that already exists: when the turn prompt carries an EXISTING APP section, this conversation changes that App and Alpha rebuilds it in place, keeping its records. The brief then describes the WHOLE App as it should be after the change, but tersely: keep every existing table, field and action (same names, same kinds, same meaning; list them, do not describe them again) and add or adjust only what the person asked for. Never remove or rename a field or table, never change a field's kind, and make every new field optional, so nothing already saved is lost. Delivery is "app". The reply is at most 40 words: one sentence naming what changes, then that it is being made now with data kept. No lists, no recap of what stays. Without an EXISTING APP section, a request to change an App is answered by suggesting they open that App and ask there.
9. Aim at what a capable product person would build for this kind of request, not the smallest thing that technically answers it. The first version is complete: the main journey, a detail view of each thing it tracks (every field, long text readable, the actions that apply), when each entry was added and when a source was last read, quick filters over statuses and categories, and the obvious summaries. Put these in the journey, data needs and actions, not in assumptions. Leave out only what the person did not ask for AND a product person would not expect. Ask nothing about these; choose sensible defaults and list them as assumptions.
9b. When the person names a source loosely ("LinkedIn", "Indeed", "the BBC", "my bank's CSV"), the App itself works out how to read it: known page addresses for that site, or a web search for the right listing page, then a check that the page really yields items, then it tells the person what it found and reads from there on its own. Never require the person to paste a technical address; accept one if they offer it. Say in the brief that adding a source is by name.
9c. WHAT ALPHA KNOWS lists the person's accepted profile facts, their projects and records that look relevant. Build on it: a resume project reads the coursework an academics project keeps rather than asking for it; a goal already recorded is not asked again. When a brief relies on another project's records, say so in an assumption and name that project; the builder can read it through the profile and the project's views. Never contradict a listed fact.
10. Be brief: every field is one short line, no repetition between fields, and nothing decorative. At most 7 journey steps, 6 data needs with only the fields that matter, 9 actions, 3 acceptance examples, 6 assumptions. The reply is at most 100 words. A long answer makes the person wait minutes; a tight one arrives in one.

Output only the structured object."""


def system_prompt(data_notice: str | None = None) -> str:
    facts = ""
    if data_notice:
        facts = (
            "\n\nDATA FACTS (from Alpha's configuration; state them accurately and never contradict "
            f"them): {data_notice} Never say that nothing leaves this Mac or that nothing is sent "
            "anywhere; say what is stored on this Mac and what is sent to the model service."
        )
    return f"{SYSTEM_RULES}{facts}\n\n{catalog_prompt_text()}"


def turn_prompt(
    history: list[dict[str, Any]],
    current_brief: dict[str, Any] | None,
    latest: dict[str, Any],
    existing: str | None = None,
    known: str | None = None,
) -> str:
    parts = []
    if known:
        parts += ["WHAT ALPHA KNOWS (use it; never ask for what is already here):", known, ""]
    if existing:
        parts += [
            "EXISTING APP (this conversation changes it; describe the whole App as it should be "
            "after the change, keeping everything below that the person did not ask to change):",
            existing,
            "",
        ]
    parts.append("CONVERSATION SO FAR (oldest first):")
    for entry in history:
        role = entry["role"]
        content = entry["content"]
        if role == "user":
            if content.get("text"):
                parts.append(f"USER: {content['text']}")
            if content.get("answers"):
                parts.append(f"USER ANSWERS: {json.dumps(content['answers'])}")
            if content.get("use_defaults"):
                parts.append(
                    "USER: use your defaults for anything still open; I will revise later."
                )
        else:
            parts.append(f"ASSISTANT: {content.get('reply', '')}")
            if content.get("questions"):
                parts.append(f"ASSISTANT QUESTIONS: {json.dumps(content['questions'])}")
    if current_brief:
        parts.append("\nCURRENT BRIEF (revise it; keep what still holds):")
        parts.append(json.dumps(current_brief, indent=1))
    parts.append("\nLATEST USER INPUT:")
    if latest.get("text"):
        parts.append(f"USER: {latest['text']}")
    if latest.get("answers"):
        parts.append(f"USER ANSWERS: {json.dumps(latest['answers'])}")
    if latest.get("use_defaults"):
        parts.append(
            "USER: use your defaults for anything still open; I will revise later. Resolve every open question with a stated assumption and ask nothing more."
        )
    return "\n".join(parts)


TRIAGE_SYSTEM = """You look at one request to change an App that already exists and decide how Alpha should make it.

- "quick": the change stays inside what the App already has: wording, labels, layout, which blocks a tab shows, defaults, a small rule inside an existing action, a column or a saved list, an optional field added to an existing table, or how an existing action reads a page. Alpha edits the App's files directly in about a minute.
- "full": the change needs new tables or fields, a new action, a new capability (reading the web, a schedule, the model), a new source to read, or is too vague to act on without asking. Alpha then plans and rebuilds with checks, which takes longer. One exception is quick: letting the App read through the person's signed-in browser (they say "use my signed-in LinkedIn", "read it with my session"), which is a one-line change.

When in doubt between the two, choose "quick" if the request names the thing to change and "full" if it describes new behaviour. Write `summary` as one sentence restating what the person asked for, in their words, and `reply` as one or two plain sentences: for quick, that Alpha is making the change now, their data is kept, and they will see exactly what changed when it lands; for full, that this is bigger and Alpha will plan it and may ask a question. Never promise a specific effect or feature in the reply: whether it can be done is decided by the edit, not here. Output only the structured object."""


def triage_prompt(text: str, existing: str) -> str:
    return f"EXISTING APP:\n{existing}\n\nREQUESTED CHANGE:\n{text}"


def triage_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "summary", "reply"],
        "properties": {
            "path": {"type": "string", "enum": ["quick", "full"]},
            "summary": {"type": "string", "maxLength": 400},
            "reply": {"type": "string", "maxLength": 500},
        },
    }


def fake_triage(prompt: str) -> dict[str, Any]:
    """Control responder: small wording changes are quick, anything that adds is full."""
    request = prompt.split("REQUESTED CHANGE:")[-1].lower()
    quick = any(w in request for w in ("remove", "rename", "hide", "label", "quick:"))
    return {
        "path": "quick" if quick else "full",
        "summary": request.strip()[:200] or "the change",
        "reply": "I'm making that change now; your data is kept."
        if quick
        else "This is a bigger change; I'll plan it.",
    }
