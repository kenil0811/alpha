"""Where a person's data goes, stated from the configured model routes (M1 review finding F11).

Records, files and runs are stored on this Mac. What a person types to the assistant, and what a
workflow sends for a model estimate, is processed wherever the configured route runs. Only
trusted configuration decides that; the model may explain it but may not invent it, so an
unqualified "nothing leaves this Mac" from a remote route is replaced by the grounded statement.
"""

from __future__ import annotations

import re
from typing import Any

from alpha.models.gateway import ModelRoute

# Where each route processes what it is sent, in the person's words.
_PROCESSED_BY = {
    "fake": "a test responder on this Mac",
    "claude-code-cli": "Anthropic's Claude service over the internet",
}


def processed_by(route: ModelRoute) -> str:
    return _PROCESSED_BY.get(route.route_id, f"the {route.provider} model service")


def is_remote(route: ModelRoute) -> bool:
    return route.route_id != "fake"


def data_notice(assistant: ModelRoute, apps: ModelRoute | None = None) -> str:
    """One plain statement for the assistant and for briefs."""
    parts = ["Your records and files are stored on this Mac."]
    if is_remote(assistant):
        parts.append(f"What you type to the assistant is sent to {processed_by(assistant)}.")
    if apps is not None and is_remote(apps):
        parts.append(
            f"When a workflow asks for an estimate, what it sends (such as a description you "
            f"typed) goes to {processed_by(apps)}."
        )
    return " ".join(parts)


def app_data_notice(apps: ModelRoute) -> str:
    """For a workflow that uses model estimates."""
    if not is_remote(apps):
        return "Its records stay on this Mac. Estimates come from a test responder on this Mac."
    return (
        "Its records stay on this Mac. To make an estimate, it sends what the estimate is about "
        f"(such as a description you typed) to {processed_by(apps)}."
    )


# Absolute locality claims that are untrue when a remote route is in use. "Your records are
# stored on this Mac" is true and is left alone.
_CLAIMS = re.compile(
    r"[^.!?\n]*\b("
    r"nothing\s+(?:is\s+|gets\s+|will\s+be\s+|ever\s+)?(?:sent|shared|uploaded)"
    r"|nothing\s+(?:ever\s+)?leaves"
    r"|never\s+leaves\s+(?:this|your)\s+mac"
    r"|(?:everything|all\s+(?:of\s+)?(?:your\s+)?(?:data|information))\s+"
    r"(?:stays|remains|is\s+kept|is\s+stored)\s+(?:only\s+|entirely\s+|completely\s+)?"
    r"(?:on|in)\s+(?:this|your)\s+mac"
    r"|(?:stays|stay|remains)\s+(?:entirely\s+|completely\s+)?(?:local|private\s+to\s+(?:this|your)\s+mac)"
    r")\b[^.!?\n]*[.!?]?",
    re.IGNORECASE,
)


def ground_text(text: str, notice: str) -> tuple[str, bool]:
    """Replace untrue locality claims with the grounded statement (once per text)."""
    if not _CLAIMS.search(text):
        return text, False
    replaced = False

    def swap(match: re.Match[str]) -> str:
        nonlocal replaced
        prefix = " " if match.group(0).startswith(" ") else ""
        if replaced:
            return ""
        replaced = True
        return prefix + notice

    return re.sub(r"\s{2,}", " ", _CLAIMS.sub(swap, text)).strip(), True


def ground_output(output: Any, notice: str) -> tuple[Any, list[str]]:
    """Ground the assistant's reply, interpretation and assumptions; returns what changed."""
    changed: list[str] = []
    reply, hit = ground_text(output.reply, notice)
    if hit:
        changed.append("reply")
    interpretation = output.interpretation
    kept: list[str] = []
    for item in interpretation.important_assumptions:
        grounded, hit = ground_text(item, notice)
        kept.append(grounded)
        if hit:
            changed.append("interpretation")
    assumptions: list[str] = []
    for item in output.assumptions:
        grounded, hit = ground_text(item, notice)
        assumptions.append(grounded)
        if hit:
            changed.append("assumptions")
    draft = output.brief_draft
    if draft is not None:
        constraints = []
        for item in draft.constraints:
            grounded, hit = ground_text(item, notice)
            constraints.append(grounded)
            if hit:
                changed.append("constraints")
        draft = draft.model_copy(update={"constraints": list(dict.fromkeys(constraints))})
    if not changed:
        return output, []
    return (
        output.model_copy(
            update={
                "reply": reply,
                "interpretation": interpretation.model_copy(
                    update={"important_assumptions": list(dict.fromkeys(kept))}
                ),
                "assumptions": list(dict.fromkeys(assumptions)),
                "brief_draft": draft,
            }
        ),
        sorted(set(changed)),
    )
