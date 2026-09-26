"""Action handlers. Each takes the Context first, then the action's declared inputs."""

from __future__ import annotations

from datetime import timezone
from typing import Any

from alpha_sdk import Context
from alpha_sdk.query import eq

STAGES = ["Found", "Applied", "Interviewing", "Offer", "Rejected", "Withdrew"]

# A step that clearly implies a stage moves the opening to it.
STAGE_FOR_STEP = {
    "Found it": "Found",
    "Applied": "Applied",
    "Phone screen": "Interviewing",
    "Interviewed": "Interviewing",
    "Offer received": "Offer",
    "Rejected": "Rejected",
    "Withdrew": "Withdrew",
}


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _stamp(ctx: Context) -> str:
    """Now, always with a UTC offset so the datetime field accepts it."""
    moment = ctx.now()
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat()


def _touch(ctx: Context, opening_id: str, stage: str | None) -> tuple[str, int, str]:
    """Record activity on an opening, changing its stage when one is given."""
    opening = ctx.records.get("job_openings", opening_id)
    changes: dict[str, Any] = {"last_activity": _stamp(ctx)}
    if stage and stage != opening.get("stage"):
        changes["stage"] = stage
    updated = ctx.records.update(
        "job_openings",
        opening_id,
        expected_revision=opening.revision,
        changes=changes,
    )
    return updated.id, updated.revision, str(updated.get("stage"))


def add_opening(
    ctx: Context,
    company: str,
    role: str,
    where_i_found_it: str | None = None,
    link: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    company_name = _text(company)
    role_name = _text(role)
    if not company_name:
        raise ValueError("Add a company before saving this opening.")
    if not role_name:
        raise ValueError("Add a role before saving this opening.")
    record = ctx.records.create(
        "job_openings",
        {
            "company": company_name,
            "role": role_name,
            "where_i_found_it": _text(where_i_found_it) or None,
            "link": _text(link) or None,
            "stage": "Found",
            "date_found": ctx.today().isoformat(),
            "notes": _text(notes) or None,
            "last_activity": _stamp(ctx),
        },
    )
    return {"id": record.id, "revision": record.revision, "stage": "Found"}


def log_step(
    ctx: Context,
    opening: str,
    date: str,
    what_i_did: str,
    note: str | None = None,
) -> dict[str, Any]:
    step = ctx.records.create(
        "steps_taken",
        {
            "opening": opening,
            "date": date,
            "what_i_did": what_i_did,
            "note": _text(note) or None,
        },
    )
    _, _, stage = _touch(ctx, opening, STAGE_FOR_STEP.get(what_i_did))
    return {"id": step.id, "revision": step.revision, "stage": stage}


def set_stage(ctx: Context, opening: str, new_stage: str) -> dict[str, Any]:
    if new_stage not in STAGES:
        raise ValueError("Choose one of the stages in the list.")
    today = ctx.today().isoformat()
    ctx.records.create(
        "steps_taken",
        {
            "opening": opening,
            "date": today,
            "what_i_did": "Stage changed",
            "note": "Stage set to " + new_stage,
        },
    )
    opening_id, revision, stage = _touch(ctx, opening, new_stage)
    return {"id": opening_id, "revision": revision, "stage": stage}


def review_list(ctx: Context, stage_filter: str | None = None) -> dict[str, Any]:
    wanted = _text(stage_filter)
    where = eq("stage", wanted) if wanted and wanted != "All stages" else None
    records = ctx.records.all(
        "job_openings", where=where, order_by=["-last_activity", "-created_at"]
    )
    openings = [
        {
            "id": record.id,
            "company": str(record.get("company")),
            "role": str(record.get("role")),
            "stage": str(record.get("stage")),
        }
        for record in records
    ]
    tally = {stage: 0 for stage in STAGES}
    for record in ctx.records.all("job_openings"):
        stage = str(record.get("stage"))
        tally[stage] = tally.get(stage, 0) + 1
    counts = [{"stage": stage, "openings": tally[stage]} for stage in STAGES]
    return {"openings": openings, "counts": counts}
