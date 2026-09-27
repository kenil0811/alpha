"""A plain-language summary of an installed App, for the assistant when a conversation changes
it. Nothing technical the person would not recognise: tables and their fields, what it does,
what its screen shows and what it runs on a schedule."""

from __future__ import annotations

from alpha_contracts.apps import AppSource


def module_summary(source: AppSource) -> str:
    lines = [f"Name: {source.name}", f"What it is for: {source.description}"]
    if source.collections:
        lines.append("Tables it keeps (every field must stay, with the same kind):")
        for collection in source.collections:
            fields = ", ".join(
                f"{f.name} ({f.kind.value}{', required' if f.required else ''}"
                + (f", one of {'/'.join(f.choices)}" if f.choices else "")
                + ")"
                for f in collection.fields
            )
            purpose = f" — {collection.description}" if collection.description else ""
            lines.append(f"- {collection.name}{purpose}: {fields}")
    if source.actions:
        lines.append("What it does:")
        for action in source.actions:
            inputs = ", ".join((action.input_schema or {}).get("properties", {}).keys())
            lines.append(
                f"- {action.id}: {action.title}. {action.description}"
                + (f" Inputs: {inputs}." if inputs else "")
            )
    if source.screen is not None:
        tabs = []
        for tab in source.screen.tabs:
            kinds = ", ".join(block.kind for block in tab.blocks)
            tabs.append(f"{tab.title} ({kinds})")
        lines.append("Its screen has tabs: " + "; ".join(tabs))
    if source.schedules:
        lines.append("It runs on its own:")
        for schedule in source.schedules:
            when = (
                f"every {schedule.every_minutes} minutes"
                if schedule.every_minutes
                else f"daily at {schedule.daily_at}"
            )
            lines.append(f"- {schedule.title}: {schedule.action}, {when}")
    if source.capabilities:
        lines.append("It can reach: " + ", ".join(source.capabilities))
    return "\n".join(lines)
