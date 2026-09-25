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
1. Decide the delivery: "answer" (a direct reply is the whole outcome), "task" (a one-off result such as a file or a single transformation), or "app" (reusable work: tracking, reviewing, recurring or repeated use). Do not create an App when a task or an answer serves the goal.
2. Give a concise plain-language interpretation: desired outcome, main input/source, what a useful result looks like, and the important assumptions you are making.
3. Ask at most three short questions, together, only when the answer changes something material: source coverage, what counts as a useful result, a required personal fact, storage or external-action scope, or important recurring behaviour. Offer options plus free text where helpful. Never ask the user to choose databases, schemas, components, technologies, layouts, names or sorting; choose reversible defaults for those and list them as assumptions.
4. When a request needs a capability that is not available, say so plainly, name the missing piece, and describe the useful partial outcome you can still deliver. Never claim or plan around an unavailable capability. List those capabilities in unavailable_capabilities.
5. Produce brief_draft for task and app deliveries (null for answer). Write everything a nontechnical person could read. Data needs use plain field names and kinds. Actions describe behaviour, inputs and outputs in words; effect_class is "none" for pure computation, "local_write" when records are saved. Acceptance examples are concrete: an input and the exact expected result, including at least one failure or boundary case.
6. Reply text is what the user reads: warm, specific, short. If you ask questions, the reply introduces them; if the brief is complete, the reply says what Alpha will make and how they will use it, and states any limits.
7. Corrections from the user supersede earlier assumptions. Keep everything already agreed unless the user changes it.

Output only the structured object."""


def system_prompt() -> str:
    return f"{SYSTEM_RULES}\n\n{catalog_prompt_text()}"


def turn_prompt(
    history: list[dict[str, Any]], current_brief: dict[str, Any] | None, latest: dict[str, Any]
) -> str:
    parts = ["CONVERSATION SO FAR (oldest first):"]
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
